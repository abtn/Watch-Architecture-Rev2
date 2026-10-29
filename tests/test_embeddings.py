import math
from typing import Any

import pytest

from core.embeddings import (
    EmbeddingProviderError,
    EmbeddingSpace,
    OpenAICompatibleEmbeddingProvider,
    embedding_provider_from_env,
)
from core.vector_type import parse_vector, serialize_vector, validate_vector


def test_embedding_space_key_is_stable_and_covers_model_revision() -> None:
    space = EmbeddingSpace(
        "openai_compatible", "bge-m3", "revision-a", 1024, "openai-embed-v1"
    )

    assert space.key == EmbeddingSpace(
        "openai_compatible", "bge-m3", "revision-a", 1024, "openai-embed-v1"
    ).key
    assert space.key != EmbeddingSpace(
        "openai_compatible", "bge-m3", "revision-b", 1024, "openai-embed-v1"
    ).key
    assert space.key != EmbeddingSpace(
        "openai_compatible", "bge-m3", "revision-a", 768, "openai-embed-v1"
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


class MockEmbeddingAPI(OpenAICompatibleEmbeddingProvider):
    def __init__(self, *, ready_after: int = 0, dimensions: int = 3) -> None:
        super().__init__(
            base_url="http://localhost:1234/v1",
            model="bge-m3",
            dimensions=dimensions,
            timeout_seconds=1,
            ready_timeout_seconds=0.2,
            batch_size=2,
            retry_attempts=2,
        )
        self.ready_after = ready_after
        self.model_calls = 0
        self.embedding_calls = 0
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self.fail_first_embedding = False
        self.reverse_results = False

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.requests.append((method, path, payload))
        if path == "models":
            self.model_calls += 1
            if self.model_calls <= self.ready_after:
                return {"data": []}
            return {
                "data": [
                    {
                        "id": "bge-m3",
                        "object": "model",
                        "owned_by": "local",
                        "created": 123,
                    }
                ]
            }
        if path == "embeddings":
            self.embedding_calls += 1
            if self.fail_first_embedding and self.embedding_calls == 1:
                raise EmbeddingProviderError(
                    "embedding_api_http_error_503", retryable=True
                )
            assert payload is not None
            data = [
                {
                    "object": "embedding",
                    "index": index,
                    "embedding": [float(len(text)), 0.5, 0.25],
                }
                for index, text in enumerate(payload["input"])
            ]
            if self.reverse_results:
                data.reverse()
            return {"data": data}
        raise AssertionError(f"unexpected endpoint: {path}")


def test_openai_compatible_provider_uses_standard_api_and_batches() -> None:
    provider = MockEmbeddingAPI()

    batch = provider.embed(["first source", "second source", "third source"])

    assert batch.space.provider == "openai_compatible"
    assert batch.space.model == "bge-m3"
    assert batch.space.revision.startswith("metadata-sha256:")
    assert batch.space.dimensions == 3
    assert [vector[0] for vector in batch.vectors] == [12.0, 13.0, 12.0]
    embedding_requests = [
        request for request in provider.requests if request[1] == "embeddings"
    ]
    assert [
        len(request[2]["input"]) for request in embedding_requests if request[2]
    ] == [2, 1]
    assert all(
        request[2]["encoding_format"] == "float"
        for request in embedding_requests
        if request[2]
    )


def test_openai_compatible_provider_restores_response_order() -> None:
    provider = MockEmbeddingAPI()
    provider.reverse_results = True

    batch = provider.embed(["one", "longer"])

    assert [vector[0] for vector in batch.vectors] == [3.0, 6.0]


def test_provider_waits_for_local_model_to_become_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.embeddings.time.sleep", lambda _: None)
    provider = MockEmbeddingAPI(ready_after=2)

    space = provider.current_space()

    assert space.model == "bge-m3"
    assert provider.model_calls == 3


def test_provider_times_out_when_model_is_not_loaded() -> None:
    class MissingModel(MockEmbeddingAPI):
        def _request_json(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if path == "models":
                self.model_calls += 1
                return {"data": []}
            return super()._request_json(method, path, payload)

    provider = MissingModel()
    provider._ready_timeout_seconds = 0.001

    with pytest.raises(
        EmbeddingProviderError, match="embedding_model_not_listed_after_ready_timeout"
    ):
        provider.current_space()


def test_provider_rejects_invalid_dimensions() -> None:
    class BadVector(MockEmbeddingAPI):
        def _request_json(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if path == "embeddings":
                return {"data": [{"index": 0, "embedding": [1.0, 2.0]}]}
            return super()._request_json(method, path, payload)

    with pytest.raises(EmbeddingProviderError, match="embedding_dimension_mismatch"):
        BadVector().embed(["test"])


def test_provider_retries_transient_embedding_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.embeddings.time.sleep", lambda _: None)
    provider = MockEmbeddingAPI()
    provider.fail_first_embedding = True

    batch = provider.embed(["test"])

    assert len(batch.vectors) == 1
    assert provider.embedding_calls == 2


def test_provider_rejects_model_metadata_change_mid_request() -> None:
    class ChangingMetadata(MockEmbeddingAPI):
        def _request_json(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if path == "models":
                self.model_calls += 1
                owner = "local-a" if self.model_calls == 1 else "local-b"
                return {
                    "data": [
                        {
                            "id": "bge-m3",
                            "object": "model",
                            "owned_by": owner,
                            "created": 123,
                        }
                    ]
                }
            return super()._request_json(method, path, payload)

    with pytest.raises(
        EmbeddingProviderError, match="embedding_space_changed_during_request"
    ):
        ChangingMetadata().embed(["test"])


def test_embedding_provider_environment_defaults_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "WATCH_EMBEDDING_PROVIDER",
        "WATCH_EMBEDDING_BASE_URL",
        "WATCH_EMBEDDING_MODEL",
        "WATCH_EMBEDDING_DIMENSIONS",
        "WATCH_EMBEDDING_TIMEOUT_SECONDS",
        "WATCH_EMBEDDING_READY_TIMEOUT_SECONDS",
        "WATCH_EMBEDDING_BATCH_SIZE",
        "WATCH_EMBEDDING_RETRY_ATTEMPTS",
        "WATCH_EMBEDDING_CONFIGURATION",
        "WATCH_EMBEDDING_API_KEY",
        "WATCH_EMBEDDING_REVISION",
    ):
        monkeypatch.delenv(name, raising=False)

    provider = embedding_provider_from_env()

    assert isinstance(provider, OpenAICompatibleEmbeddingProvider)
    assert provider._model == "bge-m3"
    assert provider._dimensions == 1024
    assert provider._base_url == "http://localhost:1234/v1/"
    assert provider._batch_size == 8
    assert provider._timeout_seconds == 180.0
    assert provider._ready_timeout_seconds == 180.0


def test_embedding_provider_rejects_unsupported_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WATCH_EMBEDDING_PROVIDER", "native_provider")

    with pytest.raises(ValueError, match="unsupported_embedding_provider"):
        embedding_provider_from_env()


def test_explicit_revision_overrides_api_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WATCH_EMBEDDING_REVISION", "bge-m3-q8-v1")
    provider = embedding_provider_from_env()
    assert provider._revision == "bge-m3-q8-v1"
