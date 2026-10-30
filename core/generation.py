"""Stateless Cloudflare Workers AI generation over Chat Completions.

The adapter returns only the final JSON object and provider usage metadata. It
never exposes or persists reasoning traces, tool calls, prompts, or raw response
bodies. Each call makes exactly one HTTP request; retry policy belongs to the
ordinary Task attempt boundary, not this provider adapter.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8"
DEFAULT_MAX_OUTPUT_TOKENS = 1024
INPUT_USD_PER_MILLION_TOKENS = Decimal("0.152")
OUTPUT_USD_PER_MILLION_TOKENS = Decimal("0.287")
_RETRYABLE_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class GenerationProviderError(RuntimeError):
    """A safe provider failure that never includes credentials or request data."""

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


@dataclass(frozen=True)
class GenerationUsage:
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


@dataclass(frozen=True)
class GenerationResult:
    """Validated final JSON output plus the provider's usage accounting."""

    content: dict[str, Any]
    model: str
    usage: GenerationUsage
    elapsed_seconds: float
    request_id: str | None


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

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> GenerationResult:
        """Generate one JSON object; reject non-JSON or usage-less responses.

        The selected FP8 model is not listed in Cloudflare's published JSON Mode
        compatibility list. We therefore request JSON in the system prompt and
        validate the returned object locally instead of sending response_format.
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
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                document = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise GenerationProviderError(
                f"cloudflare_http_{error.code}",
                retryable=error.code in _RETRYABLE_HTTP_CODES,
            ) from None
        except (URLError, TimeoutError, OSError):
            raise GenerationProviderError(
                "cloudflare_connection_or_timeout",
                retryable=True,
            ) from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GenerationProviderError("cloudflare_invalid_json_response") from None

        elapsed = time.perf_counter() - started
        if not isinstance(document, dict):
            raise GenerationProviderError("cloudflare_invalid_response_shape")

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
        if not isinstance(content, str) or not content.strip():
            raise GenerationProviderError("cloudflare_empty_completion")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            raise GenerationProviderError("generation_output_not_valid_json") from None
        if not isinstance(parsed, dict):
            raise GenerationProviderError("generation_output_not_json_object")

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
            content=parsed,
            model=self._config.model,
            usage=usage,
            elapsed_seconds=elapsed,
            request_id=response_id if isinstance(response_id, str) else None,
        )
