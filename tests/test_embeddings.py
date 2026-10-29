import math
from typing import Any

import pytest

from core.embeddings import (
    EmbeddingProviderError,
    EmbeddingSpace,
    OllamaEmbeddingProvider,
    embedding_provider_from_env,
)
from core.vector_type import parse_vector, serialize_vector, validate_vector


def test_embedding_space_key_is_stable_and_covers_model_revision() -> None:
    space = EmbeddingSpace("ollama", "bge-m3", "digest-a", 1024, "ollama-embed-v1")

    assert space.key == EmbeddingSpace(
        "ollama", "bge-m3", "digest-a", 1024, "ollama-embed-v1"
    ).key
    assert space.key != EmbeddingSpace(
        "ollama", "bge-m3", "digest-b", 1024, "ollama-embed-v1"
    ).key
    assert space.key != EmbeddingSpace(
        "ollama", "bge-m3", "digest-a", 768, "ollama-embed-v1"
    ).key


def test_vector_text_round_trip_and_validation() -> None:
    assert serialize_vector([1, -0.5, 0.0]) == "[1,-0.5,0]"
    assert parse_vector("[1,-0.5,0]") == [1.0, -0.5, 0.0]
    assert validate_vector((1, 2.5), 2) == [1.0, 2.5]

    with pytest.raises(ValueError, match="embedding_dimension_mismatch"):
        validate_vector([1.0], 2)
    with pytest.raises(ValueError, match="non_finite_embedding_value"):
        serialize_vector([math.nan])
    with pytest.raises(ValueError, match="non_numeric_embedding_value"):
        serialize_vector([True])
    with pytest.raises(ValueError, match="invalid_database_vector"):
        parse_vector("not a vector")


class MockOllama(OllamaEmbeddingProvider):
    def __init__(self, *, digest: str = "sha256:model-revision") -> None:
        super().__init__(base_url="http://localhost:11434", dimensions=3, batch_size=2)
        self.digest = digest
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.requests.append((method, path, payload))
        if path == "api/tags":
            return {
                "models": [
                    {
                        "name": "bge-m3:latest",
                        "model": "bge-m3:latest",
                        "digest": self.digest,
                    }
                ]
            }
        if path == "api/embed":
            assert payload is not None
            texts = payload["input"]
            return {"embeddings": [[1.0, 0.5, 0.25] for _ in texts]}
        raise AssertionError(f"unexpected path: {path}")


def test_ollama_provider_resolves_digest_and_batches_without_truncation() -> None:
    provider = MockOllama()

    batch = provider.embed(["first source", "second source", "third source"])

    assert batch.space.provider == "ollama"
    assert batch.space.model == "bge-m3"
    assert batch.space.revision == "sha256:model-revision"
    assert batch.space.dimensions == 3
    assert len(batch.vectors) == 3
    embed_requests = [
        request for request in provider.requests if request[1] == "api/embed"
    ]
    assert [len(request[2]["input"]) for request in embed_requests if request[2]] == [
        2,
        1,
    ]
    assert all(
        request[2]["truncate"] is False
        for request in embed_requests
        if request[2]
    )


def test_ollama_provider_rejects_missing_model() -> None:
    class MissingModel(MockOllama):
        def _request_json(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if path == "api/tags":
                return {"models": []}
            return super()._request_json(method, path, payload)

    with pytest.raises(EmbeddingProviderError, match="ollama_model_not_installed"):
        MissingModel().current_space()


def test_ollama_provider_rejects_invalid_dimensions() -> None:
    class BadVector(MockOllama):
        def _request_json(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if path == "api/embed":
                return {"embeddings": [[1.0, 2.0]]}
            return super()._request_json(method, path, payload)

    with pytest.raises(EmbeddingProviderError, match="embedding_dimension_mismatch"):
        BadVector().embed(["test"])


def test_embedding_provider_environment_defaults_to_local_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WATCH_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("WATCH_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("WATCH_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("WATCH_EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("WATCH_EMBEDDING_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("WATCH_EMBEDDING_BATCH_SIZE", raising=False)
    provider = embedding_provider_from_env()

    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider._model == "bge-m3"
    assert provider._dimensions == 1024


def test_embedding_provider_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WATCH_EMBEDDING_PROVIDER", "remote_provider")

    with pytest.raises(ValueError, match="unsupported_embedding_provider"):
        embedding_provider_from_env()


def test_ollama_provider_rejects_model_digest_change_mid_request() -> None:
    class ChangingDigest(MockOllama):
        tag_calls = 0

        def _request_json(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if path == "api/tags":
                self.tag_calls += 1
                if self.tag_calls >= 2:
                    self.digest = "sha256:new-revision"
            return super()._request_json(method, path, payload)

    with pytest.raises(
        EmbeddingProviderError, match="embedding_space_changed_during_request"
    ):
        ChangingDigest().embed(["test"])
