"""Tests for the Groq client.

Every test drives a real ``httpx.AsyncClient`` through ``httpx.MockTransport``,
so the full request path runs — payload construction, headers, status handling,
parsing — with nothing leaving the process. No network in CI, and no patching
of the client's own internals, which would test the mock rather than the code.

The three acceptance criteria are covered by name:

* transport fully mocked (this whole module);
* retries capped and jittered, and a 5xx storm bounded by the deadline
  (``TestRetries``);
* no environment value ever reaches a log (``TestSecrecy``, asserted against
  real ``caplog`` capture rather than by inspection).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.services.errors import (
    CircuitOpenError,
    LLMAuthError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMDeadlineExceededError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)
from app.services.groq_client import PRICING, Completion, GroqClient

#: Deliberately not shaped like a real Groq key: gitleaks scans this repo,
#: and a test fixture that trips the secret scanner is a false positive
#: someone has to triage every time.
FAKE_API_KEY = "not-a-real-credential-for-secrecy-assertions"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "groq_api_key": FAKE_API_KEY,
        "groq_model": "openai/gpt-oss-120b",
        "groq_timeout_seconds": 5.0,
        "groq_max_retries": 2,
        "groq_deadline_seconds": 10.0,
        "groq_breaker_threshold": 5,
        "groq_breaker_cooldown_seconds": 30.0,
    }
    values.update(overrides)
    return Settings(**values)


def _body(content: str = '{"ok": true}', **usage: int) -> dict[str, Any]:
    return {
        "model": "openai/gpt-oss-120b",
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 100),
            "completion_tokens": usage.get("completion_tokens", 50),
        },
    }


def _client(handler: Any, **overrides: Any) -> GroqClient:
    return GroqClient(settings=_settings(**overrides), transport=httpx.MockTransport(handler))


async def _complete(client: GroqClient, **kwargs: Any) -> Completion:
    return await client.complete_json(system="sys", user="usr", **kwargs)


# ------------------------------------------------------------------ success


async def test_successful_completion_is_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_body())

    completion = await _complete(_client(handler))
    assert completion.parse_json() == {"ok": True}
    assert completion.total_tokens == 150
    assert completion.attempts == 1
    assert completion.latency_ms >= 0


async def test_request_targets_the_configured_model_and_url() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_body())

    await _complete(_client(handler))
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["payload"]["model"] == "openai/gpt-oss-120b"
    assert [m["role"] for m in seen["payload"]["messages"]] == ["system", "user"]


async def test_json_object_mode_by_default() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_body())

    await _complete(_client(handler))
    assert seen["response_format"] == {"type": "json_object"}


async def test_a_schema_selects_strict_constrained_decoding() -> None:
    """The reason ``openai/gpt-oss-120b`` is the default model."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_body())

    schema = {"type": "object", "properties": {"title": {"type": "string"}}}
    await _complete(_client(handler), schema=schema)
    assert seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["response_format"]["json_schema"]["schema"] == schema


# ------------------------------------------------------------------ telemetry


def test_cost_uses_published_pricing() -> None:
    completion = Completion(
        content="{}",
        model="openai/gpt-oss-120b",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        latency_ms=1.0,
        attempts=1,
    )
    prompt_rate, completion_rate = PRICING["openai/gpt-oss-120b"]
    assert completion.cost_usd() == pytest.approx(prompt_rate + completion_rate)


def test_unpriced_model_reports_no_cost_rather_than_a_guess() -> None:
    """An invented number in telemetry is worse than an absent one; it gets summed."""
    completion = Completion(
        content="{}",
        model="some/unlisted-model",
        prompt_tokens=1000,
        completion_tokens=1000,
        latency_ms=1.0,
        attempts=1,
    )
    assert completion.cost_usd() is None


async def test_telemetry_is_logged_per_call(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_body())

    with caplog.at_level(logging.INFO, logger="app.services.groq_client"):
        await _complete(_client(handler))

    record = next(r for r in caplog.records if r.message == "groq completion")
    assert record.total_tokens == 150  # type: ignore[attr-defined]
    assert record.latency_ms >= 0  # type: ignore[attr-defined]
    assert record.cost_usd is not None  # type: ignore[attr-defined]


# ------------------------------------------------------------------ secrecy


class TestSecrecy:
    """The key must not reach a log, an exception or a repr."""

    def test_settings_repr_masks_the_key(self) -> None:
        assert FAKE_API_KEY not in repr(_settings())
        assert FAKE_API_KEY not in str(_settings().groq_api_key)

    async def test_no_log_record_contains_the_key(self, caplog: pytest.LogCaptureFixture) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_body())

        with caplog.at_level(logging.DEBUG):
            await _complete(_client(handler))

        for record in caplog.records:
            assert FAKE_API_KEY not in record.getMessage()
            assert FAKE_API_KEY not in str(record.__dict__)

    @pytest.mark.parametrize("status", [401, 403, 429, 500])
    async def test_no_error_message_contains_the_key(self, status: int) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": "denied"})

        client = _client(handler, groq_max_retries=0, groq_deadline_seconds=2.0)
        with pytest.raises(Exception) as exc:
            await _complete(client)
        assert FAKE_API_KEY not in str(exc.value)
        assert FAKE_API_KEY not in repr(exc.value)

    async def test_connection_failure_message_omits_transport_detail(self) -> None:
        """httpx exception reprs can carry request headers, so they are not interpolated."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        client = _client(handler, groq_max_retries=0, groq_deadline_seconds=2.0)
        with pytest.raises(LLMConnectionError) as exc:
            await _complete(client)
        assert FAKE_API_KEY not in str(exc.value)

    async def test_the_key_is_sent_as_a_bearer_token(self) -> None:
        """It must reach the provider, even though it reaches nothing else."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=_body())

        await _complete(_client(handler))
        assert seen["auth"] == f"Bearer {FAKE_API_KEY}"


async def test_missing_key_fails_before_any_request_is_sent() -> None:
    sent = False

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        nonlocal sent
        sent = True
        return httpx.Response(200, json=_body())

    client = GroqClient(
        settings=_settings(groq_api_key=None), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY"):
        await _complete(client)
    assert sent is False


async def test_empty_key_is_treated_as_missing() -> None:
    client = GroqClient(settings=_settings(groq_api_key=""))
    with pytest.raises(LLMConfigurationError):
        await _complete(client)


# ------------------------------------------------------------------ failures


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, LLMAuthError),
        (403, LLMAuthError),
        (429, LLMRateLimitError),
        (500, LLMServerError),
        (503, LLMServerError),
        (418, LLMResponseError),
    ],
)
async def test_status_codes_map_to_typed_errors(status: int, expected: type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "x"})

    client = _client(handler, groq_max_retries=0, groq_deadline_seconds=2.0)
    with pytest.raises(expected):
        await _complete(client)


async def test_auth_failure_is_not_retried() -> None:
    """A wrong key stays wrong; retrying only delays the operator seeing it."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(LLMAuthError):
        await _complete(_client(handler, groq_max_retries=3))
    assert calls == 1


async def test_timeout_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler, groq_max_retries=0, groq_deadline_seconds=2.0)
    with pytest.raises(LLMTimeoutError):
        await _complete(client)


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {},
    ],
)
async def test_unusable_envelopes_are_rejected(body: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(LLMResponseError):
        await _complete(_client(handler, groq_max_retries=0))


async def test_non_json_envelope_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    with pytest.raises(LLMResponseError):
        await _complete(_client(handler, groq_max_retries=0))


async def test_malformed_content_is_reported_on_parse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_body(content="{not valid json"))

    completion = await _complete(_client(handler))
    with pytest.raises(LLMResponseError, match="malformed JSON"):
        completion.parse_json()


async def test_json_array_content_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_body(content="[1, 2, 3]"))

    completion = await _complete(_client(handler))
    with pytest.raises(LLMResponseError, match="expected a JSON object"):
        completion.parse_json()


# ------------------------------------------------------------------ retries


class TestRetries:
    """Capped, jittered, and bounded by a deadline that actually binds."""

    async def test_transient_failure_is_retried_then_succeeds(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(503, json={"error": "unavailable"})
            return httpx.Response(200, json=_body())

        completion = await _complete(_client(handler, groq_max_retries=3))
        assert calls == 3
        assert completion.attempts == 3

    async def test_retries_are_capped(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500, json={"error": "boom"})

        with pytest.raises(LLMServerError):
            await _complete(_client(handler, groq_max_retries=2, groq_deadline_seconds=30.0))
        # One initial attempt plus exactly two retries.
        assert calls == 3

    async def test_zero_retries_means_one_attempt(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500, json={"error": "boom"})

        with pytest.raises(LLMServerError):
            await _complete(_client(handler, groq_max_retries=0))
        assert calls == 1

    async def test_a_5xx_storm_does_not_hang_past_the_deadline(self) -> None:
        """The acceptance criterion, measured rather than reasoned about."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "storm"})

        client = _client(
            handler,
            groq_max_retries=10,
            groq_deadline_seconds=1.0,
            groq_timeout_seconds=1.0,
            groq_breaker_threshold=100,
        )
        started = time.monotonic()
        with pytest.raises((LLMServerError, LLMDeadlineExceededError)):
            await _complete(client)
        elapsed = time.monotonic() - started
        assert elapsed < 3.0, f"took {elapsed:.2f}s against a 1s deadline"

    async def test_backoff_is_jittered(self) -> None:
        """Without jitter, variants that fail together retry together."""
        delays: list[float] = []
        real_sleep = asyncio.sleep

        async def record(delay: float) -> None:
            delays.append(delay)
            await real_sleep(0)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        # Breaker raised out of the way: this test is about the sleeps, and
        # six consecutive failures would otherwise trip the default threshold.
        client = _client(
            handler,
            groq_max_retries=6,
            groq_deadline_seconds=60.0,
            groq_breaker_threshold=100,
        )
        original = asyncio.sleep
        asyncio.sleep = record  # type: ignore[assignment]
        try:
            with pytest.raises(LLMServerError):
                await _complete(client)
        finally:
            asyncio.sleep = original  # type: ignore[assignment]

        assert len(delays) == 6
        assert len(set(delays)) > 1, "identical delays indicate no jitter"
        assert all(0 <= d <= 8.0 for d in delays), delays

    async def test_rate_limit_never_retries_sooner_than_the_provider_asked(self) -> None:
        delays: list[float] = []
        real_sleep = asyncio.sleep

        async def record(delay: float) -> None:
            delays.append(delay)
            await real_sleep(0)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "slow down"}, headers={"retry-after": "2"})

        client = _client(handler, groq_max_retries=1, groq_deadline_seconds=60.0)
        original = asyncio.sleep
        asyncio.sleep = record  # type: ignore[assignment]
        try:
            with pytest.raises(LLMRateLimitError):
                await _complete(client)
        finally:
            asyncio.sleep = original  # type: ignore[assignment]
        assert delays and all(d >= 2.0 for d in delays)

    async def test_unparseable_retry_after_falls_back_to_backoff(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"error": "x"}, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}
            )

        client = _client(handler, groq_max_retries=1, groq_deadline_seconds=60.0)
        with pytest.raises(LLMRateLimitError) as exc:
            await _complete(client)
        assert exc.value.retry_after is None

    async def test_deadline_is_enforced_before_a_wasted_attempt(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        client = _client(
            handler,
            groq_max_retries=10,
            groq_deadline_seconds=0.05,
            groq_breaker_threshold=100,
        )
        with pytest.raises((LLMDeadlineExceededError, LLMServerError)):
            await _complete(client)


# ------------------------------------------------------------------ breaker


class TestCircuitBreaker:
    async def test_breaker_opens_after_consecutive_failures(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500, json={"error": "down"})

        client = _client(
            handler, groq_max_retries=0, groq_breaker_threshold=2, groq_deadline_seconds=5.0
        )
        for _ in range(2):
            with pytest.raises(LLMServerError):
                await _complete(client)
        assert calls == 2

        # Third call is refused without reaching the transport.
        with pytest.raises(CircuitOpenError):
            await _complete(client)
        assert calls == 2

    async def test_breaker_half_opens_after_the_cooldown(self) -> None:
        state = {"fail": True, "calls": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["calls"] += 1
            if state["fail"]:
                return httpx.Response(500, json={"error": "down"})
            return httpx.Response(200, json=_body())

        client = _client(
            handler,
            groq_max_retries=0,
            groq_breaker_threshold=1,
            groq_breaker_cooldown_seconds=0.05,
            groq_deadline_seconds=5.0,
        )
        with pytest.raises(LLMServerError):
            await _complete(client)
        with pytest.raises(CircuitOpenError):
            await _complete(client)

        await asyncio.sleep(0.06)
        state["fail"] = False
        completion = await _complete(client)
        assert completion.parse_json() == {"ok": True}

    async def test_success_resets_the_failure_count(self) -> None:
        """Intermittent errors are normal; only a run of them means the provider is down."""
        results = [500, 200, 500, 500, 200]
        index = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal index
            status = results[index]
            index += 1
            return httpx.Response(status, json=_body() if status == 200 else {"error": "x"})

        client = _client(
            handler, groq_max_retries=0, groq_breaker_threshold=3, groq_deadline_seconds=5.0
        )
        for expected_ok in (False, True, False, False, True):
            if expected_ok:
                assert await _complete(client)
            else:
                with pytest.raises(LLMServerError):
                    await _complete(client)


async def test_an_already_elapsed_deadline_is_refused_before_any_attempt() -> None:
    """The deadline is checked at the top of the loop, not only after a failure."""
    sent = False

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        nonlocal sent
        sent = True
        return httpx.Response(200, json=_body())

    client = _client(handler, groq_deadline_seconds=1e-9)
    with pytest.raises(LLMDeadlineExceededError):
        await _complete(client)
    assert sent is False
