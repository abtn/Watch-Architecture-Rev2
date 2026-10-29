"""Provider-neutral embeddings with a local Ollama/BGE-M3 adapter.

No provider SDK is required. Deterministic tests inject a fake implementation of
EmbeddingProvider and never make network requests or download model weights.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class EmbeddingProviderError(RuntimeError):
    """A safe, non-payload-bearing embedding provider failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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


class OllamaEmbeddingProvider:
    """Call a locally reachable Ollama server's native embedding API."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "bge-m3",
        dimensions: int = 1024,
        timeout_seconds: float = 60.0,
        batch_size: int = 32,
        configuration: str = "ollama-embed-v1",
    ) -> None:
        parsed = urlparse(base_url.strip().rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("invalid_ollama_base_url")
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

        self._base_url = base_url.strip().rstrip("/") + "/"
        self._model = model.strip()
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._batch_size = batch_size
        self._configuration = configuration.strip()

    def current_space(self) -> EmbeddingSpace:
        """Resolve the exact installed digest instead of trusting a mutable tag."""
        document = self._request_json("GET", "api/tags")
        models = document.get("models")
        if not isinstance(models, list):
            raise EmbeddingProviderError("ollama_invalid_tags_response")

        accepted_names = {self._model}
        if ":" not in self._model:
            accepted_names.add(f"{self._model}:latest")

        matches: list[dict[str, Any]] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            names = {item.get("name"), item.get("model")}
            if any(isinstance(name, str) and name in accepted_names for name in names):
                matches.append(item)

        if not matches:
            raise EmbeddingProviderError("ollama_model_not_installed_run_ollama_pull")
        if len(matches) != 1:
            # Exact and :latest aliases can refer to the same local model. Prefer an
            # exact configured name; otherwise require an unambiguous latest alias.
            exact = [
                item
                for item in matches
                if item.get("name") == self._model or item.get("model") == self._model
            ]
            matches = exact if len(exact) == 1 else matches[:1]

        digest = matches[0].get("digest")
        if not isinstance(digest, str) or not digest.strip():
            raise EmbeddingProviderError("ollama_model_digest_missing")

        return EmbeddingSpace(
            provider=self.provider_name,
            model=self._model,
            revision=digest.strip(),
            dimensions=self._dimensions,
            configuration=self._configuration,
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Generate vectors and verify the installed model did not change mid-call."""
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
            response = self._request_json(
                "POST",
                "api/embed",
                {
                    "model": self._model,
                    "input": batch_texts,
                    "truncate": False,
                },
            )
            raw_embeddings = response.get("embeddings")
            if not isinstance(raw_embeddings, list) or len(raw_embeddings) != len(
                batch_texts
            ):
                raise EmbeddingProviderError("ollama_embedding_count_mismatch")

            batch_vectors: list[tuple[float, ...]] = []
            for raw in raw_embeddings:
                if not isinstance(raw, list):
                    raise EmbeddingProviderError("ollama_invalid_embedding_vector")
                try:
                    vector = _validate_vector(raw, initial_space.dimensions)
                except ValueError as error:
                    raise EmbeddingProviderError(error.args[0]) from error
                batch_vectors.append(tuple(vector))

            after = self.current_space()
            if after.key != initial_space.key:
                raise EmbeddingProviderError("embedding_space_changed_during_request")

            vectors.extend(batch_vectors)
            start += len(batch_texts)

        return EmbeddingBatch(space=initial_space, vectors=tuple(vectors))

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = urljoin(self._base_url, path)
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read(20 * 1024 * 1024 + 1)
        except HTTPError as error:
            # Do not put remote response bodies or query text into logs/exceptions.
            raise EmbeddingProviderError(
                f"ollama_http_error_{error.code}"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise EmbeddingProviderError("ollama_unavailable_or_timeout") from None

        if len(raw) > 20 * 1024 * 1024:
            raise EmbeddingProviderError("ollama_response_too_large")
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EmbeddingProviderError("ollama_invalid_json_response") from None
        if not isinstance(document, dict):
            raise EmbeddingProviderError("ollama_invalid_json_shape")
        return document


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
    """Build the configured embedding provider; only local Ollama is enabled yet."""
    provider_name = os.environ.get("WATCH_EMBEDDING_PROVIDER", "ollama").strip().lower()
    if provider_name != "ollama":
        raise ValueError("unsupported_embedding_provider")

    try:
        dimensions = int(os.environ.get("WATCH_EMBEDDING_DIMENSIONS", "1024"))
        timeout = float(os.environ.get("WATCH_EMBEDDING_TIMEOUT_SECONDS", "60"))
        batch_size = int(os.environ.get("WATCH_EMBEDDING_BATCH_SIZE", "32"))
    except ValueError as error:
        raise ValueError("invalid_embedding_provider_configuration") from error

    return OllamaEmbeddingProvider(
        base_url=os.environ.get(
            "WATCH_EMBEDDING_BASE_URL", "http://localhost:11434"
        ),
        model=os.environ.get("WATCH_EMBEDDING_MODEL", "bge-m3"),
        dimensions=dimensions,
        timeout_seconds=timeout,
        batch_size=batch_size,
        configuration=os.environ.get(
            "WATCH_EMBEDDING_CONFIGURATION", "ollama-embed-v1"
        ),
    )
