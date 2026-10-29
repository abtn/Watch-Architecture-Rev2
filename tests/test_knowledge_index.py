from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.embeddings import EmbeddingBatch, EmbeddingSpace
from core.knowledge_index import (
    CHUNK_MAX_CHARACTERS,
    CHUNK_OVERLAP_CHARACTERS,
    CHUNK_STEP_CHARACTERS,
    HybridKnowledgeRetriever,
    KnowledgeIndexError,
    SignalIndexer,
    chunk_source_text,
    normalize_source_text,
)
from core.models import KnowledgeChunk, Signal, Team, TeamPolicy
from core.snapshot_store import SnapshotStore


class FakeEmbeddingProvider:
    def __init__(self, revision: str = "digest-1", dimensions: int = 4) -> None:
        self.revision = revision
        self.dimensions = dimensions
        self.embed_calls = 0
        self.fail = False

    def current_space(self) -> EmbeddingSpace:
        return EmbeddingSpace(
            provider="test-fake",
            model="deterministic-test",
            revision=self.revision,
            dimensions=self.dimensions,
            configuration="test-embedding-v1",
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.embed_calls += 1
        if self.fail:
            raise RuntimeError("fake_embedding_failure")
        vectors: list[tuple[float, ...]] = []
        for text_value in texts:
            normalized = text_value.casefold()
            if "alpha" in normalized:
                vector = [1.0, 0.1, 0.1, 0.1]
            elif "beta" in normalized:
                vector = [0.1, 1.0, 0.1, 0.1]
            elif "gamma" in normalized:
                vector = [0.1, 0.1, 1.0, 0.1]
            else:
                vector = [0.5, 0.5, 0.5, 0.5]
            vectors.append(tuple(vector[: self.dimensions]))
        return EmbeddingBatch(space=self.current_space(), vectors=tuple(vectors))


@dataclass
class KnowledgeTestEnv:
    session_factory: sessionmaker[Session]
    snapshot_store: SnapshotStore
    team_ids: list[UUID] = field(default_factory=list)
    policy_ids: list[UUID] = field(default_factory=list)
    signal_ids: list[UUID] = field(default_factory=list)

    def add_team(
        self, domain: str, allowed_sources: list[dict[str, str]]
    ) -> UUID:
        team_id = uuid4()
        policy_id = uuid4()
        with self.session_factory.begin() as session:
            session.add(Team(id=team_id, domain=domain, status="active"))
            session.flush()
            session.add(
                TeamPolicy(
                    id=policy_id,
                    team_id=team_id,
                    version=1,
                    rules={"sources": allowed_sources},
                )
            )
        self.team_ids.append(team_id)
        self.policy_ids.append(policy_id)
        return team_id

    def add_policy(
        self, team_id: UUID, version: int, sources: list[dict[str, str]]
    ) -> None:
        policy_id = uuid4()
        with self.session_factory.begin() as session:
            session.add(
                TeamPolicy(
                    id=policy_id,
                    team_id=team_id,
                    version=version,
                    rules={"sources": sources},
                )
            )
        self.policy_ids.append(policy_id)

    def add_signal(
        self,
        domain: str,
        source_type: str,
        origin_url: str,
        content: bytes,
    ) -> UUID:
        snapshot_ref, stored_hash = self.snapshot_store.put(content)
        signal_id = uuid4()
        with self.session_factory.begin() as session:
            session.add(
                Signal(
                    id=signal_id,
                    domain=domain,
                    source_type=source_type,
                    origin_url=origin_url,
                    fetched_at=datetime.now(timezone.utc),
                    content_hash=stored_hash,
                    snapshot_ref=snapshot_ref,
                )
            )
        self.signal_ids.append(signal_id)
        return signal_id

    def cleanup(self) -> None:
        with self.session_factory.begin() as session:
            if self.signal_ids:
                session.execute(
                    delete(KnowledgeChunk).where(
                        KnowledgeChunk.signal_id.in_(self.signal_ids)
                    )
                )
                session.execute(delete(Signal).where(Signal.id.in_(self.signal_ids)))
            if self.policy_ids:
                session.execute(
                    delete(TeamPolicy).where(TeamPolicy.id.in_(self.policy_ids))
                )
            if self.team_ids:
                session.execute(delete(Team).where(Team.id.in_(self.team_ids)))


@pytest.fixture
def knowledge_env(
    session_factory: sessionmaker[Session], snapshot_store: SnapshotStore
) -> KnowledgeTestEnv:
    env = KnowledgeTestEnv(session_factory, snapshot_store)
    try:
        yield env
    finally:
        env.cleanup()


def _source(url: str, source_type: str = "test_feed") -> dict[str, str]:
    return {"origin_url": url, "source_type": source_type}


def _chunk_count(session_factory: sessionmaker[Session], signal_id: UUID) -> int:
    with session_factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.signal_id == signal_id)
            )
            or 0
        )


def test_chunking_uses_the_declared_maximum_and_overlap() -> None:
    chunks = chunk_source_text(("alpha " * 300).encode())

    assert chunks
    assert all(0 < len(chunk) <= CHUNK_MAX_CHARACTERS for chunk in chunks)
    assert CHUNK_STEP_CHARACTERS == CHUNK_MAX_CHARACTERS - CHUNK_OVERLAP_CHARACTERS
    assert chunks[0][-CHUNK_OVERLAP_CHARACTERS:] == chunks[1][:CHUNK_OVERLAP_CHARACTERS]


def test_html_text_excludes_script_and_normalizes_whitespace() -> None:
    result = normalize_source_text(
        b"<html><body><p>Alpha  evidence</p><script>secret()</script></body></html>"
    )

    assert result == "Alpha evidence"
    assert "secret" not in result


def test_indexing_is_idempotent_and_avoids_repeat_embedding(
    knowledge_env: KnowledgeTestEnv,
) -> None:
    url = "https://example.test/alpha"
    team_id = knowledge_env.add_team("science", [_source(url)])
    signal_id = knowledge_env.add_signal(
        "science", "test_feed", url, b"Alpha finding from the first report."
    )
    provider = FakeEmbeddingProvider()
    indexer = SignalIndexer(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )

    first = indexer.index_signal(signal_id)
    calls_after_first = provider.embed_calls
    second = indexer.index_signal(signal_id)

    assert first.outcome == "indexed"
    assert second.outcome == "unchanged"
    assert first.chunk_count == 1
    assert provider.embed_calls == calls_after_first == 1
    assert _chunk_count(knowledge_env.session_factory, signal_id) == 1
    assert team_id in knowledge_env.team_ids


def test_retrieval_applies_current_source_allowlist(
    knowledge_env: KnowledgeTestEnv,
) -> None:
    allowed_url = "https://example.test/allowed"
    denied_url = "https://example.test/denied"
    team_id = knowledge_env.add_team("science", [_source(allowed_url)])
    allowed_signal = knowledge_env.add_signal(
        "science",
        "test_feed",
        allowed_url,
        b"Alpha evidence from an authorized source.",
    )
    denied_signal = knowledge_env.add_signal(
        "science", "test_feed", denied_url, b"Alpha evidence from a denied source."
    )
    provider = FakeEmbeddingProvider()
    indexer = SignalIndexer(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )
    indexer.index_signal(allowed_signal)
    indexer.index_signal(denied_signal)
    retriever = HybridKnowledgeRetriever(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )

    passages = retriever.retrieve(team_id, "alpha evidence")

    assert passages
    assert {passage.signal_id for passage in passages} == {allowed_signal}
    assert all(passage.source_url == allowed_url for passage in passages)

    knowledge_env.add_policy(team_id, 2, [])
    assert retriever.retrieve(team_id, "alpha evidence") == ()


def test_retrieval_is_domain_scoped_even_if_both_sources_are_allowed(
    knowledge_env: KnowledgeTestEnv,
) -> None:
    same_domain_url = "https://example.test/science"
    other_domain_url = "https://example.test/politics"
    team_id = knowledge_env.add_team(
        "science", [_source(same_domain_url), _source(other_domain_url)]
    )
    science_signal = knowledge_env.add_signal(
        "science", "test_feed", same_domain_url, b"Alpha scientific evidence."
    )
    other_signal = knowledge_env.add_signal(
        "politics", "test_feed", other_domain_url, b"Alpha political evidence."
    )
    provider = FakeEmbeddingProvider()
    indexer = SignalIndexer(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )
    indexer.index_signal(science_signal)
    indexer.index_signal(other_signal)
    retriever = HybridKnowledgeRetriever(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )

    passages = retriever.retrieve(team_id, "alpha")

    assert passages
    assert {passage.signal_id for passage in passages} == {science_signal}


def test_model_revision_rebuilds_projection_without_mixing_vectors(
    knowledge_env: KnowledgeTestEnv,
) -> None:
    url = "https://example.test/revision"
    knowledge_env.add_team("science", [_source(url)])
    signal_id = knowledge_env.add_signal(
        "science", "test_feed", url, b"Alpha source content."
    )
    provider = FakeEmbeddingProvider()
    indexer = SignalIndexer(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )
    indexer.index_signal(signal_id)
    old_key = provider.current_space().key

    provider.revision = "digest-2"
    provider.fail = True
    with pytest.raises(RuntimeError, match="fake_embedding_failure"):
        indexer.index_signal(signal_id)
    with knowledge_env.session_factory() as session:
        old_keys = set(
            session.scalars(
                select(KnowledgeChunk.embedding_space_key).where(
                    KnowledgeChunk.signal_id == signal_id
                )
            ).all()
        )
    assert old_keys == {old_key}

    provider.fail = False
    result = indexer.index_signal(signal_id)
    with knowledge_env.session_factory() as session:
        current_keys = set(
            session.scalars(
                select(KnowledgeChunk.embedding_space_key).where(
                    KnowledgeChunk.signal_id == signal_id
                )
            ).all()
        )
    assert result.outcome == "indexed"
    assert current_keys == {provider.current_space().key}
    assert old_key not in current_keys


def test_indexer_fails_closed_when_snapshot_hash_disagrees_with_signal(
    knowledge_env: KnowledgeTestEnv,
) -> None:
    url = "https://example.test/corrupt-hash"
    knowledge_env.add_team("science", [_source(url)])
    signal_id = knowledge_env.add_signal(
        "science", "test_feed", url, b"Alpha source content."
    )
    with knowledge_env.session_factory.begin() as session:
        signal = session.get(Signal, signal_id)
        assert signal is not None
        signal.content_hash = "sha256:" + ("0" * 64)
    provider = FakeEmbeddingProvider()
    indexer = SignalIndexer(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )

    with pytest.raises(KnowledgeIndexError, match="signal_snapshot_hash_mismatch"):
        indexer.index_signal(signal_id)
    assert provider.embed_calls == 0
    assert _chunk_count(knowledge_env.session_factory, signal_id) == 0


def test_retrieval_obeys_passage_and_character_bounds(
    knowledge_env: KnowledgeTestEnv,
) -> None:
    url = "https://example.test/long-report"
    team_id = knowledge_env.add_team("science", [_source(url)])
    content = (
        "Alpha evidence discusses a repeatable scientific result. " * 300
    ).encode()
    signal_id = knowledge_env.add_signal("science", "test_feed", url, content)
    provider = FakeEmbeddingProvider()
    indexer = SignalIndexer(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )
    indexer.index_signal(signal_id)
    retriever = HybridKnowledgeRetriever(
        knowledge_env.session_factory, knowledge_env.snapshot_store, provider
    )

    passages = retriever.retrieve(team_id, "alpha evidence")

    assert 0 < len(passages) <= 8
    assert sum(len(passage.text) for passage in passages) <= 8000
    assert all(len(passage.text) <= CHUNK_MAX_CHARACTERS for passage in passages)
