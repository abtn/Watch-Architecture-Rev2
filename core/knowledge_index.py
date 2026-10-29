"""Rebuildable R6-D projection and policy-scoped hybrid retrieval for Signals."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from core.embeddings import EmbeddingBatch, EmbeddingProvider, EmbeddingSpace
from core.models import KnowledgeChunk, Signal, Team, TeamPolicy
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
    signal_id: UUID
    source_url: str
    source_type: str
    snapshot_ref: str
    content_hash: str
    chunk_id: UUID
    chunk_index: int
    text: str
    chunk_hash: str
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    embedding_space_key: str
    truncated: bool = False


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
            # Old vector-space rows must never be used for the current query space.
            # Remove obsolete rows even when the current projection is already valid.
            with self._session_factory.begin() as session:
                session.execute(
                    delete(KnowledgeChunk).where(
                        KnowledgeChunk.signal_id == signal_id,
                        KnowledgeChunk.embedding_space_key != space.key,
                    )
                )
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
            _raw, chunks = cached
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
                signal_id=row["signal_id"],
                source_url=row["source_url"],
                source_type=row["source_type"],
                snapshot_ref=row["source_snapshot_ref"],
                content_hash=row["source_content_hash"],
                chunk_id=row["chunk_id"],
                chunk_index=row["chunk_index"],
                text=passage_text,
                chunk_hash=row["chunk_hash"],
                score=score,
                lexical_rank=candidate["lexical_rank"],
                vector_rank=candidate["vector_rank"],
                embedding_space_key=row["embedding_space_key"],
                truncated=truncated,
            )
        )
        total_characters += len(passage_text)
        if truncated:
            break
    return tuple(passages)
