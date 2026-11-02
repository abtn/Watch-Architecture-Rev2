"""Rebuildable R6-D projection and policy-scoped hybrid retrieval for Signals."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from core.embeddings import EmbeddingBatch, EmbeddingProvider, EmbeddingSpace
from core.models import (
    Event,
    KnowledgeChunk,
    KnowledgeItem,
    LearningChange,
    Outcome,
    Signal,
    Task,
    Team,
    TeamExperienceChunk,
    TeamExperienceIndexState,
    TeamPolicy,
)
from core.policy import InvalidPolicyError, knowledge_item_review_interval_days
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.vector_type import serialize_vector, validate_vector

CHUNK_MAX_CHARACTERS = 1200
CHUNK_OVERLAP_CHARACTERS = 150
CHUNK_STEP_CHARACTERS = CHUNK_MAX_CHARACTERS - CHUNK_OVERLAP_CHARACTERS
CHUNKING_VERSION = "r6d-char-1200-overlap-150-v1"
LEXICAL_CANDIDATE_LIMIT = 20
VECTOR_CANDIDATE_LIMIT = 20
RECIPROCAL_RANK_FUSION_K = 60
MAX_RETRIEVED_PASSAGES = 8
MAX_RETRIEVED_CHARACTERS = 8000


class KnowledgeIndexError(RuntimeError):
    """A projection failure that leaves canonical Signals and Snapshots intact."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _VisibleTextParser(HTMLParser):
    """Deterministically discard markup and hidden executable/template content."""

    _HIDDEN_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._HIDDEN_TAGS:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._HIDDEN_TAGS and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def normalize_source_text(content: bytes) -> str:
    """Extract stable visible text from UTF-8 source bytes."""
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise KnowledgeIndexError("snapshot_not_utf8") from error

    if re.search(r"<[A-Za-z!/][^>]{0,256}>", decoded):
        parser = _VisibleTextParser()
        try:
            parser.feed(decoded)
            parser.close()
        except Exception as error:
            raise KnowledgeIndexError("snapshot_text_extraction_failed") from error
        decoded = " ".join(parser.parts)

    normalized = re.sub(r"\s+", " ", decoded).strip()
    if not normalized:
        raise KnowledgeIndexError("snapshot_has_no_indexable_text")
    return normalized


def chunk_source_text(content: bytes) -> tuple[str, ...]:
    """Normalize and split text with deterministic character overlap."""
    normalized = normalize_source_text(content)
    chunks = tuple(
        normalized[start : start + CHUNK_MAX_CHARACTERS]
        for start in range(0, len(normalized), CHUNK_STEP_CHARACTERS)
    )
    return tuple(chunk for chunk in chunks if chunk)


def content_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def text_hash(value: str) -> str:
    return content_hash(value.encode("utf-8"))


@dataclass(frozen=True)
class IndexingResult:
    signal_id: UUID
    outcome: str
    chunk_count: int
    embedding_space_key: str


@dataclass(frozen=True)
class RetrievedPassage:
    signal_id: UUID | None
    source_url: str | None
    source_type: str | None
    snapshot_ref: str | None
    content_hash: str
    chunk_id: UUID
    chunk_index: int
    text: str
    chunk_hash: str
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    embedding_space_key: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str
    embedding_configuration: str
    embedding_dimensions: int
    truncated: bool = False
    logical_core: str = "domain_knowledge"
    knowledge_item_id: UUID | None = None
    knowledge_item_version: int | None = None
    origin_learning_change_id: UUID | None = None


class SignalIndexer:
    """Create/rebuild only the derived Signal/Snapshot chunk projection."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._embedding_provider = embedding_provider

    def index_signal(self, signal_id: UUID) -> IndexingResult:
        source = self._load_signal(signal_id)
        raw_snapshot = self._read_verified_snapshot(source)
        chunks = chunk_source_text(raw_snapshot)
        space = self._embedding_provider.current_space()

        if self._projection_matches(source, chunks, space):
            return IndexingResult(
                signal_id=signal_id,
                outcome="unchanged",
                chunk_count=len(chunks),
                embedding_space_key=space.key,
            )

        batch = self._embedding_provider.embed(chunks)
        self._validate_batch(batch, chunks)
        # The installed model can change while the local service is running. If so,
        # retain the old projection rather than publishing vectors under a stale key.
        if self._embedding_provider.current_space().key != batch.space.key:
            raise KnowledgeIndexError("embedding_space_changed_during_indexing")

        rows = [
            KnowledgeChunk(
                id=uuid4(),
                signal_id=signal_id,
                chunk_index=index,
                chunk_text=chunk,
                chunk_hash=text_hash(chunk),
                source_snapshot_ref=source.snapshot_ref,
                source_content_hash=source.content_hash,
                chunking_version=CHUNKING_VERSION,
                embedding=list(vector),
                embedding_provider=batch.space.provider,
                embedding_model=batch.space.model,
                embedding_revision=batch.space.revision,
                embedding_configuration=batch.space.configuration,
                embedding_dimensions=batch.space.dimensions,
                embedding_space_key=batch.space.key,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, batch.vectors))
        ]

        # Canonical state and the derived projection use separate transactions. The
        # Signal is locked/rechecked before the old projection is replaced atomically.
        with self._session_factory.begin() as session:
            current_signal = session.scalar(
                select(Signal)
                .where(Signal.id == signal_id)
                .with_for_update()
            )
            if current_signal is None:
                raise KnowledgeIndexError("signal_disappeared_during_indexing")
            if (
                current_signal.snapshot_ref != source.snapshot_ref
                or current_signal.content_hash != source.content_hash
                or current_signal.origin_url != source.origin_url
                or current_signal.source_type != source.source_type
                or current_signal.domain != source.domain
            ):
                raise KnowledgeIndexError("signal_changed_during_indexing")

            session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.signal_id == signal_id)
            )
            session.add_all(rows)
            session.flush()

        return IndexingResult(
            signal_id=signal_id,
            outcome="indexed",
            chunk_count=len(rows),
            embedding_space_key=batch.space.key,
        )

    def rebuild_all(self) -> tuple[IndexingResult, ...]:
        """Idempotently index every existing Signal in deterministic ID order."""
        with self._session_factory() as session:
            signal_ids = tuple(
                session.scalars(select(Signal.id).order_by(Signal.id)).all()
            )
        return tuple(self.index_signal(signal_id) for signal_id in signal_ids)

    def _load_signal(self, signal_id: UUID) -> _SignalSource:
        with self._session_factory() as session:
            signal = session.get(Signal, signal_id)
            if signal is None:
                raise KnowledgeIndexError("signal_not_found")
            return _SignalSource(
                id=signal.id,
                domain=signal.domain,
                source_type=signal.source_type,
                origin_url=signal.origin_url,
                content_hash=signal.content_hash,
                snapshot_ref=signal.snapshot_ref,
            )

    def _read_verified_snapshot(self, source: _SignalSource) -> bytes:
        try:
            content = self._snapshot_store.read(source.snapshot_ref)
        except SnapshotIntegrityError as error:
            raise KnowledgeIndexError("source_snapshot_integrity_failure") from error
        if content_hash(content) != source.content_hash:
            raise KnowledgeIndexError("signal_snapshot_hash_mismatch")
        return content

    def _projection_matches(
        self, source: _SignalSource, chunks: tuple[str, ...], space: EmbeddingSpace
    ) -> bool:
        with self._session_factory() as session:
            existing = session.execute(
                select(
                    KnowledgeChunk.chunk_index,
                    KnowledgeChunk.chunk_text,
                    KnowledgeChunk.chunk_hash,
                    KnowledgeChunk.source_snapshot_ref,
                    KnowledgeChunk.source_content_hash,
                    KnowledgeChunk.chunking_version,
                    KnowledgeChunk.embedding_provider,
                    KnowledgeChunk.embedding_model,
                    KnowledgeChunk.embedding_revision,
                    KnowledgeChunk.embedding_configuration,
                    KnowledgeChunk.embedding_dimensions,
                    KnowledgeChunk.embedding_space_key,
                )
                .where(KnowledgeChunk.signal_id == source.id)
                .order_by(KnowledgeChunk.chunk_index)
            ).mappings().all()

        if len(existing) != len(chunks):
            return False
        for expected_index, (row, chunk) in enumerate(zip(existing, chunks)):
            if (
                row["chunk_index"] != expected_index
                or row["chunk_text"] != chunk
                or row["chunk_hash"] != text_hash(chunk)
                or row["source_snapshot_ref"] != source.snapshot_ref
                or row["source_content_hash"] != source.content_hash
                or row["chunking_version"] != CHUNKING_VERSION
                or row["embedding_provider"] != space.provider
                or row["embedding_model"] != space.model
                or row["embedding_revision"] != space.revision
                or row["embedding_configuration"] != space.configuration
                or row["embedding_dimensions"] != space.dimensions
                or row["embedding_space_key"] != space.key
            ):
                return False
        return True

    @staticmethod
    def _validate_batch(batch: EmbeddingBatch, chunks: tuple[str, ...]) -> None:
        if len(batch.vectors) != len(chunks):
            raise KnowledgeIndexError("embedding_count_mismatch")
        if batch.space.dimensions <= 0 or not batch.space.key.startswith("sha256:"):
            raise KnowledgeIndexError("invalid_embedding_space")
        for vector in batch.vectors:
            try:
                validate_vector(vector, batch.space.dimensions)
            except ValueError as error:
                raise KnowledgeIndexError(error.args[0]) from error


@dataclass(frozen=True)
class _SignalSource:
    id: UUID
    domain: str
    source_type: str
    origin_url: str
    content_hash: str
    snapshot_ref: str


@dataclass(frozen=True)
class TeamExperienceIndexingResult:
    knowledge_item_id: UUID
    outcome: str
    chunk_count: int
    embedding_space_key: str | None
    item_content_hash: str | None


def _knowledge_item_state(item: KnowledgeItem) -> dict[str, Any]:
    """Use the canonical acceptance-state reconstruction for integrity checks."""
    from core.learning_commit import LearningCommitService

    return LearningCommitService._knowledge_item_state(item)


def knowledge_item_committed_state_matches(
    item: KnowledgeItem, learning_change: LearningChange
) -> bool:
    """Compare immutable content/provenance while allowing lifecycle status changes."""
    committed = learning_change.committed_state
    if not isinstance(committed, dict):
        return False
    current = _knowledge_item_state(item)
    for field in ("status", "last_validated_at"):
        current.pop(field, None)
        committed = dict(committed)
        committed.pop(field, None)
    return current == committed


def knowledge_item_content_hash(item: KnowledgeItem) -> str:
    """Hash the complete canonical item identity/content, not mutable review status."""
    from core.state_assessment import _canonical_json

    state = _knowledge_item_state(item)
    state.pop("status", None)
    state.pop("last_validated_at", None)
    return content_hash(_canonical_json(state).encode("utf-8"))


def knowledge_item_text(item: KnowledgeItem) -> str:
    """Create a deterministic, readable embedding document from canonical fields."""
    from core.state_assessment import _canonical_json

    sections = [
        f"Knowledge item: {item.title}",
        f"Kind: {item.kind}",
        f"Statement: {item.statement}",
        f"Body: {item.body}",
        f"Applicability: {_canonical_json(item.applicability)}",
        f"Preconditions: {_canonical_json(item.preconditions)}",
        f"Assumptions: {_canonical_json(item.assumptions)}",
        f"Limitations: {_canonical_json(item.limitations)}",
        f"Non-applicability: {_canonical_json(item.non_applicability)}",
        f"Failure modes: {_canonical_json(item.failure_modes)}",
        f"Known counterexamples: {_canonical_json(item.known_counterexamples)}",
        f"Missing information: {_canonical_json(item.missing_information)}",
        f"Uncertainty: {_canonical_json(item.uncertainty)}",
    ]
    return "\\n".join(sections)


def _review_date_is_eligible(item: KnowledgeItem, now: datetime) -> bool:
    review_after = item.review_after
    return (
        item.status == "active"
        and review_after is not None
        and review_after.tzinfo is not None
        and review_after.utcoffset() == timedelta(0)
        and review_after > now
    )


def _accepted_learning_change_is_canonical(
    session: Session, item: KnowledgeItem, learning_change: LearningChange
) -> bool:
    if (
        learning_change.id != item.origin_learning_change_id
        or learning_change.team_id != item.team_id
        or learning_change.target_kind != "knowledge_item"
        or learning_change.target_id is not None
        or learning_change.operation != "create"
        or learning_change.status != "accepted"
        or learning_change.committed_by_task_id is None
        or learning_change.committed_at is None
        or not knowledge_item_committed_state_matches(item, learning_change)
    ):
        return False

    approval_task = session.get(Task, learning_change.committed_by_task_id)
    if (
        approval_task is None
        or approval_task.team_id != item.team_id
        or approval_task.task_type != "approve_learning_change"
        or approval_task.status != "done"
        or approval_task.completed_at is None
        or approval_task.attempt_count < 1
    ):
        return False

    policy = session.scalar(
        select(TeamPolicy).where(
            TeamPolicy.team_id == approval_task.team_id,
            TeamPolicy.version == approval_task.policy_version,
        )
    )
    if policy is None:
        return False
    try:
        interval_days = knowledge_item_review_interval_days(
            policy.rules, policy.schema_version
        )
    except InvalidPolicyError:
        return False
    expected_review_after = (
        learning_change.committed_at + timedelta(days=interval_days)
        if interval_days is not None
        else None
    )
    if item.review_after != expected_review_after:
        return False

    decision_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == approval_task.id,
                Event.type == "learning_change_accepted",
            )
        )
    )
    if len(decision_events) != 1:
        return False
    decision = decision_events[0].payload
    if (
        not isinstance(decision, dict)
        or decision.get("learning_change_id") != str(learning_change.id)
        or decision.get("decision") != "accept"
        or decision.get("approval_task_id") != str(approval_task.id)
        or decision.get("operator_id") != learning_change.operator_id
        or decision.get("knowledge_item_id") != str(item.id)
        or decision.get("knowledge_item_version") != item.version
        or decision.get("committed_at") != learning_change.committed_at.isoformat()
    ):
        return False

    outcomes = list(
        session.scalars(
            select(Outcome).where(
                Outcome.recorded_by_task_id == approval_task.id,
                Outcome.outcome_type == "task_execution",
            )
        )
    )
    completed_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == approval_task.id,
                Event.type == "task_completed",
            )
        )
    )
    return (
        len(outcomes) == 1
        and outcomes[0].team_id == item.team_id
        and outcomes[0].subject_kind == "task"
        and outcomes[0].subject_id == approval_task.id
        and len(completed_events) == 1
        and completed_events[0].payload.get("to_status") == "done"
        and completed_events[0].payload.get("result_category")
        == "success_learning_change_accepted"
        and completed_events[0].payload.get("learning_change_id")
        == str(learning_change.id)
        and completed_events[0].payload.get("outcome_id") == str(outcomes[0].id)
    )


class TeamExperienceIndexer:
    """Build a separate rebuildable projection from accepted canonical Team
    Experience.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider

    @staticmethod
    def _upsert_index_state(
        session: Session,
        item: KnowledgeItem,
        item_hash: str,
        *,
        status: str,
        embedding_space_key: str | None,
        chunk_count: int | None = None,
        error_kind: str | None = None,
        increment_attempt: bool = False,
        now: datetime,
    ) -> None:
        current_item = session.scalar(
            select(KnowledgeItem)
            .where(KnowledgeItem.id == item.id)
            .with_for_update()
        )
        if current_item is None:
            raise KnowledgeIndexError("knowledge_item_disappeared_during_index_state_update")
        if (
            current_item.team_id != item.team_id
            or current_item.version != item.version
            or current_item.origin_learning_change_id != item.origin_learning_change_id
            or knowledge_item_content_hash(current_item) != item_hash
        ):
            raise KnowledgeIndexError("knowledge_item_changed_during_index_state_update")

        state = session.scalar(
            select(TeamExperienceIndexState)
            .where(
                TeamExperienceIndexState.knowledge_item_id == item.id,
                TeamExperienceIndexState.team_id == item.team_id,
            )
            .with_for_update()
        )
        if state is None:
            state = TeamExperienceIndexState(
                id=uuid4(),
                knowledge_item_id=item.id,
                team_id=item.team_id,
                item_version=item.version,
                item_content_hash=item_hash,
                origin_learning_change_id=item.origin_learning_change_id,
                status=status,
                embedding_space_key=embedding_space_key,
                chunk_count=0,
                attempt_count=0,
                last_error_kind=None,
                last_attempt_at=None,
                indexed_at=None,
            )
            session.add(state)
        state.item_version = item.version
        state.item_content_hash = item_hash
        state.origin_learning_change_id = item.origin_learning_change_id
        state.status = status
        state.embedding_space_key = embedding_space_key
        if chunk_count is not None:
            state.chunk_count = chunk_count
        state.last_error_kind = error_kind
        if increment_attempt:
            state.attempt_count += 1
            state.last_attempt_at = now
        if status == "published":
            state.indexed_at = now
        elif status == "ineligible":
            state.indexed_at = None
        state.updated_at = now

    def _record_index_state(
        self,
        item: KnowledgeItem,
        item_hash: str,
        *,
        status: str,
        embedding_space_key: str | None,
        chunk_count: int | None = None,
        error_kind: str | None = None,
        increment_attempt: bool = False,
        now: datetime,
    ) -> None:
        with self._session_factory.begin() as session:
            self._upsert_index_state(
                session,
                item,
                item_hash,
                status=status,
                embedding_space_key=embedding_space_key,
                chunk_count=chunk_count,
                error_kind=error_kind,
                increment_attempt=increment_attempt,
                now=now,
            )

    def index_knowledge_item(
        self, knowledge_item_id: UUID, *, now: datetime | None = None
    ) -> TeamExperienceIndexingResult:
        reference_time = now or datetime.now(timezone.utc)
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise KnowledgeIndexError("review_reference_time_not_timezone_aware")
        reference_time = reference_time.astimezone(timezone.utc)

        source = self._load_item(knowledge_item_id)
        if source is None:
            return TeamExperienceIndexingResult(
                knowledge_item_id, "missing", 0, None, None
            )
        item, learning_change = source
        with self._session_factory() as session:
            canonical = _accepted_learning_change_is_canonical(
                session, item, learning_change
            )
        if not canonical:
            raise KnowledgeIndexError("knowledge_item_canonical_state_invalid")
        item_hash = knowledge_item_content_hash(item)

        if not _review_date_is_eligible(item, reference_time):
            with self._session_factory.begin() as session:
                session.execute(
                    delete(TeamExperienceChunk).where(
                        TeamExperienceChunk.knowledge_item_id == knowledge_item_id
                    )
                )
                self._upsert_index_state(
                    session,
                    item,
                    item_hash,
                    status="ineligible",
                    embedding_space_key=None,
                    chunk_count=0,
                    now=reference_time,
                )
            return TeamExperienceIndexingResult(
                knowledge_item_id, "ineligible", 0, None, item_hash
            )

        try:
            raw_text = knowledge_item_text(item).encode("utf-8")
            chunks = chunk_source_text(raw_text)
            space = self._embedding_provider.current_space()
        except Exception as error:
            self._record_index_state(
                item,
                item_hash,
                status="stale",
                embedding_space_key=None,
                error_kind=type(error).__name__,
                increment_attempt=True,
                now=reference_time,
            )
            raise

        if self._projection_matches(item, item_hash, chunks, space):
            return TeamExperienceIndexingResult(
                knowledge_item_id, "unchanged", len(chunks), space.key, item_hash
            )

        self._record_index_state(
            item,
            item_hash,
            status="stale",
            embedding_space_key=space.key,
            error_kind=None,
            increment_attempt=True,
            now=reference_time,
        )
        try:
            batch = self._embedding_provider.embed(chunks)
            SignalIndexer._validate_batch(batch, chunks)
            if self._embedding_provider.current_space().key != batch.space.key:
                raise KnowledgeIndexError("embedding_space_changed_during_indexing")
        except Exception as error:
            self._record_index_state(
                item,
                item_hash,
                status="stale",
                embedding_space_key=space.key,
                error_kind=type(error).__name__,
                now=datetime.now(timezone.utc),
            )
            raise

        rows = [
            TeamExperienceChunk(
                id=uuid4(),
                knowledge_item_id=item.id,
                team_id=item.team_id,
                item_version=item.version,
                item_content_hash=item_hash,
                origin_learning_change_id=item.origin_learning_change_id,
                chunk_index=index,
                chunk_text=chunk,
                chunk_hash=text_hash(chunk),
                chunking_version=CHUNKING_VERSION,
                embedding=list(vector),
                embedding_provider=batch.space.provider,
                embedding_model=batch.space.model,
                embedding_revision=batch.space.revision,
                embedding_configuration=batch.space.configuration,
                embedding_dimensions=batch.space.dimensions,
                embedding_space_key=batch.space.key,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, batch.vectors))
        ]

        with self._session_factory.begin() as session:
            current_item = session.scalar(
                select(KnowledgeItem)
                .where(KnowledgeItem.id == knowledge_item_id)
                .with_for_update()
            )
            if current_item is None:
                raise KnowledgeIndexError("knowledge_item_disappeared_during_indexing")
            current_change = session.get(
                LearningChange, current_item.origin_learning_change_id
            )
            if current_change is None or not _accepted_learning_change_is_canonical(
                session, current_item, current_change
            ):
                raise KnowledgeIndexError("knowledge_item_changed_during_indexing")
            if not _review_date_is_eligible(
                current_item, datetime.now(timezone.utc)
            ):
                session.execute(
                    delete(TeamExperienceChunk).where(
                        TeamExperienceChunk.knowledge_item_id == knowledge_item_id
                    )
                )
                self._upsert_index_state(
                    session,
                    current_item,
                    knowledge_item_content_hash(current_item),
                    status="ineligible",
                    embedding_space_key=None,
                    chunk_count=0,
                    now=datetime.now(timezone.utc),
                )
                return TeamExperienceIndexingResult(
                    knowledge_item_id, "ineligible", 0, None, item_hash
                )
            if (
                current_item.version != item.version
                or knowledge_item_content_hash(current_item) != item_hash
                or current_item.origin_learning_change_id
                != item.origin_learning_change_id
            ):
                raise KnowledgeIndexError("knowledge_item_changed_during_indexing")

            session.execute(
                delete(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == knowledge_item_id
                )
            )
            session.add_all(rows)
            session.flush()
            self._upsert_index_state(
                session,
                current_item,
                item_hash,
                status="published",
                embedding_space_key=batch.space.key,
                chunk_count=len(rows),
                error_kind=None,
                now=datetime.now(timezone.utc),
            )

        return TeamExperienceIndexingResult(
            knowledge_item_id, "indexed", len(rows), batch.space.key, item_hash
        )

    def rebuild_all(
        self, *, now: datetime | None = None
    ) -> tuple[TeamExperienceIndexingResult, ...]:
        reference_time = now or datetime.now(timezone.utc)
        with self._session_factory() as session:
            item_ids = set(
                session.scalars(
                    select(KnowledgeItem.id).where(
                        KnowledgeItem.status == "active",
                        KnowledgeItem.review_after.is_not(None),
                        KnowledgeItem.review_after > reference_time,
                    )
                ).all()
            )
            item_ids.update(
                session.scalars(
                    select(TeamExperienceChunk.knowledge_item_id).distinct()
                ).all()
            )
            item_ids.update(
                session.scalars(
                    select(TeamExperienceIndexState.knowledge_item_id).distinct()
                ).all()
            )
        return tuple(
            self.index_knowledge_item(item_id, now=reference_time)
            for item_id in sorted(item_ids, key=str)
        )

    def _load_item(
        self, knowledge_item_id: UUID
    ) -> tuple[KnowledgeItem, LearningChange] | None:
        with self._session_factory() as session:
            item = session.get(KnowledgeItem, knowledge_item_id)
            if item is None:
                return None
            learning_change = session.get(
                LearningChange, item.origin_learning_change_id
            )
            if learning_change is None:
                raise KnowledgeIndexError("knowledge_item_origin_missing")
            return item, learning_change

    def _projection_matches(
        self,
        item: KnowledgeItem,
        item_hash: str,
        chunks: tuple[str, ...],
        space: EmbeddingSpace,
    ) -> bool:
        with self._session_factory() as session:
            state = session.scalar(
                select(TeamExperienceIndexState).where(
                    TeamExperienceIndexState.knowledge_item_id == item.id,
                    TeamExperienceIndexState.team_id == item.team_id,
                )
            )
            if (
                state is None
                or state.status != "published"
                or state.item_version != item.version
                or state.item_content_hash != item_hash
                or state.origin_learning_change_id != item.origin_learning_change_id
                or state.embedding_space_key != space.key
                or state.chunk_count != len(chunks)
            ):
                return False
            rows = session.execute(
                select(
                    TeamExperienceChunk.chunk_index,
                    TeamExperienceChunk.chunk_text,
                    TeamExperienceChunk.chunk_hash,
                    TeamExperienceChunk.item_version,
                    TeamExperienceChunk.item_content_hash,
                    TeamExperienceChunk.origin_learning_change_id,
                    TeamExperienceChunk.chunking_version,
                    TeamExperienceChunk.embedding_provider,
                    TeamExperienceChunk.embedding_model,
                    TeamExperienceChunk.embedding_revision,
                    TeamExperienceChunk.embedding_configuration,
                    TeamExperienceChunk.embedding_dimensions,
                    TeamExperienceChunk.embedding_space_key,
                )
                .where(TeamExperienceChunk.knowledge_item_id == item.id)
                .order_by(TeamExperienceChunk.chunk_index)
            ).mappings().all()
        if len(rows) != len(chunks):
            return False
        for index, (row, chunk) in enumerate(zip(rows, chunks)):
            if (
                row["chunk_index"] != index
                or row["chunk_text"] != chunk
                or row["chunk_hash"] != text_hash(chunk)
                or row["item_version"] != item.version
                or row["item_content_hash"] != item_hash
                or row["origin_learning_change_id"] != item.origin_learning_change_id
                or row["chunking_version"] != CHUNKING_VERSION
                or row["embedding_provider"] != space.provider
                or row["embedding_model"] != space.model
                or row["embedding_revision"] != space.revision
                or row["embedding_configuration"] != space.configuration
                or row["embedding_dimensions"] != space.dimensions
                or row["embedding_space_key"] != space.key
            ):
                return False
        return True


class HybridKnowledgeRetriever:
    """Hybrid PostgreSQL FTS/vector retrieval, authorized from current Team policy."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._embedding_provider = embedding_provider

    def retrieve(self, team_id: UUID, query: str) -> tuple[RetrievedPassage, ...]:
        if not isinstance(query, str) or not query.strip():
            return ()

        query_batch = self._embedding_provider.embed([query.strip()])
        if len(query_batch.vectors) != 1:
            raise KnowledgeIndexError("query_embedding_count_mismatch")
        try:
            query_vector = validate_vector(
                query_batch.vectors[0], query_batch.space.dimensions
            )
        except ValueError as error:
            raise KnowledgeIndexError(error.args[0]) from error

        now_utc = datetime.now(timezone.utc)
        domain_ranked: list[tuple[float, dict[str, Any]]] = []
        experience_verified: list[tuple[float, dict[str, Any]]] = []

        with self._session_factory() as session:
            with session.begin():
                session.connection(
                    execution_options={"isolation_level": "REPEATABLE READ"}
                )
                team = session.get(Team, team_id)
                if team is None or team.status != "active" or not team.domain.strip():
                    return ()
                policy = session.scalar(
                    select(TeamPolicy)
                    .where(TeamPolicy.team_id == team_id)
                    .order_by(TeamPolicy.version.desc())
                    .limit(1)
                )
                if policy is None:
                    return ()

                embedding_parameters: dict[str, Any] = {
                    "embedding_space_key": query_batch.space.key,
                    "embedding_provider": query_batch.space.provider,
                    "embedding_model": query_batch.space.model,
                    "embedding_revision": query_batch.space.revision,
                    "embedding_configuration": query_batch.space.configuration,
                    "embedding_dimensions": query_batch.space.dimensions,
                    "chunking_version": CHUNKING_VERSION,
                    "query": query.strip(),
                    "query_vector": serialize_vector(query_vector),
                }

                allowed_sources = self._allowed_sources(policy.rules)
                if allowed_sources:
                    scope_clause, scope_params = _source_predicate(allowed_sources)
                    domain_parameters = {
                        **embedding_parameters,
                        **scope_params,
                        "domain": team.domain,
                        "candidate_limit": LEXICAL_CANDIDATE_LIMIT,
                    }
                    domain_where = (
                        "c.embedding_space_key = :embedding_space_key "
                        "AND c.embedding_provider = :embedding_provider "
                        "AND c.embedding_model = :embedding_model "
                        "AND c.embedding_revision = :embedding_revision "
                        "AND c.embedding_configuration = :embedding_configuration "
                        "AND c.embedding_dimensions = :embedding_dimensions "
                        "AND c.chunking_version = :chunking_version "
                        "AND s.domain = :domain "
                        "AND c.source_snapshot_ref = s.snapshot_ref "
                        "AND c.source_content_hash = s.content_hash "
                        f"AND {scope_clause}"
                    )
                    projection = _candidate_select()
                    lexical_rows = session.execute(
                        text(
                            f"{projection} WHERE {domain_where} "
                            "AND to_tsvector('simple', c.chunk_text) "
                            "@@ plainto_tsquery('simple', :query) "
                            "ORDER BY ts_rank_cd(to_tsvector('simple', c.chunk_text), "
                            "plainto_tsquery('simple', :query)) DESC, "
                            "c.signal_id, c.chunk_index, c.id "
                            "LIMIT :candidate_limit"
                        ),
                        domain_parameters,
                    ).mappings().all()
                    domain_parameters["candidate_limit"] = VECTOR_CANDIDATE_LIMIT
                    vector_rows = session.execute(
                        text(
                            f"{projection} WHERE {domain_where} "
                            "ORDER BY c.embedding <=> CAST(:query_vector AS vector), "
                            "c.signal_id, c.chunk_index, c.id "
                            "LIMIT :candidate_limit"
                        ),
                        domain_parameters,
                    ).mappings().all()
                    domain_ranked = _rank_candidate_rows(
                        lexical_rows, vector_rows, "domain_knowledge"
                    )

                experience_where = (
                    "c.team_id = :team_id "
                    "AND i.team_id = :team_id "
                    "AND i.status = 'active' "
                    "AND i.review_after IS NOT NULL "
                    "AND i.review_after > :now_utc "
                    "AND i.version = c.item_version "
                    "AND i.origin_learning_change_id = c.origin_learning_change_id "
                    "AND lc.id = i.origin_learning_change_id "
                    "AND lc.team_id = i.team_id "
                    "AND lc.status = 'accepted' "
                    "AND lc.target_kind = 'knowledge_item' "
                    "AND lc.target_id IS NULL "
                    "AND lc.operation = 'create' "
                    "AND st.status = 'published' "
                    "AND st.item_version = c.item_version "
                    "AND st.item_content_hash = c.item_content_hash "
                    "AND st.origin_learning_change_id = c.origin_learning_change_id "
                    "AND st.embedding_space_key = c.embedding_space_key "
                    "AND st.chunk_count > c.chunk_index "
                    "AND c.embedding_space_key = :embedding_space_key "
                    "AND c.embedding_provider = :embedding_provider "
                    "AND c.embedding_model = :embedding_model "
                    "AND c.embedding_revision = :embedding_revision "
                    "AND c.embedding_configuration = :embedding_configuration "
                    "AND c.embedding_dimensions = :embedding_dimensions "
                    "AND c.chunking_version = :chunking_version"
                )
                experience_projection = (
                    "SELECT c.id AS chunk_id, "
                    "c.knowledge_item_id, c.team_id, c.item_version, "
                    "c.item_content_hash, c.origin_learning_change_id, "
                    "c.chunk_index, c.chunk_text, c.chunk_hash, c.chunking_version, "
                    "c.embedding_provider, c.embedding_model, c.embedding_revision, "
                    "c.embedding_configuration, c.embedding_dimensions, "
                    "c.embedding_space_key, 'team_experience' AS logical_core "
                    "FROM team_experience_chunks AS c "
                    "JOIN knowledge_items AS i "
                    "ON i.id = c.knowledge_item_id AND i.team_id = c.team_id "
                    "JOIN learning_changes AS lc "
                    "ON lc.id = i.origin_learning_change_id AND lc.team_id = i.team_id "
                    "JOIN team_experience_index_state AS st "
                    "ON st.knowledge_item_id = c.knowledge_item_id "
                    "AND st.team_id = c.team_id"
                )
                experience_parameters = {
                    **embedding_parameters,
                    "team_id": team_id,
                    "now_utc": now_utc,
                    "candidate_limit": LEXICAL_CANDIDATE_LIMIT,
                }
                experience_lexical = session.execute(
                    text(
                        f"{experience_projection} WHERE {experience_where} "
                        "AND to_tsvector('simple', c.chunk_text) "
                        "@@ plainto_tsquery('simple', :query) "
                        "ORDER BY ts_rank_cd(to_tsvector('simple', c.chunk_text), "
                        "plainto_tsquery('simple', :query)) DESC, "
                        "c.knowledge_item_id, c.item_version, c.chunk_index, c.id "
                        "LIMIT :candidate_limit"
                    ),
                    experience_parameters,
                ).mappings().all()
                experience_parameters["candidate_limit"] = VECTOR_CANDIDATE_LIMIT
                experience_vector = session.execute(
                    text(
                        f"{experience_projection} WHERE {experience_where} "
                        "ORDER BY c.embedding <=> CAST(:query_vector AS vector), "
                        "c.knowledge_item_id, c.item_version, c.chunk_index, c.id "
                        "LIMIT :candidate_limit"
                    ),
                    experience_parameters,
                ).mappings().all()
                experience_ranked = _rank_candidate_rows(
                    experience_lexical, experience_vector, "team_experience"
                )
                experience_verified = self._verify_experience_candidates(
                    session, experience_ranked, query_batch.space, now_utc
                )

        domain_verified = self._verify_candidates(domain_ranked, query_batch.space)
        combined = domain_verified + experience_verified
        combined.sort(key=_ranked_candidate_sort_key)
        return _bound_passages(combined)


        if not isinstance(query, str) or not query.strip():
            return ()

        # Embedding calls happen outside database transactions. The returned space
        # travels with the vectors, so a model revision can never be silently mixed.
        query_batch = self._embedding_provider.embed([query.strip()])
        if len(query_batch.vectors) != 1:
            raise KnowledgeIndexError("query_embedding_count_mismatch")
        try:
            query_vector = validate_vector(
                query_batch.vectors[0], query_batch.space.dimensions
            )
        except ValueError as error:
            raise KnowledgeIndexError(error.args[0]) from error

        with self._session_factory() as session:
            with session.begin():
                session.connection(
                    execution_options={"isolation_level": "REPEATABLE READ"}
                )
                team = session.get(Team, team_id)
                if team is None or team.status != "active" or not team.domain.strip():
                    return ()
                policy = session.scalar(
                    select(TeamPolicy)
                    .where(TeamPolicy.team_id == team_id)
                    .order_by(TeamPolicy.version.desc())
                    .limit(1)
                )
                if policy is None:
                    return ()
                allowed_sources = self._allowed_sources(policy.rules)
                if not allowed_sources:
                    return ()

                scope_clause, scope_params = _source_predicate(allowed_sources)
                parameters: dict[str, Any] = {
                    **scope_params,
                    "domain": team.domain,
                    "embedding_space_key": query_batch.space.key,
                    "embedding_provider": query_batch.space.provider,
                    "embedding_model": query_batch.space.model,
                    "embedding_revision": query_batch.space.revision,
                    "embedding_configuration": query_batch.space.configuration,
                    "embedding_dimensions": query_batch.space.dimensions,
                    "chunking_version": CHUNKING_VERSION,
                    "candidate_limit": LEXICAL_CANDIDATE_LIMIT,
                    "query": query.strip(),
                    "query_vector": serialize_vector(query_vector),
                }

                base_where = (
                    "c.embedding_space_key = :embedding_space_key "
                    "AND c.embedding_provider = :embedding_provider "
                    "AND c.embedding_model = :embedding_model "
                    "AND c.embedding_revision = :embedding_revision "
                    "AND c.embedding_configuration = :embedding_configuration "
                    "AND c.embedding_dimensions = :embedding_dimensions "
                    "AND c.chunking_version = :chunking_version "
                    "AND s.domain = :domain "
                    "AND c.source_snapshot_ref = s.snapshot_ref "
                    "AND c.source_content_hash = s.content_hash "
                    f"AND {scope_clause}"
                )
                projection = _candidate_select()
                lexical_statement = text(
                    f"{projection} WHERE {base_where} "
                    "AND to_tsvector('simple', c.chunk_text) "
                    "@@ plainto_tsquery('simple', :query) "
                    "ORDER BY ts_rank_cd(to_tsvector('simple', c.chunk_text), "
                    "plainto_tsquery('simple', :query)) DESC, "
                    "c.signal_id, c.chunk_index, c.id "
                    "LIMIT :candidate_limit"
                )
                lexical_rows = session.execute(
                    lexical_statement, parameters
                ).mappings().all()

                parameters["candidate_limit"] = VECTOR_CANDIDATE_LIMIT
                vector_statement = text(
                    f"{projection} WHERE {base_where} "
                    "ORDER BY c.embedding <=> CAST(:query_vector AS vector), "
                    "c.signal_id, c.chunk_index, c.id "
                    "LIMIT :candidate_limit"
                )
                vector_rows = session.execute(
                    vector_statement, parameters
                ).mappings().all()

                candidates: dict[UUID, dict[str, Any]] = {}
                for rank, row in enumerate(lexical_rows, start=1):
                    record = dict(row)
                    candidates[record["chunk_id"]] = {
                        "row": record,
                        "lexical_rank": rank,
                        "vector_rank": None,
                    }
                for rank, row in enumerate(vector_rows, start=1):
                    record = dict(row)
                    existing = candidates.get(record["chunk_id"])
                    if existing is None:
                        candidates[record["chunk_id"]] = {
                            "row": record,
                            "lexical_rank": None,
                            "vector_rank": rank,
                        }
                    else:
                        existing["vector_rank"] = rank

        ranked: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates.values():
            lexical_rank = candidate["lexical_rank"]
            vector_rank = candidate["vector_rank"]
            score = 0.0
            if lexical_rank is not None:
                score += 1.0 / (RECIPROCAL_RANK_FUSION_K + lexical_rank)
            if vector_rank is not None:
                score += 1.0 / (RECIPROCAL_RANK_FUSION_K + vector_rank)
            ranked.append((score, candidate))
        ranked.sort(
            key=lambda item: (
                -item[0],
                str(item[1]["row"]["signal_id"]),
                item[1]["row"]["chunk_index"],
                str(item[1]["row"]["chunk_id"]),
            )
        )

        verified = self._verify_candidates(ranked, query_batch.space)
        return _bound_passages(verified)

    @staticmethod
    def _allowed_sources(rules: Any) -> set[tuple[str, str]]:
        if not isinstance(rules, dict):
            return set()
        entries = rules.get("sources")
        if not isinstance(entries, list):
            return set()
        allowed: set[tuple[str, str]] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            origin_url = entry.get("origin_url")
            source_type = entry.get("source_type")
            if (
                isinstance(origin_url, str)
                and origin_url.strip()
                and isinstance(source_type, str)
                and source_type.strip()
            ):
                allowed.add((origin_url, source_type))
        return allowed

    def _verify_experience_candidates(
        self,
        session: Session,
        ranked: list[tuple[float, dict[str, Any]]],
        query_space: EmbeddingSpace,
        now: datetime,
    ) -> list[tuple[float, dict[str, Any]]]:
        verified: list[tuple[float, dict[str, Any]]] = []
        text_cache: dict[UUID, tuple[str, ...] | None] = {}
        for score, candidate in ranked:
            row = candidate["row"]
            if (
                row["chunking_version"] != CHUNKING_VERSION
                or row["embedding_space_key"] != query_space.key
                or row["chunk_hash"] != text_hash(row["chunk_text"])
            ):
                continue
            try:
                recorded_space = EmbeddingSpace(
                    provider=row["embedding_provider"],
                    model=row["embedding_model"],
                    revision=row["embedding_revision"],
                    dimensions=row["embedding_dimensions"],
                    configuration=row["embedding_configuration"],
                )
            except (TypeError, ValueError):
                continue
            if recorded_space.key != row["embedding_space_key"]:
                continue

            item = session.get(KnowledgeItem, row["knowledge_item_id"])
            if (
                item is None
                or item.team_id != row["team_id"]
                or item.version != row["item_version"]
                or item.origin_learning_change_id != row["origin_learning_change_id"]
                or not _review_date_is_eligible(item, now)
            ):
                continue
            learning_change = session.get(
                LearningChange, item.origin_learning_change_id
            )
            index_state = session.scalar(
                select(TeamExperienceIndexState).where(
                    TeamExperienceIndexState.knowledge_item_id == item.id,
                    TeamExperienceIndexState.team_id == item.team_id,
                )
            )
            if (
                index_state is None
                or index_state.status != "published"
                or index_state.item_version != item.version
                or index_state.item_content_hash != row["item_content_hash"]
                or index_state.origin_learning_change_id
                != item.origin_learning_change_id
                or index_state.embedding_space_key != query_space.key
                or index_state.chunk_count <= row["chunk_index"]
                or learning_change is None
                or not _accepted_learning_change_is_canonical(
                    session, item, learning_change
                )
                or knowledge_item_content_hash(item) != row["item_content_hash"]
            ):
                continue

            if item.id not in text_cache:
                try:
                    text_cache[item.id] = chunk_source_text(
                        knowledge_item_text(item).encode("utf-8")
                    )
                except KnowledgeIndexError:
                    text_cache[item.id] = None
            chunks = text_cache[item.id]
            if chunks is None:
                continue
            index = row["chunk_index"]
            if index < 0 or index >= len(chunks) or chunks[index] != row["chunk_text"]:
                continue

            candidate["score"] = score
            verified.append((score, candidate))
        return verified

    def _verify_candidates(
        self,
        ranked: list[tuple[float, dict[str, Any]]],
        query_space: EmbeddingSpace,
    ) -> list[tuple[float, dict[str, Any]]]:
        snapshot_cache: dict[str, tuple[bytes, tuple[str, ...]] | None] = {}
        verified: list[tuple[float, dict[str, Any]]] = []

        for score, candidate in ranked:
            row = candidate["row"]
            if (
                row["chunking_version"] != CHUNKING_VERSION
                or row["embedding_space_key"] != query_space.key
                or row["chunk_hash"] != text_hash(row["chunk_text"])
            ):
                continue
            try:
                recorded_space = EmbeddingSpace(
                    provider=row["embedding_provider"],
                    model=row["embedding_model"],
                    revision=row["embedding_revision"],
                    dimensions=row["embedding_dimensions"],
                    configuration=row["embedding_configuration"],
                )
            except (TypeError, ValueError):
                continue
            if recorded_space.key != row["embedding_space_key"]:
                continue

            reference = row["source_snapshot_ref"]
            cached = snapshot_cache.get(reference)
            if reference not in snapshot_cache:
                try:
                    raw = self._snapshot_store.read(reference)
                    if content_hash(raw) != row["source_content_hash"]:
                        snapshot_cache[reference] = None
                    else:
                        chunks = chunk_source_text(raw)
                        snapshot_cache[reference] = (raw, chunks)
                except (SnapshotIntegrityError, KnowledgeIndexError):
                    snapshot_cache[reference] = None
                cached = snapshot_cache[reference]
            if cached is None:
                continue
            raw, chunks = cached
            if content_hash(raw) != row["source_content_hash"]:
                continue
            index = row["chunk_index"]
            if index < 0 or index >= len(chunks) or chunks[index] != row["chunk_text"]:
                continue

            candidate["score"] = score
            verified.append((score, candidate))
        return verified


def _candidate_select() -> str:
    return (
        "SELECT c.id AS chunk_id, c.signal_id, c.chunk_index, c.chunk_text, "
        "c.chunk_hash, c.source_snapshot_ref, c.source_content_hash, "
        "c.chunking_version, c.embedding_provider, c.embedding_model, "
        "c.embedding_revision, c.embedding_configuration, "
        "c.embedding_dimensions, c.embedding_space_key, "
        "s.origin_url AS source_url, s.source_type "
        "FROM knowledge_chunks AS c "
        "JOIN signals AS s ON s.id = c.signal_id"
    )


def _rank_candidate_rows(
    lexical_rows: Any,
    vector_rows: Any,
    logical_core: str,
) -> list[tuple[float, dict[str, Any]]]:
    candidates: dict[UUID, dict[str, Any]] = {}
    for rank, row in enumerate(lexical_rows, start=1):
        record = dict(row)
        record["logical_core"] = logical_core
        candidates[record["chunk_id"]] = {
            "row": record,
            "lexical_rank": rank,
            "vector_rank": None,
        }
    for rank, row in enumerate(vector_rows, start=1):
        record = dict(row)
        record["logical_core"] = logical_core
        existing = candidates.get(record["chunk_id"])
        if existing is None:
            candidates[record["chunk_id"]] = {
                "row": record,
                "lexical_rank": None,
                "vector_rank": rank,
            }
        else:
            existing["vector_rank"] = rank

    ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates.values():
        lexical_rank = candidate["lexical_rank"]
        vector_rank = candidate["vector_rank"]
        score = 0.0
        if lexical_rank is not None:
            score += 1.0 / (RECIPROCAL_RANK_FUSION_K + lexical_rank)
        if vector_rank is not None:
            score += 1.0 / (RECIPROCAL_RANK_FUSION_K + vector_rank)
        ranked.append((score, candidate))
    ranked.sort(key=_ranked_candidate_sort_key)
    return ranked


def _ranked_candidate_sort_key(item: tuple[float, dict[str, Any]]) -> tuple[Any, ...]:
    row = item[1]["row"]
    record_id = row.get("signal_id") or row.get("knowledge_item_id")
    return (
        -item[0],
        row.get("logical_core", "domain_knowledge"),
        str(record_id),
        row["chunk_index"],
        str(row["chunk_id"]),
    )


def _source_predicate(
    allowed_sources: set[tuple[str, str]],
) -> tuple[str, dict[str, str]]:
    terms: list[str] = []
    parameters: dict[str, str] = {}
    for index, (origin_url, source_type) in enumerate(sorted(allowed_sources)):
        origin_key = f"allowed_origin_{index}"
        type_key = f"allowed_source_type_{index}"
        terms.append(
            f"(s.origin_url = :{origin_key} AND s.source_type = :{type_key})"
        )
        parameters[origin_key] = origin_url
        parameters[type_key] = source_type
    return "(" + " OR ".join(terms) + ")", parameters


def _bound_passages(
    verified: list[tuple[float, dict[str, Any]]],
) -> tuple[RetrievedPassage, ...]:
    passages: list[RetrievedPassage] = []
    total_characters = 0
    for score, candidate in verified:
        if len(passages) >= MAX_RETRIEVED_PASSAGES:
            break
        row = candidate["row"]
        remaining = MAX_RETRIEVED_CHARACTERS - total_characters
        if remaining <= 0:
            break
        original_text = row["chunk_text"]
        passage_text = original_text[:remaining]
        truncated = len(passage_text) < len(original_text)
        passage_text = passage_text.rstrip()
        if not passage_text:
            break
        passages.append(
            RetrievedPassage(
                signal_id=row.get("signal_id"),
                source_url=row.get("source_url"),
                source_type=row.get("source_type"),
                snapshot_ref=row.get("source_snapshot_ref"),
                content_hash=row.get("source_content_hash")
                or row.get("item_content_hash"),
                chunk_id=row["chunk_id"],
                chunk_index=row["chunk_index"],
                text=passage_text,
                chunk_hash=row["chunk_hash"],
                score=score,
                lexical_rank=candidate["lexical_rank"],
                vector_rank=candidate["vector_rank"],
                embedding_space_key=row["embedding_space_key"],
                embedding_provider=row["embedding_provider"],
                embedding_model=row["embedding_model"],
                embedding_revision=row["embedding_revision"],
                embedding_configuration=row["embedding_configuration"],
                embedding_dimensions=row["embedding_dimensions"],
                truncated=truncated,
                logical_core=row.get("logical_core", "domain_knowledge"),
                knowledge_item_id=row.get("knowledge_item_id"),
                knowledge_item_version=row.get("item_version"),
                origin_learning_change_id=row.get("origin_learning_change_id"),
            )
        )
        total_characters += len(passage_text)
        if truncated:
            break
    return tuple(passages)
