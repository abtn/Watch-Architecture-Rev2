"""Run a disposable end-to-end smoke test against a local Ollama BGE-M3 model.

Usage on the developer machine:
    uv run alembic upgrade head
    $env:TEST_DATABASE_URL = "postgresql+psycopg://watch:watch@127.0.0.1:5432/watch"
    uv run python -m core.embedding_smoke

The script inserts a uniquely identified temporary Team, policy, and Signal, then
removes those rows in a finally block. Its temporary SnapshotStore is deleted too.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine, delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

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
    source_type = "local_embedding_smoke"
    source_content = (
        b"Local-only smoke-test article. BGE-M3 embeddings and PostgreSQL "
        b"vector retrieval should preserve this astronomy evidence."
    )
    snapshot_store: SnapshotStore | None = None
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
        if space.model != "bge-m3" or space.dimensions != 1024:
            raise RuntimeError(
                "local smoke test expects model bge-m3 with 1024 dimensions"
            )

        with TemporaryDirectory(prefix="watch-local-embedding-smoke-") as root:
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
            passages = retriever.retrieve(team_id, "BGE-M3 astronomy evidence")

            if first.outcome != "indexed" or first.chunk_count != 1:
                raise RuntimeError("local smoke test did not index its test Signal")
            if second.outcome != "unchanged":
                raise RuntimeError("local smoke test did not prove idempotency")
            if not any(
                passage.signal_id == signal_id
                and "astronomy evidence" in passage.text
                for passage in passages
            ):
                raise RuntimeError(
                    "local smoke test could not retrieve its authorized test Signal"
                )

            print("Local BGE-M3 smoke test: PASS")
            print(f"Embedding model: {space.model}")
            print(f"Installed revision: {space.revision}")
            print(f"Embedding dimensions: {space.dimensions}")
            print("Projection indexing: PASS")
            print("Repeat indexing / idempotency: PASS")
            print("Authorized hybrid retrieval: PASS")
            success = True
    except (EmbeddingProviderError, RuntimeError, ValueError) as error:
        print(f"Local embedding smoke test failed: {error}", file=sys.stderr)
    except SQLAlchemyError:
        print(
            "Local embedding smoke test could not access the migrated PostgreSQL "
            "database. Check TEST_DATABASE_URL and database availability.",
            file=sys.stderr,
        )
    except OSError:
        print(
            "Local embedding smoke test could not access Ollama or local Snapshot "
            "storage. Check that Ollama is running and BGE-M3 is installed.",
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
