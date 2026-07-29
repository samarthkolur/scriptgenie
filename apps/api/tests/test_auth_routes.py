"""Tests for authentication at the route boundary.

The acceptance criterion for this stage is that every ``/v1`` route refuses an
unauthenticated caller while ``/health`` does not. That is asserted here by
enumerating the application's own routes rather than by listing the ones this
file knows about, so a route added later without a user dependency fails on the
day it is added.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.main import API_V1_PREFIX, create_app
from tests.auth_fixtures import JwksServer, PostgrestStub, SigningKey, claims, settings

PROFILE_ROW = {
    "id": "00000000-0000-4000-8000-000000000001",
    "email": "ada@example.test",
    "display_name": "Ada Lovelace",
    "avatar_url": "https://example.test/ada.png",
    "created_at": "2026-07-29T09:00:00+00:00",
}


def _app_and_token(stub: PostgrestStub | None = None) -> tuple[TestClient, str, PostgrestStub]:
    key = SigningKey.generate("key-1")
    postgrest = stub or PostgrestStub()
    app = create_app(
        settings(),
        auth_transport=JwksServer([key]).transport(),
        db_transport=postgrest.transport(),
    )
    token = key.sign(claims(subject=uuid4()))
    return TestClient(app), token, postgrest


# ------------------------------------------------------- the stated criterion


def test_every_v1_route_requires_authentication() -> None:
    app = create_app(settings())
    client = TestClient(app)

    # Enumerated from the OpenAPI document rather than from `app.routes`: that
    # is the published contract, it survives however FastAPI happens to nest
    # included routers internally, and it is what a client would work from.
    operations = [
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        if path.startswith(API_V1_PREFIX)
        for method in methods
    ]
    assert operations, "no v1 routes are mounted; this test would pass vacuously"

    for method, path in operations:
        # Path parameters are filled with a syntactically valid value so the
        # request reaches the dependency rather than failing to route.
        concrete = _fill_path_params(path)
        response = client.request(method, concrete)
        assert response.status_code == 401, f"{method} {concrete} answered without a token"


def _fill_path_params(path: str) -> str:
    while "{" in path:
        start = path.index("{")
        end = path.index("}", start)
        path = path[:start] + "00000000-0000-4000-8000-000000000001" + path[end + 1 :]
    return path


def test_health_is_reachable_without_a_token() -> None:
    assert TestClient(create_app(settings())).get("/health").status_code == 200


def test_a_missing_token_is_a_problem_document_with_a_challenge() -> None:
    response = TestClient(create_app(settings())).get(f"{API_V1_PREFIX}/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/unauthenticated")


def test_a_tampered_token_is_rejected_at_the_route() -> None:
    client, token, _ = _app_and_token()
    header, payload, signature = token.split(".")

    response = client.get(
        f"{API_V1_PREFIX}/me",
        headers={"Authorization": f"Bearer {header}.{payload}x.{signature}"},
    )

    assert response.status_code == 401


def test_an_expired_token_is_rejected_at_the_route() -> None:
    key = SigningKey.generate("key-1")
    app = create_app(settings(), auth_transport=JwksServer([key]).transport())
    expired = key.sign(claims(expires_in=-1))

    response = TestClient(app).get(
        f"{API_V1_PREFIX}/me", headers={"Authorization": f"Bearer {expired}"}
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_a_non_bearer_authorization_header_is_rejected() -> None:
    client, token, _ = _app_and_token()

    response = client.get(f"{API_V1_PREFIX}/me", headers={"Authorization": f"Basic {token}"})

    assert response.status_code == 401


# ------------------------------------------------------------------ the route


def test_a_verified_caller_reads_their_own_profile() -> None:
    stub = PostgrestStub().on("GET", "profiles", httpx.Response(200, json=[PROFILE_ROW]))
    client, token, _postgrest = _app_and_token(stub)

    response = client.get(f"{API_V1_PREFIX}/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.test"
    assert response.json()["display_name"] == "Ada Lovelace"


def test_the_profile_is_read_under_the_callers_own_token() -> None:
    """The whole point of carrying the token: the database applies the same
    user's row level security, so a bug in this service cannot widen access."""
    stub = PostgrestStub().on("GET", "profiles", httpx.Response(200, json=[PROFILE_ROW]))
    client, token, postgrest = _app_and_token(stub)

    client.get(f"{API_V1_PREFIX}/me", headers={"Authorization": f"Bearer {token}"})

    request = postgrest.last("GET", "profiles")
    assert request.headers["authorization"] == f"Bearer {token}"
    assert request.headers["apikey"] == "anon-key-for-tests"
    assert request.headers["apikey"] != token, "the anon key is not the user's credential"


def test_the_profile_response_never_contains_the_access_token() -> None:
    stub = PostgrestStub().on("GET", "profiles", httpx.Response(200, json=[PROFILE_ROW]))
    client, token, _ = _app_and_token(stub)

    response = client.get(f"{API_V1_PREFIX}/me", headers={"Authorization": f"Bearer {token}"})

    assert token not in response.text


def test_a_missing_profile_row_says_why() -> None:
    """The trigger creates it on signup, so its absence is a deployment fault
    and not something the caller can fix by retrying."""
    stub = PostgrestStub().on("GET", "profiles", httpx.Response(200, json=[]))
    client, token, _ = _app_and_token(stub)

    response = client.get(f"{API_V1_PREFIX}/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert "trigger" in response.json()["detail"]
