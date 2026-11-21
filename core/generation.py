"""Stateless generation over Chat Completions.

The adapter returns raw completion text with validated provider usage. The
legacy JSON method strictly parses that text for existing callers. It never
exposes reasoning traces or tool calls. Each call makes one HTTP request;
retry policy belongs to the ordinary Task attempt boundary.
"""

from __future__ import annotations

import json
import math
import os
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from http.client import HTTPSConnection, IncompleteRead
from threading import Event, Thread, Timer
from typing import Any, Iterator, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, Request, build_opener

DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8"
MAX_MODEL_CONTEXT_TOKENS = 32_000
CHAT_TOKEN_OVERHEAD_TOKENS = 128
CLOUDFLARE_PRICING_REVISION = "cloudflare-llama-3.1-8b-fp8-2026-10-30"
DEFAULT_MAX_OUTPUT_TOKENS = 1024
INPUT_USD_PER_MILLION_TOKENS = Decimal("0.152")
OUTPUT_USD_PER_MILLION_TOKENS = Decimal("0.287")
_RETRYABLE_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class _DeadlineHTTPSConnection(HTTPSConnection):
    """HTTPS connection whose establishment and I/O share one absolute deadline."""

    def __init__(self, host: str, *, deadline: float, **kwargs: Any) -> None:
        self._deadline = deadline
        self._deadline_timer: Timer | None = None
        self._deadline_expired = Event()
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("generation_deadline_exceeded")

        resolved = Event()
        addresses: list[tuple[Any, ...]] = []
        failures: list[Exception] = []

        def resolve_host() -> None:
            try:
                addresses.extend(
                    socket.getaddrinfo(
                        self.host,
                        self.port,
                        0,
                        socket.SOCK_STREAM,
                    )
                )
            except Exception as error:
                failures.append(error)
            finally:
                resolved.set()

        resolver = Thread(target=resolve_host, daemon=True)
        resolver.start()

        timer = Timer(remaining, self._expire_connection)
        timer.daemon = True
        self._deadline_timer = timer
        timer.start()

        try:
            if not resolved.wait(remaining):
                raise TimeoutError("generation_deadline_exceeded")
            if self._deadline_expired.is_set() or time.monotonic() >= self._deadline:
                raise TimeoutError("generation_deadline_exceeded")
            if failures:
                raise failures[0]
            if not addresses:
                raise OSError("generation_dns_returned_no_addresses")

            last_error: OSError | None = None
            for family, socktype, protocol, _canonical_name, address in addresses:
                remaining = self._deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("generation_deadline_exceeded")

                connection_socket = socket.socket(family, socktype, protocol)
                self.sock = connection_socket
                try:
                    if self._deadline_expired.is_set():
                        raise TimeoutError("generation_deadline_exceeded")
                    connection_socket.settimeout(remaining)
                    if self.source_address:
                        connection_socket.bind(self.source_address)
                    connection_socket.connect(address)
                    last_error = None
                    break
                except OSError as error:
                    self._close_socket(connection_socket)
                    self.sock = None
                    last_error = error
                    if (
                        self._deadline_expired.is_set()
                        or time.monotonic() >= self._deadline
                    ):
                        raise TimeoutError("generation_deadline_exceeded") from None

            if self.sock is None:
                if last_error is not None:
                    raise last_error
                raise OSError("generation_connection_socket_missing")

            if self._tunnel_host:
                self._tunnel()

            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("generation_deadline_exceeded")
            self.sock.settimeout(remaining)
            server_hostname = self._tunnel_host or self.host
            self.sock = self._context.wrap_socket(
                self.sock,
                server_hostname=server_hostname,
            )
            if self._deadline_expired.is_set() or time.monotonic() >= self._deadline:
                self._expire_connection()
                raise TimeoutError("generation_deadline_exceeded")
        except OSError:
            if self._deadline_expired.is_set() or time.monotonic() >= self._deadline:
                self._expire_connection()
                raise TimeoutError("generation_deadline_exceeded") from None
            raise

    def _expire_connection(self) -> None:
        self._deadline_expired.set()
        connection_socket = self.sock
        if connection_socket is not None:
            self._close_socket(connection_socket)

    def cancel_deadline(self) -> None:
        if self._deadline_timer is not None:
            self._deadline_timer.cancel()

    @staticmethod
    def _close_socket(connection_socket: socket.socket) -> None:
        try:
            connection_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            connection_socket.close()
        except OSError:
            pass


class _DeadlineHTTPSHandler(HTTPSHandler):
    def __init__(self, deadline: float) -> None:
        super().__init__()
        self._deadline = deadline
        self._connection: _DeadlineHTTPSConnection | None = None

    def https_open(self, request):
        def create_connection(host: str, *, timeout: float, **kwargs: Any):
            connection = _DeadlineHTTPSConnection(
                host,
                timeout=timeout,
                deadline=self._deadline,
                **kwargs,
            )
            self._connection = connection
            return connection

        return self.do_open(
            create_connection,
            request,
            context=self._context,
        )

    def cancel_deadline(self) -> None:
        if self._connection is not None:
            self._connection.cancel_deadline()


@contextmanager
def _open_with_deadline(
    request: Request,
    deadline: float,
) -> Iterator[Any]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("generation_deadline_exceeded")
    handler = _DeadlineHTTPSHandler(deadline)
    opener = build_opener(handler)
    try:
        with opener.open(request, timeout=remaining) as response:
            yield response
    finally:
        handler.cancel_deadline()


class GenerationProviderError(RuntimeError):
    """A safe provider failure that never includes credentials or request data."""

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


@dataclass(frozen=True)
class GenerationCostQuote:
    """Conservative maximum request cost for one exact provider prompt."""

    provider: str
    model: str
    maximum_input_tokens: int
    maximum_output_tokens: int
    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal
    pricing_revision: str

    @property
    def maximum_cost_usd(self) -> Decimal:
        return (
            Decimal(self.maximum_input_tokens) * self.input_usd_per_million_tokens
            + Decimal(self.maximum_output_tokens)
            * self.output_usd_per_million_tokens
        ) / Decimal(1_000_000)


@dataclass(frozen=True)
class GenerationUsage:
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


@dataclass(frozen=True)
class GenerationResult:
    """Provider completion and usage; content remains for JSON callers."""

    content: dict[str, Any]
    model: str
    usage: GenerationUsage
    elapsed_seconds: float
    request_id: str | None
    raw_content: str | None = None


class GenerationProvider(Protocol):
    """Shared structural contract for production and deterministic test providers."""

    provider_name: str

    def maximum_request_cost(
        self, *, system_prompt: str, user_prompt: str
    ) -> GenerationCostQuote: ...

    def generate_raw(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        timeout_seconds: float | None = None,
    ) -> GenerationResult: ...


@dataclass(frozen=True)
class CloudflareWorkersAIConfig:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float = 60.0
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url.strip().rstrip("/"))
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.cloudflare.com"
            or not parsed.path.endswith("/ai/v1")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid_cloudflare_workers_ai_base_url")
        if not self.model.strip():
            raise ValueError("empty_generation_model")
        if self.model != DEFAULT_MODEL:
            raise ValueError("unsupported_generation_model")
        if not self.api_key.strip():
            raise ValueError("empty_generation_api_key")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 300
        ):
            raise ValueError("invalid_generation_timeout")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 1 <= self.max_output_tokens <= DEFAULT_MAX_OUTPUT_TOKENS
        ):
            raise ValueError("invalid_generation_max_output_tokens")

    @classmethod
    def from_environment(cls) -> CloudflareWorkersAIConfig:
        provider = os.environ.get("WATCH_GENERATION_PROVIDER", "").strip()
        if provider != "cloudflare_workers_ai":
            raise ValueError("unsupported_generation_provider")

        base_url = os.environ.get("WATCH_GENERATION_BASE_URL", "").strip()
        model = os.environ.get("WATCH_GENERATION_MODEL", DEFAULT_MODEL).strip()
        api_key = os.environ.get("WATCH_GENERATION_API_KEY", "").strip()
        timeout_raw = os.environ.get("WATCH_GENERATION_TIMEOUT_SECONDS", "60")
        output_raw = os.environ.get(
            "WATCH_GENERATION_MAX_OUTPUT_TOKENS",
            str(DEFAULT_MAX_OUTPUT_TOKENS),
        )
        try:
            timeout_seconds = float(timeout_raw)
            max_output_tokens = int(output_raw)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid_generation_environment_configuration") from error

        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )


class CloudflareWorkersAIGenerationProvider:
    """One-request, non-streaming Cloudflare Workers AI JSON generator."""

    provider_name = "cloudflare_workers_ai"

    def __init__(self, config: CloudflareWorkersAIConfig) -> None:
        self._config = config
        self._endpoint = (
            config.base_url.strip().rstrip("/") + "/chat/completions"
        )

    @classmethod
    def from_environment(cls) -> CloudflareWorkersAIGenerationProvider:
        return cls(CloudflareWorkersAIConfig.from_environment())

    def maximum_request_cost(
        self, *, system_prompt: str, user_prompt: str
    ) -> GenerationCostQuote:
        """Quote a conservative upper bound without network side effects.

        UTF-8 byte lengths bound the prompt token count, with a fixed allowance
        for Chat Completions message framing. Input plus output must fit the
        model's published 32K context window.
        """
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("empty_generation_system_prompt")
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError("empty_generation_user_prompt")
        maximum_input_tokens = (
            len(system_prompt.encode("utf-8"))
            + len(user_prompt.encode("utf-8"))
            + CHAT_TOKEN_OVERHEAD_TOKENS
        )
        if (
            maximum_input_tokens + self._config.max_output_tokens
            > MAX_MODEL_CONTEXT_TOKENS
        ):
            raise GenerationProviderError("generation_context_budget_exceeded")
        return GenerationCostQuote(
            provider=self.provider_name,
            model=self._config.model,
            maximum_input_tokens=maximum_input_tokens,
            maximum_output_tokens=self._config.max_output_tokens,
            input_usd_per_million_tokens=INPUT_USD_PER_MILLION_TOKENS,
            output_usd_per_million_tokens=OUTPUT_USD_PER_MILLION_TOKENS,
            pricing_revision=CLOUDFLARE_PRICING_REVISION,
        )

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> GenerationResult:
        """Generate and strictly parse one JSON object for legacy callers."""
        result = self.generate_raw(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        try:
            parsed = json.loads(result.raw_content or "")
        except json.JSONDecodeError:
            raise GenerationProviderError(
                "generation_output_not_valid_json"
            ) from None
        if not isinstance(parsed, dict):
            raise GenerationProviderError("generation_output_not_json_object")
        return GenerationResult(
            content=parsed,
            model=result.model,
            usage=result.usage,
            elapsed_seconds=result.elapsed_seconds,
            request_id=result.request_id,
            raw_content=result.raw_content,
        )

    def generate_raw(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        timeout_seconds: float | None = None,
    ) -> GenerationResult:
        """Return raw completion text with validated model and usage metadata.

        Parsing is deliberately left to the application after the usage charge
        has been reconciled and durably recorded.
        """
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("empty_generation_system_prompt")
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError("empty_generation_user_prompt")
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or not 0 <= temperature <= 2
        ):
            raise ValueError("invalid_generation_temperature")
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("invalid_generation_timeout")
        request_timeout = (
            self._config.timeout_seconds
            if timeout_seconds is None
            else min(self._config.timeout_seconds, float(timeout_seconds))
        )
        request_deadline = time.monotonic() + request_timeout

        self.maximum_request_cost(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._config.max_output_tokens,
            "temperature": temperature,
            "stream": False,
        }
        request = Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        started = time.perf_counter()
        try:
            with _open_with_deadline(request, request_deadline) as response:
                document = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise GenerationProviderError(
                f"cloudflare_http_{error.code}",
                retryable=error.code in _RETRYABLE_HTTP_CODES,
            ) from None
        except (URLError, TimeoutError, OSError, IncompleteRead):
            raise GenerationProviderError(
                "cloudflare_connection_or_timeout",
                retryable=True,
            ) from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GenerationProviderError("cloudflare_invalid_json_response") from None

        elapsed = time.perf_counter() - started
        if not isinstance(document, dict):
            raise GenerationProviderError("cloudflare_invalid_response_shape")
        response_model = document.get("model")
        if response_model != self._config.model:
            raise GenerationProviderError("cloudflare_model_mismatch")

        choices = document.get("choices")
        if (
            not isinstance(choices, list)
            or not choices
            or not isinstance(choices[0], dict)
        ):
            raise GenerationProviderError("cloudflare_missing_completion_choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise GenerationProviderError("cloudflare_missing_completion_message")
        content = message.get("content")
        if not isinstance(content, str):
            raise GenerationProviderError("cloudflare_completion_not_text")

        usage_document = document.get("usage")
        if not isinstance(usage_document, dict):
            raise GenerationProviderError("generation_usage_missing")
        input_tokens = usage_document.get("prompt_tokens")
        output_tokens = usage_document.get("completion_tokens")
        if (
            isinstance(input_tokens, bool)
            or not isinstance(input_tokens, int)
            or input_tokens < 0
            or isinstance(output_tokens, bool)
            or not isinstance(output_tokens, int)
            or output_tokens < 0
        ):
            raise GenerationProviderError("generation_usage_invalid")
        total_tokens = usage_document.get("total_tokens")
        if total_tokens is not None and (
            isinstance(total_tokens, bool)
            or not isinstance(total_tokens, int)
            or total_tokens != input_tokens + output_tokens
        ):
            raise GenerationProviderError("generation_usage_inconsistent")

        estimated_cost = (
            Decimal(input_tokens) * INPUT_USD_PER_MILLION_TOKENS
            + Decimal(output_tokens) * OUTPUT_USD_PER_MILLION_TOKENS
        ) / Decimal(1_000_000)
        usage = GenerationUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
        )
        response_id = document.get("id")
        return GenerationResult(
            content={},
            model=response_model,
            usage=usage,
            elapsed_seconds=elapsed,
            request_id=response_id if isinstance(response_id, str) else None,
            raw_content=content,
        )
