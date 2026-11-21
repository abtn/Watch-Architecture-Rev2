from __future__ import annotations

import json
import time
from contextlib import nullcontext
from decimal import Decimal
from http.client import IncompleteRead
from threading import BoundedSemaphore, Event, Lock, Thread, current_thread
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import core.generation as generation
from core.generation import (
    CloudflareWorkersAIConfig,
    CloudflareWorkersAIGenerationProvider,
    GenerationCostQuote,
    GenerationProviderError,
)
from core.update_thread import MAX_ATTEMPTS, TASK_BUDGET


class FakeHTTPResponse:
    def __init__(self, document: dict[str, object]) -> None:
        self._body = json.dumps(document).encode("utf-8")

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _provider(
    timeout_seconds: float = 12.0,
) -> CloudflareWorkersAIGenerationProvider:
    return CloudflareWorkersAIGenerationProvider(
        CloudflareWorkersAIConfig(
            base_url=(
                "https://api.cloudflare.com/client/v4/accounts/"
                "account-id/ai/v1"
            ),
            model="@cf/meta/llama-3.1-8b-instruct-fp8",
            api_key="test-token",
            timeout_seconds=timeout_seconds,
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

    def fake_urlopen(request: Request, deadline: float) -> FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["deadline"] = deadline
        assert request.data is not None
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(_response())

    monkeypatch.setattr(generation, "_open_with_deadline", fake_urlopen)
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


def test_absolute_generation_deadline_bounds_slow_dns_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deadline_seconds = 0.2
    deadline_tolerance = 0.2
    dns_started = Event()
    dns_release = Event()
    dns_finished = Event()
    caller_finished = Event()
    dns_worker: list[Thread] = []
    connection_holder: list[generation._DeadlineHTTPSConnection] = []
    connection_started_at: list[float] = []
    errors: list[BaseException] = []

    def slow_dns(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        dns_worker.append(current_thread())
        dns_started.set()
        dns_release.wait()
        dns_finished.set()
        return []

    monkeypatch.setattr(generation.socket, "getaddrinfo", slow_dns)

    def connect() -> None:
        try:
            connection_started_at.append(time.monotonic())
            connection = generation._DeadlineHTTPSConnection(
                "api.cloudflare.com",
                timeout=1.0,
                deadline=connection_started_at[0] + deadline_seconds,
            )
            connection_holder.append(connection)
            connection.connect()
        except BaseException as error:
            errors.append(error)
        finally:
            caller_finished.set()

    caller = Thread(target=connect, daemon=True)

    try:
        caller.start()
        assert dns_started.wait(timeout=0.5)
        assert not caller_finished.is_set()
        assert not dns_finished.is_set()
        assert caller_finished.wait(timeout=deadline_seconds + deadline_tolerance)
        assert len(errors) == 1
        assert isinstance(errors[0], TimeoutError)
        assert "generation_deadline_exceeded" in str(errors[0])
        assert (
            time.monotonic() - connection_started_at[0]
            < deadline_seconds + deadline_tolerance
        )
        assert not dns_finished.is_set()
    finally:
        dns_release.set()
        if dns_worker:
            dns_finished.wait(timeout=0.5)
            dns_worker[0].join(timeout=0.5)
        caller.join(timeout=0.5)
        if connection_holder:
            connection_holder[0].cancel_deadline()
        assert not caller.is_alive()
        if dns_worker:
            assert dns_finished.is_set()
            assert not dns_worker[0].is_alive()



def test_repeated_stalled_dns_resolution_is_process_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity = generation.DNS_RESOLVER_CONCURRENCY_LIMIT
    monkeypatch.setattr(
        generation,
        "_DNS_RESOLVER_SLOTS",
        BoundedSemaphore(capacity),
    )
    dns_release = Event()
    capacity_reached = Event()
    workers: list[Thread] = []
    workers_lock = Lock()
    active_workers = 0
    maximum_active_workers = 0
    errors: dict[int, BaseException] = {}
    callers: dict[int, Thread] = {}
    finished: dict[int, Event] = {}

    def slow_dns(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        nonlocal active_workers, maximum_active_workers
        with workers_lock:
            active_workers += 1
            maximum_active_workers = max(maximum_active_workers, active_workers)
            workers.append(current_thread())
            if active_workers == capacity:
                capacity_reached.set()
        dns_release.wait()
        with workers_lock:
            active_workers -= 1
        return []

    monkeypatch.setattr(generation.socket, "getaddrinfo", slow_dns)

    def connect(index: int) -> None:
        connection = generation._DeadlineHTTPSConnection(
            "api.cloudflare.com",
            timeout=1.0,
            deadline=time.monotonic() + 0.2,
        )
        try:
            connection.connect()
        except BaseException as error:
            errors[index] = error
        finally:
            connection.cancel_deadline()
            finished[index].set()

    try:
        for index in range(capacity):
            finished[index] = Event()
            callers[index] = Thread(target=connect, args=(index,), daemon=True)
            callers[index].start()

        assert capacity_reached.wait(timeout=0.5)
        assert len(workers) == capacity
        assert maximum_active_workers == capacity

        for index in range(capacity, capacity + 8):
            finished[index] = Event()
            callers[index] = Thread(target=connect, args=(index,), daemon=True)
            callers[index].start()

        for index in range(capacity, capacity + 8):
            assert finished[index].wait(timeout=0.2)
            assert isinstance(errors[index], generation._DNSResolverCapacityError)

        for index in range(capacity):
            assert finished[index].wait(timeout=0.6)
            assert isinstance(errors[index], TimeoutError)

        # Timed-out callers must not release capacity while getaddrinfo is
        # still blocked. Further requests remain rejected without new workers.
        for index in range(capacity + 8, capacity + 16):
            finished[index] = Event()
            callers[index] = Thread(target=connect, args=(index,), daemon=True)
            callers[index].start()
            assert finished[index].wait(timeout=0.2)
            assert isinstance(errors[index], generation._DNSResolverCapacityError)

        assert len(workers) == capacity
        assert maximum_active_workers == capacity
        assert active_workers == capacity
    finally:
        dns_release.set()
        for caller in callers.values():
            caller.join(timeout=0.5)
        for worker in workers:
            worker.join(timeout=0.5)

    assert all(not caller.is_alive() for caller in callers.values())
    assert all(not worker.is_alive() for worker in workers)
    assert active_workers == 0

    # Capacity is reclaimed only after the resolver workers actually finish.
    acquired = [
        generation._DNS_RESOLVER_SLOTS.acquire(blocking=False)
        for _ in range(capacity)
    ]
    assert all(acquired)
    for _ in acquired:
        generation._DNS_RESOLVER_SLOTS.release()


def test_provider_preserves_dns_capacity_exhaustion_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_with_capacity_error(*_args: object, **_kwargs: object) -> None:
        raise URLError(
            generation._DNSResolverCapacityError(
                "generation_dns_resolver_capacity_exhausted"
            )
        )

    monkeypatch.setattr(generation, "_open_with_deadline", fail_with_capacity_error)

    with pytest.raises(GenerationProviderError) as caught:
        _provider().generate_raw(
            system_prompt="Return JSON.",
            user_prompt="Test DNS capacity exhaustion.",
        )

    assert caught.value.reason == "generation_dns_resolver_capacity_exhausted"
    assert caught.value.retryable is True


@pytest.mark.parametrize("blocked_phase", ["tcp", "tls"])
def test_absolute_generation_deadline_interrupts_tcp_and_tls(
    monkeypatch: pytest.MonkeyPatch,
    blocked_phase: str,
) -> None:
    closed = Event()
    tls_started = Event()

    class BlockingSocket:
        def settimeout(self, _timeout: float) -> None:
            return None

        def bind(self, _address: object) -> None:
            return None

        def connect(self, _address: object) -> None:
            if blocked_phase == "tcp":
                assert closed.wait(timeout=0.5)
                raise OSError("socket closed at deadline")

        def shutdown(self, _how: int) -> None:
            closed.set()

        def close(self) -> None:
            closed.set()

    connection_socket = BlockingSocket()

    class BlockingTLSContext:
        def wrap_socket(
            self,
            sock: BlockingSocket,
            *,
            server_hostname: str,
        ) -> BlockingSocket:
            assert server_hostname == "api.cloudflare.com"
            tls_started.set()
            assert closed.wait(timeout=0.5)
            raise OSError("TLS socket closed at deadline")

    monkeypatch.setattr(
        generation.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                generation.socket.AF_INET,
                generation.socket.SOCK_STREAM,
                0,
                "",
                ("127.0.0.1", 443),
            )
        ],
    )
    monkeypatch.setattr(
        generation.socket,
        "socket",
        lambda *_args, **_kwargs: connection_socket,
    )
    connection = generation._DeadlineHTTPSConnection(
        "api.cloudflare.com",
        timeout=1.0,
        deadline=time.monotonic() + 0.12,
    )
    connection._context = BlockingTLSContext()  # type: ignore[assignment]
    started = time.monotonic()

    try:
        with pytest.raises(TimeoutError, match="generation_deadline_exceeded"):
            connection.connect()
        assert time.monotonic() - started < 0.30
        if blocked_phase == "tls":
            assert tls_started.is_set()
        assert closed.is_set()
    finally:
        connection.cancel_deadline()


def test_absolute_deadline_rejects_send_after_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def settimeout(self, _timeout: float) -> None:
            return None

    connection = generation._DeadlineHTTPSConnection(
        "api.cloudflare.com",
        timeout=1.0,
        deadline=time.monotonic() - 0.001,
    )
    connection.sock = FakeSocket()  # type: ignore[assignment]

    with pytest.raises(TimeoutError, match="generation_deadline_exceeded"):
        connection.send(b"POST / HTTP/1.1\r\n")


def test_absolute_deadline_closes_socket_during_response_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_socket, peer_socket = generation.socket.socketpair()

    class ConnectedSocket:
        def settimeout(self, timeout: float) -> None:
            client_socket.settimeout(timeout)

        def connect(self, _address: object) -> None:
            return None

        def shutdown(self, how: int) -> None:
            client_socket.shutdown(how)

        def close(self) -> None:
            client_socket.close()

    class PassthroughTLSContext:
        def wrap_socket(
            self,
            sock: ConnectedSocket,
            *,
            server_hostname: str,
        ) -> ConnectedSocket:
            assert server_hostname == "api.cloudflare.com"
            return sock

    monkeypatch.setattr(
        generation.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                generation.socket.AF_INET,
                generation.socket.SOCK_STREAM,
                0,
                "",
                ("127.0.0.1", 443),
            )
        ],
    )
    monkeypatch.setattr(
        generation.socket,
        "socket",
        lambda *_args, **_kwargs: ConnectedSocket(),
    )
    connection = generation._DeadlineHTTPSConnection(
        "api.cloudflare.com",
        timeout=1.0,
        deadline=time.monotonic() + 0.05,
    )
    connection._context = PassthroughTLSContext()  # type: ignore[assignment]

    try:
        connection.connect()
        peer_socket.settimeout(0.5)
        assert peer_socket.recv(1) == b""
    finally:
        connection.cancel_deadline()
        client_socket.close()
        peer_socket.close()


@pytest.mark.parametrize(
    ("provider_timeout", "call_timeout", "task_deadline", "expected_deadline"),
    [
        (12.0, 30.0, 145.0, 112.0),
        (60.0, 30.0, 145.0, 130.0),
        (60.0, 30.0, 115.0, 115.0),
    ],
)
def test_provider_uses_earliest_absolute_or_relative_deadline(
    monkeypatch: pytest.MonkeyPatch,
    provider_timeout: float,
    call_timeout: float,
    task_deadline: float,
    expected_deadline: float,
) -> None:
    captured: dict[str, float] = {}

    def open_at_deadline(request: Request, deadline: float):
        captured["deadline"] = deadline
        return nullcontext(FakeHTTPResponse(_response()))

    monkeypatch.setattr(generation, "_open_with_deadline", open_at_deadline)
    monkeypatch.setattr(generation.time, "monotonic", lambda: 100.0)

    _provider(timeout_seconds=provider_timeout).generate_raw(
        system_prompt="Return JSON.",
        user_prompt="Propose one item.",
        timeout_seconds=call_timeout,
        deadline_monotonic=task_deadline,
    )

    assert captured["deadline"] == expected_deadline


def test_incomplete_http_response_is_a_retryable_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IncompleteResponse(FakeHTTPResponse):
        def read(self) -> bytes:
            raise IncompleteRead(b'{"choices":', 128)

    monkeypatch.setattr(
        generation,
        "_open_with_deadline",
        lambda *_args, **_kwargs: IncompleteResponse(_response()),
    )

    with pytest.raises(GenerationProviderError) as caught:
        _provider().generate_raw(
            system_prompt="Return JSON.",
            user_prompt="Propose one item.",
        )

    assert caught.value.reason == "cloudflare_connection_or_timeout"
    assert caught.value.retryable is True


def test_generation_raw_uses_the_smaller_per_call_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, deadline: float) -> FakeHTTPResponse:
        captured["remaining"] = deadline - time.monotonic()
        return FakeHTTPResponse(_response())

    monkeypatch.setattr(generation, "_open_with_deadline", fake_urlopen)
    result = _provider().generate_raw(
        system_prompt="Return JSON.",
        user_prompt="Propose one item.",
        timeout_seconds=4.0,
    )

    assert result.raw_content == '{"decision":"candidate"}'
    assert 0 < captured["remaining"] <= 4.0


def test_generation_fails_closed_when_usage_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "_open_with_deadline",
        lambda *_args, **_kwargs: FakeHTTPResponse(
            {
                "model": generation.DEFAULT_MODEL,
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
        "_open_with_deadline",
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

    monkeypatch.setattr(generation, "_open_with_deadline", fake_urlopen)
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



def test_initial_provider_quotes_conservative_maximum_without_a_request() -> None:
    quote = _provider().maximum_request_cost(
        system_prompt="Return one JSON object.",
        user_prompt='{"objective":"gather evidence"}',
    )

    expected_input = (
        len("Return one JSON object.".encode("utf-8"))
        + len('{"objective":"gather evidence"}'.encode("utf-8"))
        + generation.CHAT_TOKEN_OVERHEAD_TOKENS
    )
    expected_cost = (
        Decimal(expected_input) * generation.INPUT_USD_PER_MILLION_TOKENS
        + Decimal(512) * generation.OUTPUT_USD_PER_MILLION_TOKENS
    ) / Decimal(1_000_000)
    assert quote.provider == "cloudflare_workers_ai"
    assert quote.model == generation.DEFAULT_MODEL
    assert quote.maximum_input_tokens == expected_input
    assert quote.maximum_output_tokens == 512
    assert quote.maximum_cost_usd == expected_cost


def test_three_maximum_update_thread_reservations_fit_task_cost_ceiling() -> None:
    quote = GenerationCostQuote(
        provider="cloudflare_workers_ai",
        model=generation.DEFAULT_MODEL,
        maximum_input_tokens=30_976,
        maximum_output_tokens=1_024,
        input_usd_per_million_tokens=generation.INPUT_USD_PER_MILLION_TOKENS,
        output_usd_per_million_tokens=generation.OUTPUT_USD_PER_MILLION_TOKENS,
        pricing_revision=generation.CLOUDFLARE_PRICING_REVISION,
    )

    assert generation.CHAT_TOKEN_OVERHEAD_TOKENS == 128
    assert generation.DEFAULT_MAX_OUTPUT_TOKENS == 1_024
    assert (
        quote.maximum_input_tokens + quote.maximum_output_tokens
        == generation.MAX_MODEL_CONTEXT_TOKENS
    )
    assert quote.maximum_cost_usd == Decimal("0.00500224")
    three_attempt_reservations = quote.maximum_cost_usd * 3
    assert three_attempt_reservations == Decimal("0.01500672")
    task_ceiling = Decimal(str(TASK_BUDGET["max_cost_usd"]))
    assert task_ceiling == Decimal("0.02")
    assert MAX_ATTEMPTS == 3
    assert three_attempt_reservations < task_ceiling


def test_initial_provider_rejects_a_model_without_a_pinned_price_card() -> None:
    with pytest.raises(ValueError, match="unsupported_generation_model"):
        CloudflareWorkersAIConfig(
            base_url="https://api.cloudflare.com/client/v4/accounts/x/ai/v1",
            model="@cf/meta/different-model",
            api_key="test-token",
        )



def test_generation_fails_closed_when_provider_returns_a_different_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _response()
    document["model"] = "@cf/meta/different-model"
    monkeypatch.setattr(
        generation,
        "_open_with_deadline",
        lambda *_args, **_kwargs: FakeHTTPResponse(document),
    )

    with pytest.raises(GenerationProviderError, match="cloudflare_model_mismatch"):
        _provider().generate_json(
            system_prompt="Return JSON.",
            user_prompt="Propose one item.",
        )


def test_generation_raw_returns_malformed_completion_with_validated_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "_open_with_deadline",
        lambda *_args, **_kwargs: FakeHTTPResponse(_response("Not JSON.")),
    )

    result = _provider().generate_raw(
        system_prompt="Return JSON.",
        user_prompt="Test raw completion handling.",
    )

    assert result.raw_content == "Not JSON."
    assert result.content == {}
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.request_id == "chatcmpl-test"
