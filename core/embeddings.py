"""Provider-neutral embeddings over an OpenAI-compatible API.

The adapter works with local servers such as LM Studio and with hosted services
that implement the standard /v1/models and /v1/embeddings contract. Tests inject
deterministic fakes and never make inference requests or download model weights.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class EmbeddingProviderError(RuntimeError):
    """A safe, non-payload-bearing embedding provider failure."""

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


@dataclass(frozen=True)
class EmbeddingSpace:
    """Identity of one compatible embedding vector space."""

    provider: str
    model: str
    revision: str
    dimensions: int
    configuration: str

    @property
    def key(self) -> str:
        payload = {
            "configuration": self.configuration,
            "dimensions": self.dimensions,
            "model": self.model,
            "provider": self.provider,
            "revision": self.revision,
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmbeddingBatch:
    """Embeddings and the exact vector-space identity used to produce them."""

    space: EmbeddingSpace
    vectors: tuple[tuple[float, ...], ...]


class EmbeddingProvider(Protocol):
    """Small adapter boundary consumed by the indexer and retriever."""

    def current_space(self) -> EmbeddingSpace:
        """Return the current model/version identity."""
        ...

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed the supplied texts in order and report their vector-space ID."""
        ...


class OpenAICompatibleEmbeddingProvider:
    """Call an OpenAI-compatible /v1/models and /v1/embeddings API."""

    provider_name = "openai_compatible"
    _RETRYABLE_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "bge-m3",
        dimensions: int = 1024,
        timeout_seconds: float = 180.0,
        batch_size: int = 8,
        configuration: str = "openai-embeddings-v1",
        api_key: str = "",
        revision: str = "",
        ready_timeout_seconds: float = 180.0,
        retry_attempts: int = 2,
    ) -> None:
        parsed = urlparse(base_url.strip().rstrip("/"))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid_embedding_api_base_url")
        if not model.strip():
            raise ValueError("empty_embedding_model")
        if dimensions <= 0:
            raise ValueError("invalid_embedding_dimensions")
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise ValueError("invalid_embedding_timeout")
        if batch_size <= 0:
            raise ValueError("invalid_embedding_batch_size")
        if not configuration.strip():
            raise ValueError("empty_embedding_configuration")
        if ready_timeout_seconds <= 0 or not math.isfinite(ready_timeout_seconds):
            raise ValueError("invalid_embedding_ready_timeout")
        if retry_attempts <= 0:
            raise ValueError("invalid_embedding_retry_attempts")

        self._base_url = base_url.strip().rstrip("/") + "/"
        self._endpoint_identity = base_url.strip().rstrip("/")
        self._model = model.strip()
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._batch_size = batch_size
        self._api_key = api_key.strip()
        self._revision = revision.strip()
        self._ready_timeout_seconds = ready_timeout_seconds
        self._retry_attempts = retry_attempts
        # Endpoint identity keeps compatible-looking but different servers apart.
        self._configuration = json.dumps(
            {
                "adapter": configuration.strip(),
                "base_url": self._endpoint_identity,
                "request_contract": "openai-compatible-embeddings-v1",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def current_space(self) -> EmbeddingSpace:
        """Wait boundedly for the configured model to appear in the API model list.

        The API owns loading and GPU placement. This adapter does not issue
        provider-specific load/unload commands; it observes readiness and times out
        with a safe diagnostic if the service or configured model never appears.
        """
        deadline = time.monotonic() + self._ready_timeout_seconds
        delay = 0.25
        last_reason = "embedding_model_not_listed"

        while True:
            try:
                document = self._request_json("GET", "models")
                data = document.get("data")
                if not isinstance(data, list):
                    raise EmbeddingProviderError(
                        "embedding_api_invalid_models_response"
                    )

                matches = [
                    item
                    for item in data
                    if isinstance(item, dict) and item.get("id") == self._model
                ]
                if len(matches) > 1:
                    raise EmbeddingProviderError(
                        "embedding_api_ambiguous_model_identifier"
                    )
                if matches:
                    model_metadata = matches[0]
                    revision = self._revision or _metadata_revision(model_metadata)
                    return EmbeddingSpace(
                        provider=self.provider_name,
                        model=self._model,
                        revision=revision,
                        dimensions=self._dimensions,
                        configuration=self._configuration,
                    )
                last_reason = "embedding_model_not_listed"
            except EmbeddingProviderError as error:
                if not error.retryable:
                    raise
                last_reason = error.reason

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EmbeddingProviderError(
                    f"{last_reason}_after_ready_timeout"
                ) from None
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, 3.0)

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed in modest batches and reject ordering, shape, or model changes."""
        for value in texts:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("embedding_text_must_be_nonempty")

        initial_space = self.current_space()
        if not texts:
            return EmbeddingBatch(space=initial_space, vectors=())

        vectors: list[tuple[float, ...]] = []
        start = 0
        while start < len(texts):
            before = self.current_space()
            if before.key != initial_space.key:
                raise EmbeddingProviderError("embedding_space_changed_during_request")

            batch_texts = list(texts[start : start + self._batch_size])
            response = self._request_json_with_retries(
                "POST",
                "embeddings",
                {
                    "model": self._model,
                    "input": batch_texts,
                    "encoding_format": "float",
                },
            )
            raw_data = response.get("data")
            if not isinstance(raw_data, list) or len(raw_data) != len(batch_texts):
                raise EmbeddingProviderError("embedding_count_mismatch")

            ordered_data = _ordered_embedding_data(raw_data, len(batch_texts))
            batch_vectors: list[tuple[float, ...]] = []
            for item in ordered_data:
                raw_vector = item.get("embedding")
                if not isinstance(raw_vector, list):
                    raise EmbeddingProviderError("invalid_embedding_vector")
                try:
                    vector = _validate_vector(raw_vector, initial_space.dimensions)
                except ValueError as error:
                    raise EmbeddingProviderError(error.args[0]) from error
                batch_vectors.append(tuple(vector))

            after = self.current_space()
            if after.key != initial_space.key:
                raise EmbeddingProviderError("embedding_space_changed_during_request")

            vectors.extend(batch_vectors)
            start += len(batch_texts)

        return EmbeddingBatch(space=initial_space, vectors=tuple(vectors))

    def _request_json_with_retries(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Retry only transient failures, with a small bounded exponential delay."""
        delay = 1.0
        for attempt in range(self._retry_attempts):
            try:
                return self._request_json(method, path, payload)
            except EmbeddingProviderError as error:
                if not error.retryable or attempt == self._retry_attempts - 1:
                    raise
                time.sleep(min(delay, 5.0))
                delay = min(delay * 2, 5.0)
        raise EmbeddingProviderError("embedding_api_retry_exhausted")

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = urljoin(self._base_url, path)
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read(20 * 1024 * 1024 + 1)
        except HTTPError as error:
            # Never include provider response bodies, API keys, or input text here.
            raise EmbeddingProviderError(
                f"embedding_api_http_error_{error.code}",
                retryable=error.code in self._RETRYABLE_HTTP_CODES,
            ) from None
        except (URLError, TimeoutError, OSError):
            raise EmbeddingProviderError(
                "embedding_api_unavailable_or_timeout", retryable=True
            ) from None

        if len(raw) > 20 * 1024 * 1024:
            raise EmbeddingProviderError("embedding_api_response_too_large")
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EmbeddingProviderError(
                "embedding_api_invalid_json_response"
            ) from None
        if not isinstance(document, dict):
            raise EmbeddingProviderError("embedding_api_invalid_json_shape")
        return document


def _ordered_embedding_data(
    data: list[object], expected_count: int
) -> list[dict[str, Any]]:
    if not all(isinstance(item, dict) for item in data):
        raise EmbeddingProviderError("invalid_embedding_response_item")

    items = [item for item in data if isinstance(item, dict)]
    indexed = ["index" in item for item in items]
    if any(indexed) and not all(indexed):
        raise EmbeddingProviderError("invalid_embedding_response_indices")
    if all(indexed):
        indices = [item.get("index") for item in items]
        if any(
            isinstance(index, bool) or not isinstance(index, int) for index in indices
        ):
            raise EmbeddingProviderError("invalid_embedding_response_indices")
        if sorted(indices) != list(range(expected_count)):
            raise EmbeddingProviderError("invalid_embedding_response_indices")
        items.sort(key=lambda item: item["index"])
    return items


def _metadata_revision(metadata: dict[str, Any]) -> str:
    """Fingerprint API model metadata when no stronger revision pin is configured.

    OpenAI-compatible APIs do not standardize an immutable model-weight digest.
    Operators should set WATCH_EMBEDDING_REVISION when model IDs can be reused.
    """
    canonical = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "metadata-sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_vector(values: Sequence[object], dimensions: int) -> list[float]:
    if len(values) != dimensions:
        raise ValueError("embedding_dimension_mismatch")
    vector: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("non_numeric_embedding_value")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non_finite_embedding_value")
        vector.append(number)
    return vector


def embedding_provider_from_env() -> EmbeddingProvider:
    """Build the configured provider-neutral API adapter."""
    provider_name = (
        os.environ.get("WATCH_EMBEDDING_PROVIDER", "openai_compatible")
        .strip()
        .lower()
        .replace("-", "_")
    )
    if provider_name != "openai_compatible":
        raise ValueError("unsupported_embedding_provider")

    try:
        dimensions = int(os.environ.get("WATCH_EMBEDDING_DIMENSIONS", "1024"))
        timeout = float(os.environ.get("WATCH_EMBEDDING_TIMEOUT_SECONDS", "180"))
        ready_timeout = float(
            os.environ.get("WATCH_EMBEDDING_READY_TIMEOUT_SECONDS", "180")
        )
        batch_size = int(os.environ.get("WATCH_EMBEDDING_BATCH_SIZE", "8"))
        retry_attempts = int(os.environ.get("WATCH_EMBEDDING_RETRY_ATTEMPTS", "2"))
    except ValueError as error:
        raise ValueError("invalid_embedding_provider_configuration") from error

    return OpenAICompatibleEmbeddingProvider(
        base_url=os.environ.get(
            "WATCH_EMBEDDING_BASE_URL", "http://localhost:1234/v1"
        ),
        model=os.environ.get("WATCH_EMBEDDING_MODEL", "bge-m3"),
        dimensions=dimensions,
        timeout_seconds=timeout,
        ready_timeout_seconds=ready_timeout,
        batch_size=batch_size,
        retry_attempts=retry_attempts,
        configuration=os.environ.get(
            "WATCH_EMBEDDING_CONFIGURATION", "openai-embeddings-v1"
        ),
        api_key=os.environ.get("WATCH_EMBEDDING_API_KEY", ""),
        revision=os.environ.get("WATCH_EMBEDDING_REVISION", ""),
    )
