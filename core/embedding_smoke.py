"""Run an end-to-end smoke test against the configured embedding API.

Usage on the developer machine:
    uv run alembic upgrade head
    $env:TEST_DATABASE_URL = "postgresql+psycopg://watch:watch@127.0.0.1:5432/watch"
    uv run python -m core.embedding_smoke

The script inserts a uniquely identified temporary Team, policy, and Signal, then
removes those rows in a finally block. Its temporary SnapshotStore is deleted too.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine, delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from core.embeddings import EmbeddingProviderError, embedding_provider_from_env
from core.knowledge_index import HybridKnowledgeRetriever, SignalIndexer
from core.models import KnowledgeChunk, Signal, Team, TeamPolicy
from core.snapshot_store import SnapshotStore


def main() -> int:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_url:
        print(
            "Set TEST_DATABASE_URL to a migrated disposable PostgreSQL database.",
            file=sys.stderr,
        )
        return 2

    engine = create_engine(database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    team_id = uuid4()
    policy_id = uuid4()
    signal_id = uuid4()
    origin_url = f"https://local-smoke.invalid/{signal_id}"
    source_type = "embedding_api_smoke"
    source_content = (
        b"Local-only smoke-test article. Embeddings and PostgreSQL vector retrieval "
        b"should preserve this astronomy evidence."
    )
    success = False
    cleanup_error = False
    schema_ready = False

    try:
        with engine.connect() as connection:
            table_exists = connection.scalar(
                text("SELECT to_regclass('public.knowledge_chunks')")
            )
        if table_exists is None:
            raise RuntimeError(
                "knowledge_chunks table is missing; run uv run alembic upgrade head"
            )
        schema_ready = True

        provider = embedding_provider_from_env()
        space = provider.current_space()

        with TemporaryDirectory(prefix="watch-embedding-api-smoke-") as root:
            snapshot_store = SnapshotStore(Path(root))
            snapshot_ref, stored_hash = snapshot_store.put(source_content)

            with session_factory.begin() as session:
                session.add(Team(id=team_id, domain="local_smoke", status="active"))
                session.flush()
                session.add(
                    TeamPolicy(
                        id=policy_id,
                        team_id=team_id,
                        version=1,
                        rules={
                            "sources": [
                                {
                                    "origin_url": origin_url,
                                    "source_type": source_type,
                                }
                            ]
                        },
                    )
                )
                session.flush()
                session.add(
                    Signal(
                        id=signal_id,
                        domain="local_smoke",
                        source_type=source_type,
                        origin_url=origin_url,
                        fetched_at=datetime.now(timezone.utc),
                        content_hash=stored_hash,
                        snapshot_ref=snapshot_ref,
                    )
                )

            indexer = SignalIndexer(session_factory, snapshot_store, provider)
            first = indexer.index_signal(signal_id)
            second = indexer.index_signal(signal_id)
            retriever = HybridKnowledgeRetriever(
                session_factory, snapshot_store, provider
            )
            passages = retriever.retrieve(team_id, "embedding astronomy evidence")

            if first.outcome != "indexed" or first.chunk_count != 1:
                raise RuntimeError("smoke test did not index its test Signal")
            if second.outcome != "unchanged":
                raise RuntimeError("smoke test did not prove idempotency")
            if not any(
                passage.signal_id == signal_id
                and "astronomy evidence" in passage.text
                for passage in passages
            ):
                raise RuntimeError(
                    "smoke test could not retrieve its authorized test Signal"
                )

            print("Embedding API smoke test: PASS")
            print(f"Provider: {space.provider}")
            print(f"Model ID: {space.model}")
            print(f"Model revision/fingerprint: {space.revision}")
            print(f"Embedding dimensions: {space.dimensions}")
            print("Projection indexing: PASS")
            print("Repeat indexing / idempotency: PASS")
            print("Authorized hybrid retrieval: PASS")
            success = True
    except (EmbeddingProviderError, RuntimeError, ValueError) as error:
        print(f"Embedding API smoke test failed: {error}", file=sys.stderr)
    except SQLAlchemyError:
        print(
            "Embedding API smoke test could not access the migrated PostgreSQL "
            "database. Check TEST_DATABASE_URL and database availability.",
            file=sys.stderr,
        )
    except OSError:
        print(
            "Embedding API smoke test could not access local Snapshot storage. "
            "Check the configured embedding API/model and database separately.",
            file=sys.stderr,
        )
    finally:
        if schema_ready:
            try:
                with session_factory.begin() as session:
                    session.execute(
                        delete(KnowledgeChunk).where(
                            KnowledgeChunk.signal_id == signal_id
                        )
                    )
                    session.execute(delete(Signal).where(Signal.id == signal_id))
                    session.execute(
                        delete(TeamPolicy).where(TeamPolicy.id == policy_id)
                    )
                    session.execute(delete(Team).where(Team.id == team_id))
            except SQLAlchemyError:
                cleanup_error = True
                print(
                    "Warning: disposable smoke-test records could not all be removed; "
                    "inspect the test database before reusing it.",
                    file=sys.stderr,
                )
        engine.dispose()

    if cleanup_error:
        return 1
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
