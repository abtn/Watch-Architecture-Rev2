from __future__ import annotations

import json
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import core.generation as generation
from core.generation import (
    CloudflareWorkersAIConfig,
    CloudflareWorkersAIGenerationProvider,
    GenerationProviderError,
)


class FakeHTTPResponse:
    def __init__(self, document: dict[str, object]) -> None:
        self._body = json.dumps(document).encode("utf-8")

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _provider() -> CloudflareWorkersAIGenerationProvider:
    return CloudflareWorkersAIGenerationProvider(
        CloudflareWorkersAIConfig(
            base_url=(
                "https://api.cloudflare.com/client/v4/accounts/"
                "account-id/ai/v1"
            ),
            model="@cf/meta/llama-3.1-8b-instruct-fp8",
            api_key="test-token",
            timeout_seconds=12,
            max_output_tokens=512,
        )
    )


def _response(
    content: str = '{"decision":"candidate"}',
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": usage
        if usage is not None
        else {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


def test_generation_posts_once_and_returns_validated_json_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["timeout"] = timeout
        assert request.data is not None
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(_response())

    monkeypatch.setattr(generation, "urlopen", fake_urlopen)
    result = _provider().generate_json(
        system_prompt="Return JSON.",
        user_prompt="Propose one item.",
    )

    assert captured["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/account-id/ai/v1/"
        "chat/completions"
    )
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-token"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "@cf/meta/llama-3.1-8b-instruct-fp8"
    assert body["stream"] is False
    assert body["max_tokens"] == 512
    assert "response_format" not in body
    assert result.content == {"decision": "candidate"}
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.usage.estimated_cost_usd == Decimal("0.00002094")
    assert result.request_id == "chatcmpl-test"


def test_generation_fails_closed_when_usage_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "urlopen",
        lambda *_args, **_kwargs: FakeHTTPResponse(
            {
                "choices": [
                    {"message": {"content": '{"decision":"candidate"}'}}
                ]
            }
        ),
    )

    with pytest.raises(GenerationProviderError, match="generation_usage_missing"):
        _provider().generate_json(system_prompt="Return JSON.", user_prompt="Test.")


def test_generation_rejects_non_json_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "urlopen",
        lambda *_args, **_kwargs: FakeHTTPResponse(_response("Not JSON.")),
    )

    with pytest.raises(
        GenerationProviderError,
        match="generation_output_not_valid_json",
    ):
        _provider().generate_json(system_prompt="Return JSON.", user_prompt="Test.")


@pytest.mark.parametrize("status,retryable", [(401, False), (429, True), (503, True)])
def test_http_errors_are_categorized_without_retrying(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    retryable: bool,
) -> None:
    calls = 0

    def fake_urlopen(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise HTTPError(
            "https://api.cloudflare.com/",
            status,
            "provider error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(generation, "urlopen", fake_urlopen)
    with pytest.raises(GenerationProviderError) as caught:
        _provider().generate_json(system_prompt="Return JSON.", user_prompt="Test.")

    assert caught.value.retryable is retryable
    assert calls == 1


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.cloudflare.com/client/v4/accounts/x/ai/v1",
        "https://example.com/client/v4/accounts/x/ai/v1",
        "https://api.cloudflare.com/client/v4/accounts/x/ai/v1?debug=true",
        "https://user:pass@api.cloudflare.com/client/v4/accounts/x/ai/v1",
    ],
)
def test_configuration_rejects_non_cloudflare_or_unsafe_base_urls(
    base_url: str,
) -> None:
    with pytest.raises(ValueError, match="invalid_cloudflare_workers_ai_base_url"):
        CloudflareWorkersAIConfig(
            base_url=base_url,
            model="@cf/meta/llama-3.1-8b-instruct-fp8",
            api_key="test-token",
        )


def test_configuration_rejects_output_limit_above_initial_cap() -> None:
    with pytest.raises(ValueError, match="invalid_generation_max_output_tokens"):
        CloudflareWorkersAIConfig(
            base_url="https://api.cloudflare.com/client/v4/accounts/x/ai/v1",
            model="@cf/meta/llama-3.1-8b-instruct-fp8",
            api_key="test-token",
            max_output_tokens=1025,
        )
