"""Tests for request correlation and the problem details envelope."""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    APIError,
    ConflictStateError,
    NotFoundError,
    RateLimitedError,
)
from app.core.request_context import (
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
    get_request_id,
)
from app.main import create_app
from tests.auth_fixtures import settings


class Typed(BaseModel):
    """A body model for the validation probe.

    Module level, not nested in the router factory: `from __future__ import
    annotations` makes every annotation a string, and FastAPI resolves those
    against module globals. A locally-scoped class is invisible there, and the
    parameter is silently demoted to a query string.
    """

    count: int


def _client() -> TestClient:
    # `raise_server_exceptions=False` so the unhandled-exception handler is
    # exercised as a caller would see it, rather than the test client
    # re-raising and hiding the response the browser would receive.
    app = create_app(settings())
    app.include_router(_probe_router())
    return TestClient(app, raise_server_exceptions=False)


def _probe_router() -> APIRouter:
    """Routes that fail in each of the ways the handlers cover."""
    router = APIRouter(prefix="/probe")

    @router.get("/echo")
    def echo() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    @router.get("/not-found")
    def not_found() -> None:
        raise NotFoundError("no such project")

    @router.get("/conflicted")
    def conflicted() -> None:
        raise ConflictStateError(
            "generation is blocked while a HARD conflict is unresolved",
            conflicts=[{"rule_id": "horror_comedy_tonal_pressure", "severity": "HARD"}],
        )

    @router.get("/limited")
    def limited() -> None:
        raise RateLimitedError("10 runs per hour", retry_after_seconds=1800)

    @router.get("/exploded")
    def exploded() -> None:
        raise RuntimeError("connection to postgres://user:hunter2@db failed")

    @router.post("/typed")
    def typed(body: Typed) -> dict[str, int]:
        return {"count": body.count}

    return router


# ------------------------------------------------------------- request ids


def test_a_request_id_is_generated_and_returned() -> None:
    response = _client().get("/health")

    assert uuid.UUID(response.headers[REQUEST_ID_HEADER])


def test_an_inbound_request_id_is_adopted() -> None:
    """A trace that starts in the browser must not restart at the API."""
    supplied = "web-01HXYZ-abc_123"

    response = _client().get("/health", headers={REQUEST_ID_HEADER: supplied})

    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_the_request_id_is_reachable_from_handler_code() -> None:
    response = _client().get("/probe/echo", headers={REQUEST_ID_HEADER: "trace-42"})

    assert response.json()["request_id"] == "trace-42"


@pytest.mark.parametrize(
    ("supplied", "reason"),
    [
        ("has spaces", "a space is not valid in a header value we echo back"),
        ("../../etc/passwd", "path traversal characters have no place in an id"),
        ("id\r\nX-Admin: true", "a CRLF would inject a second response header"),
        ("x" * (MAX_REQUEST_ID_LENGTH + 1), "an unbounded id inflates every log line"),
        ("", "an empty header is not an id"),
    ],
)
def test_an_unusable_inbound_request_id_is_replaced(supplied: str, reason: str) -> None:
    """Replaced rather than rejected: the caller's id being unusable is not a
    reason to fail their request, but it is a reason not to echo it."""
    response = _client().get("/health", headers={REQUEST_ID_HEADER: supplied})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != supplied, reason
    assert uuid.UUID(returned)


def test_the_request_id_survives_a_failure() -> None:
    """The response a user can quote is their only link to the log line."""
    response = _client().get("/probe/exploded")

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER]
    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]


# --------------------------------------------------------- problem details


def test_an_application_error_renders_as_a_problem_document() -> None:
    response = _client().get("/probe/not-found")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"].endswith("/not-found")
    assert body["title"] == "Not found"
    assert body["status"] == 404
    assert body["detail"] == "no such project"
    assert body["instance"] == "/probe/not-found"


def test_structured_detail_is_carried_into_the_document() -> None:
    """A 409 that only says "conflict" leaves the client nothing to act on."""
    response = _client().get("/probe/conflicted")

    assert response.status_code == 409
    assert response.json()["conflicts"][0]["rule_id"] == "horror_comedy_tonal_pressure"


def test_a_rate_limit_carries_retry_after() -> None:
    response = _client().get("/probe/limited")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "1800"
    assert response.json()["retry_after_seconds"] == 1800


def test_an_unhandled_exception_never_leaks_its_message() -> None:
    """The message here contains a password. None of it may reach the client."""
    response = _client().get("/probe/exploded")

    assert response.status_code == 500
    body = response.text
    assert "hunter2" not in body
    assert "postgres" not in body
    assert response.json()["title"] == "Internal server error"


def test_an_unknown_route_is_a_problem_document_too() -> None:
    """One error format, including for the 404 the framework raises itself."""
    response = _client().get("/no-such-route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/not-found")


def test_a_malformed_body_reports_which_field_failed() -> None:
    """FastAPI's per-field detail is worth more to a client than a bare 422,
    so it is carried through rather than flattened into prose."""
    response = _client().post("/probe/typed", json={"count": "seven"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"].endswith("/invalid-body")
    assert body["errors"][0]["loc"] == ["body", "count"]


def test_every_api_error_declares_a_distinct_problem_type() -> None:
    """The `type` URI is what a client branches on, so two errors sharing one
    would make them indistinguishable to anything but a human."""
    subclasses = _all_subclasses(APIError)
    types = [cls.problem_type for cls in subclasses]

    assert len(types) == len(set(types)), sorted(types)


def test_every_api_error_uri_is_absolute() -> None:
    for cls in _all_subclasses(APIError):
        # RateLimitedError is the one subclass that requires more than a
        # detail, because a 429 without Retry-After is not a complete answer.
        error = (
            cls("detail", retry_after_seconds=1)
            if issubclass(cls, RateLimitedError)
            else cls("detail")
        )
        assert error.type_uri.startswith("https://")


def _all_subclasses(root: type[APIError]) -> list[type[APIError]]:
    found: list[type[APIError]] = []
    for subclass in root.__subclasses__():
        found.append(subclass)
        found.extend(_all_subclasses(subclass))
    return found


# ------------------------------------------------------------------- CORS


def test_the_request_id_header_is_exposed_to_the_browser() -> None:
    """A cross-origin response hides every header the server does not expose,
    which would make the id unreadable by the code that would report it."""
    configured = settings(allowed_origins=["https://app.example"])
    client = TestClient(create_app(configured))

    response = client.get("/health", headers={"Origin": "https://app.example"})

    exposed = response.headers["access-control-expose-headers"].lower()
    assert REQUEST_ID_HEADER.lower() in exposed
    assert "retry-after" in exposed


def test_an_unknown_origin_gets_no_cors_grant() -> None:
    configured = settings(allowed_origins=["https://app.example"])
    client = TestClient(create_app(configured))

    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_origins_are_split_from_a_comma_separated_variable(monkeypatch) -> None:
    """The form every deployment platform uses for a list in an env var.

    Regression guard: pydantic-settings parses list-typed fields as JSON before
    validators run, so this raised at import time until the field opted out of
    that decoding.
    """
    from app.core import config

    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().allowed_origins == [
            "https://a.example",
            "https://b.example",
        ]
    finally:
        config.get_settings.cache_clear()


async def test_the_request_id_is_propagated_to_the_database() -> None:
    """So a slow query in Supabase's logs ties back to the request that caused it."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json=[])

    from app.core.request_context import set_request_id
    from app.core.security import AuthenticatedUser
    from app.db.supabase import SupabaseClient

    set_request_id("trace-99")
    client = SupabaseClient(settings(), transport=httpx.MockTransport(handler))
    await client.select(
        "projects",
        user=AuthenticatedUser(id=uuid.uuid4(), email=None, role="authenticated", access_token="t"),
    )

    assert seen[REQUEST_ID_HEADER.lower()] == "trace-99"
