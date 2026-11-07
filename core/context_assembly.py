"""Bounded, immutable per-Task Context assembly for R6-E Step 1."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.embeddings import EmbeddingSpace
from core.knowledge_index import (
    CHUNK_MAX_CHARACTERS,
    CHUNKING_VERSION,
    LEXICAL_CANDIDATE_LIMIT,
    MAX_RETRIEVED_CHARACTERS,
    MAX_RETRIEVED_PASSAGES,
    RECIPROCAL_RANK_FUSION_K,
    VECTOR_CANDIDATE_LIMIT,
    KnowledgeIndexError,
    RetrievedPassage,
    _accepted_learning_change_is_canonical,
    _review_date_is_eligible,
    chunk_source_text,
    content_hash,
    knowledge_item_committed_state_matches,
    knowledge_item_content_hash,
    knowledge_item_text,
    text_hash,
)
from core.models import (
    Event,
    KnowledgeChunk,
    KnowledgeItem,
    LearningChange,
    Objective,
    Signal,
    Task,
    Team,
    TeamExperienceChunk,
    TeamExperienceIndexState,
    TeamPolicy,
)
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.state_assessment import (
    StateAssessment,
    StateAssessmentBuilder,
    _canonical_json,
)

CONTEXT_SCHEMA_VERSION = "r6e-task-context-v2"
CONTEXT_MANIFEST_VERSION = "r6e-context-manifest-v2"
LEGACY_CONTEXT_MANIFEST_VERSION = "r6e-context-manifest-v1"
RETRIEVAL_CONFIGURATION_VERSION = "postgres-hybrid-rrf-v2"


class TaskContextError(ValueError):
    """Context assembly was rejected or could not preserve its canonical basis."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class KnowledgeRetriever(Protocol):
    """The policy-scoped retrieval boundary used by the assembler."""

    def retrieve(self, team_id: UUID, query: str) -> tuple[RetrievedPassage, ...]:
        """Return current, authorized, canonical Signal passages."""
        ...


@dataclass(frozen=True)
class AssembledTaskContext:
    """An immutable Context artifact and its exact assessment/provenance."""

    task_id: UUID
    snapshot_ref: str
    content_hash: str
    event_id: UUID
    manifest: dict[str, Any]
    document: dict[str, Any]
    assessment: StateAssessment
    replayed: bool = False


@dataclass(frozen=True)
class _TaskContextScope:
    task_id: UUID
    team_id: UUID
    team_domain: str
    objective_id: UUID
    objective_statement: str
    policy_version: int
    policy_rules_json: str
    budget_json: str


class TaskContextAssembler:
    """Assemble one bounded Context and commit only its Task-scoped K effects.

    Retrieval and embedding calls occur outside database transactions. The
    Task is then locked and all mutable scope/policy/canonical Signal references
    are rechecked before the immutable Snapshot and its single manifest Event
    are committed. Replays must reproduce the exact bytes and manifest.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        retriever: KnowledgeRetriever,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._retriever = retriever
        self._assessments = StateAssessmentBuilder(session_factory)

    def assemble(self, task_id: UUID) -> AssembledTaskContext:
        """Assemble the Context for a running Objective-scoped Strategy Task."""
        scope = self._load_scope(task_id)
        prior = self._load_prior_context(scope)
        if prior is not None:
            return prior
        query = scope.objective_statement
        try:
            passages = self._retriever.retrieve(scope.team_id, query)
        except KnowledgeIndexError as error:
            raise TaskContextError(error.reason) from error
        return self._persist(scope, query, passages)

    def _load_prior_context(
        self, scope: _TaskContextScope
    ) -> AssembledTaskContext | None:
        """Replay an immutable Context before doing a new retrieval pass.

        This keeps pre-Checkpoint-4 Contexts stable when the retriever gains a
        second logical core or when the Team Experience projection is rebuilt.
        """
        with self._session_factory() as session:
            events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == scope.task_id,
                        Event.type == "context_assembled",
                    )
                )
            )
            if not events:
                return None
            if len(events) != 1:
                raise TaskContextError("duplicate_context_assembled_events")
            event = events[0]
            payload = event.payload
            if not isinstance(payload, dict):
                raise TaskContextError("context_manifest_corrupt")
            schema_version = payload.get("schema_version")
            if schema_version not in {
                CONTEXT_MANIFEST_VERSION,
                LEGACY_CONTEXT_MANIFEST_VERSION,
            }:
                raise TaskContextError("context_manifest_version_unsupported")
            reference = payload.get("snapshot_ref")
            recorded_hash = payload.get("content_hash")
            manifest = payload.get("manifest")
            if not isinstance(reference, str) or not isinstance(manifest, dict):
                raise TaskContextError("context_manifest_corrupt")
            try:
                stored_bytes = self._snapshot_store.read(reference)
            except SnapshotIntegrityError as error:
                raise TaskContextError("context_snapshot_integrity_failure") from error
            actual_hash = content_hash(stored_bytes)
            digest = actual_hash.removeprefix("sha256:")
            if (
                recorded_hash != actual_hash
                or reference != f"snap://sha256/{digest}"
                or payload
                != {
                    "schema_version": schema_version,
                    "snapshot_ref": reference,
                    "content_hash": actual_hash,
                    "manifest": manifest,
                }
            ):
                raise TaskContextError("context_snapshot_integrity_failure")
            try:
                document = json.loads(stored_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise TaskContextError("context_snapshot_integrity_failure") from error
            if (
                not isinstance(document, dict)
                or document.get("manifest") != manifest
                or manifest.get("task_id") != str(scope.task_id)
                or manifest.get("team_id") != str(scope.team_id)
                or manifest.get("policy_version") != scope.policy_version
            ):
                raise TaskContextError("context_manifest_corrupt")
            assembled_at = manifest.get("assembled_at")
            if not isinstance(assembled_at, str):
                raise TaskContextError("context_manifest_corrupt")
            try:
                assessment_time = datetime.fromisoformat(
                    assembled_at.replace("Z", "+00:00")
                )
            except ValueError as error:
                raise TaskContextError("context_manifest_corrupt") from error
            if (
                assessment_time.tzinfo is None
                or assessment_time.utcoffset() is None
            ):
                raise TaskContextError("context_manifest_corrupt")
            current_scope = self._scope_in_session(
                session, scope.task_id, lock=False
            )
            if current_scope != scope:
                raise TaskContextError("task_context_scope_changed")
            assessment = self._assessments.build_in_session(
                session,
                scope.objective_id,
                created_at=assessment_time,
            )
            expected_assessment = json.loads(
                json.dumps(asdict(assessment), default=str, allow_nan=False)
            )
            if document.get("assessment") != expected_assessment:
                raise TaskContextError("context_replay_conflict")
            return AssembledTaskContext(
                task_id=scope.task_id,
                snapshot_ref=reference,
                content_hash=actual_hash,
                event_id=event.id,
                manifest=manifest,
                document=document,
                assessment=assessment,
                replayed=True,
            )

    def verify_snapshot(self, context: AssembledTaskContext) -> None:
        """Re-read and verify the exact immutable bytes passed to a proposer."""
        try:
            stored_bytes = self._snapshot_store.read(context.snapshot_ref)
        except SnapshotIntegrityError as error:
            raise TaskContextError("context_snapshot_integrity_failure") from error
        expected_bytes = _canonical_json(context.document).encode("utf-8")
        expected_hash = content_hash(expected_bytes)
        digest = expected_hash.removeprefix("sha256:")
        if (
            stored_bytes != expected_bytes
            or context.content_hash != expected_hash
            or context.snapshot_ref != f"snap://sha256/{digest}"
        ):
            raise TaskContextError("context_snapshot_integrity_failure")

    def _load_scope(self, task_id: UUID) -> _TaskContextScope:
        with self._session_factory() as session:
            return self._scope_in_session(session, task_id, lock=False)

    def _persist(
        self,
        expected_scope: _TaskContextScope,
        query: str,
        passages: tuple[RetrievedPassage, ...],
    ) -> AssembledTaskContext:
        with self._session_factory.begin() as session:
            # PostgreSQL READ COMMITTED is intentional here. The Task lock is
            # acquired before the existing-manifest query, so a waiter sees a
            # prior assembler's committed Event in its next statement snapshot.
            # StrategyService later revalidates the assessment basis before K writes.
            # The Task row is the serialization point for duplicate assemblers.
            current_scope = self._scope_in_session(
                session, expected_scope.task_id, lock=True
            )
            if current_scope != expected_scope:
                raise TaskContextError("task_context_scope_changed")

            self._validate_passages(session, current_scope, passages)
            prior_events = list(
                session.scalars(
                    select(Event)
                    .where(
                        Event.task_id == current_scope.task_id,
                        Event.type == "context_assembled",
                    )
                    .order_by(Event.created_at, Event.id)
                )
            )
            if len(prior_events) > 1:
                raise TaskContextError("duplicate_context_assembled_events")

            if prior_events:
                prior_manifest = prior_events[0].payload.get("manifest")
                if not isinstance(prior_manifest, dict):
                    raise TaskContextError("context_manifest_corrupt")
                assembled_at = prior_manifest.get("assembled_at")
                if not isinstance(assembled_at, str):
                    raise TaskContextError("context_manifest_corrupt")
                try:
                    assessment_time = datetime.fromisoformat(
                        assembled_at.replace("Z", "+00:00")
                    )
                except ValueError as error:
                    raise TaskContextError("context_manifest_corrupt") from error
                if (
                    assessment_time.tzinfo is None
                    or assessment_time.utcoffset() is None
                ):
                    raise TaskContextError("context_manifest_corrupt")
            else:
                assessment_time = datetime.now(timezone.utc)

            assessment = self._assessments.build_in_session(
                session,
                current_scope.objective_id,
                created_at=assessment_time,
            )
            manifest = self._manifest(
                current_scope, query, passages, assessment
            )
            document = self._document(
                current_scope, passages, assessment, manifest
            )
            snapshot_bytes = _canonical_json(document).encode("utf-8")
            expected_content_hash = content_hash(snapshot_bytes)

            if prior_events:
                event = prior_events[0]
                reference = event.payload.get("snapshot_ref")
                recorded_hash = event.payload.get("content_hash")
                expected_event_payload = {
                    "schema_version": CONTEXT_MANIFEST_VERSION,
                    "snapshot_ref": reference,
                    "content_hash": expected_content_hash,
                    "manifest": manifest,
                }
                if (
                    not isinstance(reference, str)
                    or recorded_hash != expected_content_hash
                    or event.payload != expected_event_payload
                ):
                    raise TaskContextError("context_replay_conflict")
                try:
                    stored_bytes = self._snapshot_store.read(reference)
                except SnapshotIntegrityError as error:
                    raise TaskContextError(
                        "context_snapshot_integrity_failure"
                    ) from error
                if stored_bytes != snapshot_bytes:
                    raise TaskContextError("context_replay_conflict")
                snapshot_ref = reference
                stored_hash = recorded_hash
                event_id = event.id
                replayed = True
            else:
                snapshot_ref, stored_hash = self._snapshot_store.put(snapshot_bytes)
                event = Event(
                    id=uuid4(),
                    task_id=current_scope.task_id,
                    type="context_assembled",
                    payload={
                        "schema_version": CONTEXT_MANIFEST_VERSION,
                        "snapshot_ref": snapshot_ref,
                        "content_hash": stored_hash,
                        "manifest": manifest,
                    },
                    created_at=assessment_time,
                )
                session.add(event)
                session.flush()
                event_id = event.id
                replayed = False

            return AssembledTaskContext(
                task_id=current_scope.task_id,
                snapshot_ref=snapshot_ref,
                content_hash=stored_hash,
                event_id=event_id,
                manifest=manifest,
                document=document,
                assessment=assessment,
                replayed=replayed,
            )

    @staticmethod
    def _scope_in_session(
        session: Session, task_id: UUID, *, lock: bool
    ) -> _TaskContextScope:
        task_query = select(Task).where(Task.id == task_id)
        if lock:
            task_query = task_query.with_for_update()
        task = session.scalar(task_query)
        if task is None:
            raise TaskContextError("task_not_found")
        if task.task_type != "propose_strategy":
            raise TaskContextError("unsupported_task_type")
        if task.status != "running":
            raise TaskContextError("task_not_running")
        if task.allowed_writes != []:
            raise TaskContextError("task_write_scope_violation")
        if not isinstance(task.budget, dict):
            raise TaskContextError("invalid_task_budget")
        TaskContextAssembler._validate_budget(task.budget)
        if task.objective_id is None:
            raise TaskContextError("objective_required")

        team_query = select(Team).where(Team.id == task.team_id)
        objective_query = select(Objective).where(
            Objective.id == task.objective_id
        )
        policy_query = (
            select(TeamPolicy)
            .where(TeamPolicy.team_id == task.team_id)
            .order_by(TeamPolicy.version.desc())
            .limit(1)
        )
        if lock:
            # FOR UPDATE conflicts with the FK key-share lock used by a new
            # TeamPolicy row, preventing a newer policy from being published
            # between the current-policy check and the Context manifest commit.
            team_query = team_query.with_for_update()
            objective_query = objective_query.with_for_update(read=True)
            policy_query = policy_query.with_for_update(read=True)

        team = session.scalar(team_query)
        objective = session.scalar(objective_query)
        policy = session.scalar(policy_query)
        if team is None or team.status != "active" or not team.domain.strip():
            raise TaskContextError("team_not_active")
        if (
            objective is None
            or objective.team_id != task.team_id
            or objective.status != "active"
            or not objective.statement.strip()
        ):
            raise TaskContextError("objective_not_active")
        if policy is None:
            raise TaskContextError("team_policy_missing")
        if policy.version != task.policy_version:
            raise TaskContextError("task_policy_not_current")

        return _TaskContextScope(
            task_id=task.id,
            team_id=task.team_id,
            team_domain=team.domain,
            objective_id=objective.id,
            objective_statement=objective.statement,
            policy_version=task.policy_version,
            policy_rules_json=_canonical_json(policy.rules),
            budget_json=_canonical_json(task.budget),
        )

    @staticmethod
    def _validate_budget(budget: dict[str, Any]) -> None:
        max_tool_calls = budget.get("max_tool_calls")
        max_cost_usd = budget.get("max_cost_usd")
        deadline_seconds = budget.get("deadline_seconds")
        if (
            isinstance(max_tool_calls, bool)
            or not isinstance(max_tool_calls, int)
            or max_tool_calls < 0
        ):
            raise TaskContextError("invalid_task_budget")
        if (
            isinstance(max_cost_usd, bool)
            or not isinstance(max_cost_usd, (int, float))
            or not math.isfinite(float(max_cost_usd))
            or max_cost_usd < 0
        ):
            raise TaskContextError("invalid_task_budget")
        if (
            isinstance(deadline_seconds, bool)
            or not isinstance(deadline_seconds, int)
            or deadline_seconds < 1
        ):
            raise TaskContextError("invalid_task_budget")

    def _validate_passages(
        self,
        session: Session,
        scope: _TaskContextScope,
        passages: tuple[RetrievedPassage, ...],
    ) -> None:
        if len(passages) > MAX_RETRIEVED_PASSAGES:
            raise TaskContextError("retrieval_passage_limit_exceeded")
        if len({passage.chunk_id for passage in passages}) != len(passages):
            raise TaskContextError("duplicate_retrieval_chunk")
        if sum(len(passage.text) for passage in passages) > MAX_RETRIEVED_CHARACTERS:
            raise TaskContextError("retrieval_character_limit_exceeded")

        rules = json.loads(scope.policy_rules_json)
        if not isinstance(rules, dict):
            raise TaskContextError("invalid_team_policy")
        configured_sources = rules.get("sources", [])
        allowed_sources: set[tuple[str, str]] = set()
        if isinstance(configured_sources, list):
            for entry in configured_sources:
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
                    allowed_sources.add((origin_url, source_type))

        snapshot_cache: dict[str, tuple[bytes, tuple[str, ...]]] = {}
        for passage in passages:
            if (
                not passage.text
                or len(passage.text) > CHUNK_MAX_CHARACTERS
                or not math.isfinite(passage.score)
                or passage.score < 0
            ):
                raise TaskContextError("invalid_retrieval_passage")
            if (
                passage.embedding_dimensions <= 0
                or not passage.embedding_provider
                or not passage.embedding_model
                or not passage.embedding_revision
                or not passage.embedding_configuration
            ):
                raise TaskContextError("invalid_embedding_identity")
            try:
                embedding_space = EmbeddingSpace(
                    provider=passage.embedding_provider,
                    model=passage.embedding_model,
                    revision=passage.embedding_revision,
                    dimensions=passage.embedding_dimensions,
                    configuration=passage.embedding_configuration,
                )
            except ValueError as error:
                raise TaskContextError("invalid_embedding_identity") from error
            if embedding_space.key != passage.embedding_space_key:
                raise TaskContextError("embedding_identity_mismatch")

            if passage.logical_core == "team_experience":
                self._validate_team_experience_passage(
                    session, scope, passage, datetime.now(timezone.utc)
                )
                continue
            if (
                passage.logical_core != "domain_knowledge"
                or passage.signal_id is None
                or passage.knowledge_item_id is not None
                or passage.knowledge_item_version is not None
                or passage.origin_learning_change_id is not None
            ):
                raise TaskContextError("invalid_retrieval_logical_core")

            signal = session.get(Signal, passage.signal_id)
            if (
                signal is None
                or signal.domain != scope.team_domain
                or signal.origin_url != passage.source_url
                or signal.source_type != passage.source_type
                or signal.snapshot_ref != passage.snapshot_ref
                or signal.content_hash != passage.content_hash
            ):
                raise TaskContextError("retrieval_candidate_not_current")
            if (signal.origin_url, signal.source_type) not in allowed_sources:
                raise TaskContextError("retrieval_candidate_not_authorized")

            cached = snapshot_cache.get(signal.snapshot_ref)
            if cached is None:
                try:
                    raw = self._snapshot_store.read(signal.snapshot_ref)
                    if content_hash(raw) != signal.content_hash:
                        raise TaskContextError("source_snapshot_hash_mismatch")
                    chunks = chunk_source_text(raw)
                except (SnapshotIntegrityError, KnowledgeIndexError) as error:
                    raise TaskContextError(
                        "source_snapshot_integrity_failure"
                    ) from error
                cached = (raw, chunks)
                snapshot_cache[signal.snapshot_ref] = cached

            _, chunks = cached
            if (
                passage.chunk_index < 0
                or passage.chunk_index >= len(chunks)
                or text_hash(chunks[passage.chunk_index]) != passage.chunk_hash
            ):
                raise TaskContextError("retrieval_chunk_not_current")
            expected_text = chunks[passage.chunk_index]
            if passage.truncated:
                if not expected_text.startswith(passage.text):
                    raise TaskContextError("retrieval_chunk_not_current")
            elif expected_text != passage.text:
                raise TaskContextError("retrieval_chunk_not_current")

            # The index is a projection, but the manifest must still identify
            # the exact projection row returned by retrieval. Reject a row that
            # was replaced or reconfigured between retrieval and persistence.
            chunk = session.get(KnowledgeChunk, passage.chunk_id)
            if (
                chunk is None
                or chunk.signal_id != signal.id
                or chunk.chunk_index != passage.chunk_index
                or chunk.chunk_text != expected_text
                or chunk.chunk_hash != passage.chunk_hash
                or chunk.source_snapshot_ref != signal.snapshot_ref
                or chunk.source_content_hash != signal.content_hash
                or chunk.chunking_version != CHUNKING_VERSION
                or chunk.embedding_provider != passage.embedding_provider
                or chunk.embedding_model != passage.embedding_model
                or chunk.embedding_revision != passage.embedding_revision
                or chunk.embedding_configuration
                != passage.embedding_configuration
                or chunk.embedding_dimensions != passage.embedding_dimensions
                or chunk.embedding_space_key != passage.embedding_space_key
                or len(chunk.embedding) != passage.embedding_dimensions
            ):
                raise TaskContextError(
                    "retrieval_chunk_projection_not_current"
                )

    @staticmethod
    def _validate_team_experience_passage(
        session: Session,
        scope: _TaskContextScope,
        passage: RetrievedPassage,
        now_utc: datetime,
    ) -> None:
        if (
            passage.signal_id is not None
            or passage.source_url is not None
            or passage.source_type is not None
            or passage.snapshot_ref is not None
            or passage.knowledge_item_id is None
            or passage.knowledge_item_version is None
            or passage.origin_learning_change_id is None
        ):
            raise TaskContextError("invalid_team_experience_provenance")

        item = session.get(KnowledgeItem, passage.knowledge_item_id)
        if (
            item is None
            or item.team_id != scope.team_id
            or item.version != passage.knowledge_item_version
            or item.origin_learning_change_id != passage.origin_learning_change_id
            or not _review_date_is_eligible(item, now_utc)
        ):
            raise TaskContextError("team_experience_item_not_current_or_eligible")
        learning_change = session.get(
            LearningChange, item.current_learning_change_id
        )
        if (
            learning_change is None
            or not _accepted_learning_change_is_canonical(
                session, item, learning_change
            )
            or not knowledge_item_committed_state_matches(item, learning_change)
        ):
            raise TaskContextError("team_experience_canonical_state_invalid")
        current_hash = knowledge_item_content_hash(item)
        if passage.content_hash != current_hash:
            raise TaskContextError("team_experience_content_hash_mismatch")

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
            or index_state.item_content_hash != current_hash
            or index_state.origin_learning_change_id
            != item.origin_learning_change_id
            or index_state.embedding_space_key != passage.embedding_space_key
            or index_state.chunk_count <= passage.chunk_index
        ):
            raise TaskContextError("team_experience_index_not_published")

        try:
            chunks = chunk_source_text(
                knowledge_item_text(item).encode("utf-8")
            )
        except KnowledgeIndexError as error:
            raise TaskContextError("team_experience_text_invalid") from error
        if (
            passage.chunk_index < 0
            or passage.chunk_index >= len(chunks)
            or text_hash(chunks[passage.chunk_index]) != passage.chunk_hash
        ):
            raise TaskContextError("team_experience_chunk_not_current")
        expected_text = chunks[passage.chunk_index]
        if passage.truncated:
            if not expected_text.startswith(passage.text):
                raise TaskContextError("team_experience_chunk_not_current")
        elif expected_text != passage.text:
            raise TaskContextError("team_experience_chunk_not_current")

        chunk = session.get(TeamExperienceChunk, passage.chunk_id)
        if (
            chunk is None
            or chunk.knowledge_item_id != item.id
            or chunk.team_id != item.team_id
            or chunk.item_version != item.version
            or chunk.item_content_hash != current_hash
            or chunk.origin_learning_change_id != item.origin_learning_change_id
            or chunk.chunk_index != passage.chunk_index
            or chunk.chunk_text != expected_text
            or chunk.chunk_hash != passage.chunk_hash
            or chunk.chunking_version != CHUNKING_VERSION
            or chunk.embedding_provider != passage.embedding_provider
            or chunk.embedding_model != passage.embedding_model
            or chunk.embedding_revision != passage.embedding_revision
            or chunk.embedding_configuration != passage.embedding_configuration
            or chunk.embedding_dimensions != passage.embedding_dimensions
            or chunk.embedding_space_key != passage.embedding_space_key
            or len(chunk.embedding) != passage.embedding_dimensions
        ):
            raise TaskContextError("team_experience_projection_not_current")

    @staticmethod
    def _manifest(
        scope: _TaskContextScope,
        query: str,
        passages: tuple[RetrievedPassage, ...],
        assessment: StateAssessment,
    ) -> dict[str, Any]:
        spaces_by_key: dict[str, dict[str, Any]] = {}
        selected: list[dict[str, Any]] = []
        for rank, passage in enumerate(passages, start=1):
            identity = {
                "provider": passage.embedding_provider,
                "model": passage.embedding_model,
                "revision": passage.embedding_revision,
                "configuration": passage.embedding_configuration,
                "dimensions": passage.embedding_dimensions,
                "key": passage.embedding_space_key,
            }
            spaces_by_key[passage.embedding_space_key] = identity
            selected_entry: dict[str, Any] = {
                "rank": rank,
                "logical_core": passage.logical_core,
                "record_kind": (
                    "signal"
                    if passage.logical_core == "domain_knowledge"
                    else "knowledge_item"
                ),
                "chunk_id": str(passage.chunk_id),
                "chunk_index": passage.chunk_index,
                "chunk_hash": passage.chunk_hash,
                "score": passage.score,
                "lexical_rank": passage.lexical_rank,
                "vector_rank": passage.vector_rank,
                "truncated": passage.truncated,
                "embedding_space_key": passage.embedding_space_key,
            }
            if passage.logical_core == "domain_knowledge":
                selected_entry.update(
                    {
                        "signal_id": str(passage.signal_id),
                        "source_url": passage.source_url,
                        "source_type": passage.source_type,
                        "source_snapshot_ref": passage.snapshot_ref,
                        "source_content_hash": passage.content_hash,
                    }
                )
            else:
                selected_entry.update(
                    {
                        "knowledge_item_id": str(passage.knowledge_item_id),
                        "knowledge_item_version": passage.knowledge_item_version,
                        "knowledge_item_content_hash": passage.content_hash,
                        "origin_learning_change_id": str(
                            passage.origin_learning_change_id
                        ),
                    }
                )
            selected.append(selected_entry)
        logical_cores = sorted({passage.logical_core for passage in passages})
        return {
            "schema_version": CONTEXT_MANIFEST_VERSION,
            "task_id": str(scope.task_id),
            "team_id": str(scope.team_id),
            "objective_id": str(scope.objective_id),
            "policy_version": scope.policy_version,
            "logical_core": (
                logical_cores[0]
                if len(logical_cores) == 1
                else "mixed" if logical_cores else "none"
            ),
            "logical_cores": logical_cores,
            "query_hash": content_hash(query.encode("utf-8")),
            "assessment_basis_sha256": assessment.basis.sha256,
            "assembled_at": assessment.created_at,
            "retrieval": {
                "configuration_version": RETRIEVAL_CONFIGURATION_VERSION,
                "strategy": "postgres_full_text_and_pgvector_rrf",
                "chunking_version": CHUNKING_VERSION,
                "lexical_candidate_limit": LEXICAL_CANDIDATE_LIMIT,
                "vector_candidate_limit": VECTOR_CANDIDATE_LIMIT,
                "rrf_k": RECIPROCAL_RANK_FUSION_K,
                "maximum_passages": MAX_RETRIEVED_PASSAGES,
                "maximum_characters": MAX_RETRIEVED_CHARACTERS,
            },
            "embedding_spaces": [
                spaces_by_key[key] for key in sorted(spaces_by_key)
            ],
            "selected": selected,
        }

    @staticmethod
    def _document(
        scope: _TaskContextScope,
        passages: tuple[RetrievedPassage, ...],
        assessment: StateAssessment,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "task": {
                "id": str(scope.task_id),
                "team_id": str(scope.team_id),
                "task_type": "propose_strategy",
                "objective_id": str(scope.objective_id),
                "policy_version": scope.policy_version,
                "budget": json.loads(scope.budget_json),
            },
            "team": {
                "id": str(scope.team_id),
                "domain": scope.team_domain,
            },
            "objective": {
                "id": str(scope.objective_id),
                "statement": scope.objective_statement,
            },
            "policy": {
                "version": scope.policy_version,
                "rules": json.loads(scope.policy_rules_json),
            },
            "assessment": json.loads(
                json.dumps(asdict(assessment), default=str, allow_nan=False)
            ),
            "knowledge": {
                "domain_knowledge": [
                    {
                        "signal_id": str(passage.signal_id),
                        "source_url": passage.source_url,
                        "source_type": passage.source_type,
                        "snapshot_ref": passage.snapshot_ref,
                        "content_hash": passage.content_hash,
                        "chunk_id": str(passage.chunk_id),
                        "chunk_index": passage.chunk_index,
                        "chunk_hash": passage.chunk_hash,
                        "text": passage.text,
                        "score": passage.score,
                    }
                    for passage in passages
                    if passage.logical_core == "domain_knowledge"
                ],
                "team_experience": [
                    {
                        "knowledge_item_id": str(passage.knowledge_item_id),
                        "knowledge_item_version": passage.knowledge_item_version,
                        "content_hash": passage.content_hash,
                        "origin_learning_change_id": str(
                            passage.origin_learning_change_id
                        ),
                        "chunk_id": str(passage.chunk_id),
                        "chunk_index": passage.chunk_index,
                        "chunk_hash": passage.chunk_hash,
                        "text": passage.text,
                        "score": passage.score,
                    }
                    for passage in passages
                    if passage.logical_core == "team_experience"
                ],
            },
            "manifest": manifest,
        }
