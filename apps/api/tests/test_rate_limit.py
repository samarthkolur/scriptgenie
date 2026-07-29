"""Tests for rate limiting, the concurrency cap, body size and usage accounting.

Four protections against four different failure modes. The tests are grouped
the same way, because a test file that mixed them would make it easy to believe
one of them covered another.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core import usage
from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.security import AuthenticatedUser
from app.db.supabase import SupabaseClient
from app.main import API_V1_PREFIX
from app.services.groq_client import GroqClient
from app.services.rate_limit import enforce_generation_limit, record_generation_usage
from tests.api_fixtures import (
    CLEAN_BUNDLE,
    CLEAN_EXTRACTION,
    OWNER_ID,
    PROJECT_ID,
    GroqStub,
    harness,
    project_row,
    run_row,
    variant_payload,
)
from tests.auth_fixtures import PostgrestStub, settings


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=OWNER_ID, email=None, role="authenticated", access_token="verified-token"
    )


def _counting_db(used: int) -> PostgrestStub:
    return PostgrestStub().on(
        "GET",
        "generation_runs",
        httpx.Response(200, json=[], headers={"content-range": f"0-0/{used}"}),
    )


def _client(stub: PostgrestStub) -> SupabaseClient:
    return SupabaseClient(settings(), transport=stub.transport())


# ------------------------------------------------------------- the limit


async def test_a_caller_inside_their_allowance_is_let_through() -> None:
    stub = _counting_db(used=9)
    configured = settings(rate_limit_generations_per_window=10)

    await enforce_generation_limit(_client(stub), _user(), configured)


async def test_a_caller_at_their_allowance_is_refused() -> None:
    stub = _counting_db(used=10)
    configured = settings(rate_limit_generations_per_window=10)

    with pytest.raises(RateLimitedError) as raised:
        await enforce_generation_limit(_client(stub), _user(), configured)

    assert raised.value.extra["used"] == 10
    assert raised.value.extra["limit"] == 10


async def test_the_limit_is_counted_over_a_rolling_window() -> None:
    """Rolling, not fixed: allowance returns gradually as runs age out, rather
    than all at once on the hour."""
    stub = _counting_db(used=0)
    configured = settings(rate_limit_generations_per_window=10, rate_limit_window_seconds=3600)

    before = datetime.now(UTC)
    await enforce_generation_limit(_client(stub), _user(), configured)

    filter_value = stub.last("GET", "generation_runs").url.params["created_at"]
    assert filter_value.startswith("gte.")
    since = datetime.fromisoformat(filter_value.removeprefix("gte."))
    assert timedelta(seconds=3595) < before - since < timedelta(seconds=3605)


async def test_the_limit_is_counted_in_the_database_not_in_memory() -> None:
    """An in-process counter doubles every user's allowance for each extra
    instance and resets on restart, which makes the limit loosest exactly when
    the service is least healthy."""
    stub = _counting_db(used=10)
    configured = settings(rate_limit_generations_per_window=10)

    for _ in range(3):
        with pytest.raises(RateLimitedError):
            await enforce_generation_limit(_client(stub), _user(), configured)
        stub.responses.setdefault("GET generation_runs", []).append(
            httpx.Response(200, json=[], headers={"content-range": "0-0/10"})
        )

    # Three separate client objects would each have their own in-memory
    # counter; the database answered all three the same way.
    assert len([r for r in stub.requests if r.method == "GET"]) == 3


async def test_a_limit_of_zero_disables_the_check_rather_than_refusing_everything() -> None:
    """Zero is how an operator turns a limit off. A service that refused every
    request is never what setting a limit was meant to do."""
    stub = _counting_db(used=999)
    configured = settings(rate_limit_generations_per_window=0)

    await enforce_generation_limit(_client(stub), _user(), configured)

    assert stub.requests == [], "a disabled limit must not even pay for the count"


async def test_the_refusal_names_the_window_in_words() -> None:
    stub = _counting_db(used=10)

    with pytest.raises(RateLimitedError, match="hour"):
        await enforce_generation_limit(
            _client(stub),
            _user(),
            settings(rate_limit_generations_per_window=10, rate_limit_window_seconds=3600),
        )


@pytest.mark.parametrize(
    ("window", "expected"),
    [(3600, "hour"), (7200, "2 hours"), (60, "minute"), (900, "15 minutes"), (90, "90 seconds")],
)
async def test_the_window_is_described_in_units_a_person_reads(window: int, expected: str) -> None:
    stub = _counting_db(used=1)

    with pytest.raises(RateLimitedError, match=expected):
        await enforce_generation_limit(
            _client(stub),
            _user(),
            settings(rate_limit_generations_per_window=1, rate_limit_window_seconds=window),
        )


async def test_retry_after_is_shorter_than_the_window() -> None:
    """Telling a caller to wait an hour when their oldest run ages out in four
    minutes is safe and useless, and a client told a useless number ignores it."""
    stub = _counting_db(used=10)
    configured = settings(rate_limit_generations_per_window=10, rate_limit_window_seconds=3600)

    with pytest.raises(RateLimitedError) as raised:
        await enforce_generation_limit(_client(stub), _user(), configured)

    assert 0 < raised.value.retry_after_seconds < 3600
    assert raised.value.retry_after_seconds == 360


async def test_retry_after_is_never_zero() -> None:
    """A Retry-After of 0 tells a client to retry immediately into the same 429."""
    stub = _counting_db(used=100)
    configured = settings(rate_limit_generations_per_window=100, rate_limit_window_seconds=10)

    with pytest.raises(RateLimitedError) as raised:
        await enforce_generation_limit(_client(stub), _user(), configured)

    assert raised.value.retry_after_seconds >= 1


# ---------------------------------------------------- the limit at the route


def _quota_db(used: int) -> PostgrestStub:
    return (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on(
            "GET",
            "generation_runs",
            httpx.Response(200, json=[], headers={"content-range": f"0-0/{used}"}),
        )
    )


def test_exceeding_the_limit_returns_429_with_retry_after() -> None:
    api = harness(_quota_db(used=10), **{"rate_limit_generations_per_window": 10})

    response = api.post(f"/projects/{PROJECT_ID}/generate", json={"bundle": CLEAN_BUNDLE})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "360"
    body = response.json()
    assert body["type"].endswith("/rate-limited")
    assert body["limit"] == 10
    assert body["used"] == 10


def test_a_rate_limited_request_consumes_no_model_quota() -> None:
    """The stated criterion. The refusal costs one counting query and nothing
    else — no tokens, no rows."""
    api = harness(_quota_db(used=10), **{"rate_limit_generations_per_window": 10})

    api.post(f"/projects/{PROJECT_ID}/generate", json={"bundle": CLEAN_BUNDLE})

    assert api.groq.calls == []
    assert {r.method for r in api.db.requests} == {"GET"}


def test_a_request_inside_the_allowance_proceeds() -> None:
    """Without this, the test above would also pass against a limiter that
    refused everything."""
    from tests.test_api_v1 import _generation_db

    api = harness(
        _generation_db(variants=1),
        GroqStub(variants=[variant_payload()], extraction=CLEAN_EXTRACTION),
        **{"rate_limit_generations_per_window": 10},
    )

    response = api.post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 1},
    )

    assert response.status_code == 200


# ------------------------------------------------------- usage accounting


def _usage_db(variants: int = 1) -> PostgrestStub:
    from tests.test_api_v1 import _generation_db

    return _generation_db(variants=variants).on(
        "POST", "usage_events", httpx.Response(201, json=[])
    )


def test_a_usage_row_is_written_for_every_generation_run() -> None:
    api = harness(
        _usage_db(),
        GroqStub(variants=[variant_payload()], extraction=CLEAN_EXTRACTION),
    )

    api.post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 1},
    )

    written = json.loads(api.db.last("POST", "usage_events").content)
    assert written["event_type"] == "generation"
    assert written["owner_id"] == str(OWNER_ID)


def test_the_usage_row_totals_every_call_the_run_made() -> None:
    """One variant call plus one verification extraction. A row recording only
    the last would understate the run by half."""
    api = harness(
        _usage_db(),
        GroqStub(variants=[variant_payload()], extraction=CLEAN_EXTRACTION),
    )

    api.post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 1},
    )

    written = json.loads(api.db.last("POST", "usage_events").content)
    # The stub reports 800 prompt / 400 completion tokens per call.
    assert written["prompt_tokens"] == 1600
    assert written["completion_tokens"] == 800
    assert written["cost_usd"] > 0


def test_the_usage_row_is_written_under_the_service_role() -> None:
    """usage_events denies every client. An account that could write its own
    accounting could understate its spend."""
    api = harness(
        _usage_db(),
        GroqStub(variants=[variant_payload()], extraction=CLEAN_EXTRACTION),
    )

    api.post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 1},
    )

    headers = api.db.last("POST", "usage_events").headers
    assert headers["authorization"] == "Bearer service-role-key-for-tests"


async def test_a_failed_accounting_write_never_costs_the_caller_their_variants() -> None:
    """The tokens were spent and the variants exist. Losing the response
    because the accounting write failed would charge for nothing."""
    stub = PostgrestStub().on("POST", "usage_events", httpx.Response(500, json={"m": "down"}))
    from app.api.v1 import presenters

    response = __import__("app.api.v1.schemas", fromlist=["x"]).GenerationResponse(
        run=presenters.generation_run(run_row()),
        envelope=_any_envelope(),
        variants=(),
        failures=(),
    )

    await record_generation_usage(
        _client(stub),
        _user(),
        PROJECT_ID,
        response,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=None,
    )


def _any_envelope():
    from app.domain import ConstraintBundle
    from app.engines.conflict_detector import detect
    from app.engines.resolution import apply_resolutions
    from app.engines.scope_parameterizer import parameterize
    from app.kb.loader import get_knowledge_base

    kb = get_knowledge_base()
    bundle = ConstraintBundle.model_validate(CLEAN_BUNDLE)
    return parameterize(apply_resolutions(detect(bundle, kb), (), kb), kb)


# ----------------------------------------------------------------- the meter


def test_the_meter_totals_across_calls() -> None:
    with usage.measured() as meter:
        usage.record(model="m", prompt_tokens=100, completion_tokens=50, cost_usd=0.001)
        usage.record(model="m", prompt_tokens=200, completion_tokens=25, cost_usd=0.002)

    assert meter.prompt_tokens == 300
    assert meter.completion_tokens == 75
    assert meter.total_tokens == 375
    assert meter.calls == 2
    assert meter.cost_usd == pytest.approx(0.003)


def test_an_unpriced_model_leaves_the_cost_absent_rather_than_zero() -> None:
    """A zero would be summed into a total that reads as free, and nothing
    downstream could tell it apart from a genuinely free call."""
    with usage.measured() as meter:
        usage.record(model="unpriced", prompt_tokens=100, completion_tokens=50, cost_usd=None)

    assert meter.cost_usd is None
    assert meter.total_tokens == 150


def test_recording_outside_a_metered_block_is_a_no_op() -> None:
    """Model calls happen in tests, scripts and tooling, none of which should
    have to install a meter to be allowed to run."""
    usage.record(model="m", prompt_tokens=1, completion_tokens=1, cost_usd=0.1)

    assert usage.current_meter() is None


def test_the_meter_is_restored_after_the_block() -> None:
    outer = usage.measured()
    with outer:
        with usage.measured() as inner:
            usage.record(model="m", prompt_tokens=5, completion_tokens=0, cost_usd=None)
        assert inner.prompt_tokens == 5
        assert usage.current_meter() is outer.meter
        assert outer.meter.prompt_tokens == 0

    assert usage.current_meter() is None


async def test_concurrent_tasks_share_the_meter_that_started_them() -> None:
    """asyncio tasks inherit a copy of the context, so each sees the same meter
    object — which is exactly the sharing the accounting needs."""

    async def spend() -> None:
        usage.record(model="m", prompt_tokens=10, completion_tokens=5, cost_usd=None)

    with usage.measured() as meter:
        await asyncio.gather(*(spend() for _ in range(5)))

    assert meter.calls == 5
    assert meter.prompt_tokens == 50


# ------------------------------------------------------- concurrency cap


async def test_outbound_model_calls_are_capped() -> None:
    """Groq's free tier allows 30 RPM. Queueing here turns an over-limit burst
    into a slower generation rather than a batch of provider 429s."""
    live = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-120b",
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    client = GroqClient(
        settings=settings(groq_api_key="k", groq_max_concurrency=3),
        transport=httpx.MockTransport(handler),
    )

    await asyncio.gather(*(client.complete_json(system="s", user="u") for _ in range(12)))

    assert peak <= 3, f"{peak} calls were in flight at once against a cap of 3"


async def test_the_cap_does_not_deadlock_when_a_call_fails() -> None:
    """A slot released only on success would leak one per failure until the
    service stopped calling out at all."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = GroqClient(
        settings=settings(groq_api_key="k", groq_max_concurrency=1, groq_max_retries=0),
        transport=httpx.MockTransport(handler),
    )

    from app.services.errors import LLMError

    for _ in range(3):
        with pytest.raises(LLMError):
            await client.complete_json(system="s", user="u")

    # A leaked slot would have made the third call hang rather than raise.
    assert client._slots._value == 1


# -------------------------------------------------------- request body size


def test_an_oversized_declared_body_is_refused_before_it_is_read() -> None:
    api = harness(max_request_bytes=2048)
    oversized = {"bundle": CLEAN_BUNDLE, "notes": "x" * 4096}

    response = api.client.post(
        f"{API_V1_PREFIX}/conflicts/detect",
        json=oversized,
        headers={"Authorization": f"Bearer {api.token}"},
    )

    assert response.status_code == 413
    body = response.json()
    assert body["type"].endswith("/payload-too-large")
    assert body["limit_bytes"] == 2048


def test_the_size_refusal_is_a_problem_document_like_every_other_failure() -> None:
    api = harness(max_request_bytes=1024)

    response = api.client.post(
        f"{API_V1_PREFIX}/conflicts/detect",
        json={"padding": "x" * 4096},
        headers={"Authorization": f"Bearer {api.token}"},
    )

    assert response.headers["content-type"].startswith("application/problem+json")
    assert set(response.json()) >= {"type", "title", "status", "detail"}


def test_an_oversized_body_is_refused_before_authentication() -> None:
    """It is refused ahead of the framework, so an unauthenticated flood cannot
    make this service buffer megabytes per request."""
    api = harness(max_request_bytes=1024)

    response = api.client.post(f"{API_V1_PREFIX}/conflicts/detect", json={"padding": "x" * 4096})

    assert response.status_code == 413


def test_a_body_inside_the_limit_is_accepted() -> None:
    api = harness(max_request_bytes=256 * 1024)

    response = api.post("/conflicts/detect", json={"bundle": CLEAN_BUNDLE})

    assert response.status_code == 200


def test_a_request_with_no_body_at_all_is_unaffected() -> None:
    api = harness(max_request_bytes=1024)

    assert api.get("/kb/options").status_code == 200


def test_a_chunked_body_that_declares_nothing_is_still_counted() -> None:
    """A chunked request carries no Content-Length, so the header check cannot
    see it; the running total is what catches it."""
    api = harness(max_request_bytes=1024)

    def chunks():
        for _ in range(8):
            yield b"x" * 512

    response = api.client.post(
        f"{API_V1_PREFIX}/conflicts/detect",
        content=chunks(),
        headers={
            "Authorization": f"Bearer {api.token}",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 413


def test_an_unparseable_content_length_falls_through_to_the_counter() -> None:
    """A size we cannot trust is not a size we guess at."""
    from app.core.limits import _content_length

    assert _content_length({"headers": [(b"content-length", b"not-a-number")]}) is None
    assert _content_length({"headers": []}) is None
    assert _content_length({"headers": [(b"content-length", b"42")]}) == 42


async def test_the_size_limit_ignores_non_http_traffic() -> None:
    """A lifespan or websocket scope has no body to measure, and must pass
    through untouched rather than being treated as a zero-length request."""
    from app.core.limits import RequestSizeLimitMiddleware

    seen: list[str] = []

    async def app(scope, receive, send) -> None:
        seen.append(scope["type"])

    middleware = RequestSizeLimitMiddleware(app, max_bytes=10)
    await middleware({"type": "lifespan"}, _noop_receive, _noop_send)

    assert seen == ["lifespan"]


async def _noop_receive():  # pragma: no cover - never awaited in that test
    return {"type": "http.request", "body": b""}


async def _noop_send(message) -> None:  # pragma: no cover - never called
    return None


# ------------------------------------------------------------- configuration


def test_the_defaults_are_usable_without_any_configuration() -> None:
    configured = Settings(_env_file=None)

    assert configured.rate_limit_generations_per_window == 10
    assert configured.rate_limit_window_seconds == 3600
    assert configured.groq_max_concurrency == 8
    assert configured.max_request_bytes == 256 * 1024


def test_a_negative_limit_is_refused_at_startup() -> None:
    """Failing at startup beats a service whose limit silently means nothing."""
    with pytest.raises(ValueError):
        Settings(_env_file=None, rate_limit_generations_per_window=-1)


def test_an_absurd_concurrency_cap_is_refused_at_startup() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, groq_max_concurrency=1000)
