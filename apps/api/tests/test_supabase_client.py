"""Tests for the PostgREST client.

The behaviour under test is mostly about credentials and refusals. What a
select returns matters less than which identity it travelled under, because
that is what decides whether the database's row level security applies at all.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.core.errors import ConfigurationError, ConflictStateError, UpstreamError
from app.core.security import AuthenticatedUser
from app.db.supabase import SupabaseClient
from tests.auth_fixtures import PostgrestStub, settings


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=uuid4(),
        email="ada@example.test",
        role="authenticated",
        access_token="a-verified-access-token",
    )


def _client(stub: PostgrestStub, **overrides: object) -> SupabaseClient:
    return SupabaseClient(settings(**overrides), transport=stub.transport())


# ------------------------------------------------------------------ reading


async def test_select_returns_the_rows() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[{"id": "1"}]))

    rows = await _client(stub).select("projects", user=_user())

    assert rows == [{"id": "1"}]


async def test_an_empty_result_is_not_an_error() -> None:
    """Under RLS, "no such row" and "not yours" are the same answer, and both
    are answers a caller should be handling rather than an exception."""
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))

    assert await _client(stub).select("projects", user=_user()) == []


async def test_select_one_bounds_the_query() -> None:
    """A caller expecting one row and receiving ten thousand is a bug that
    should cost one row of bandwidth, not all of them."""
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[{"id": "1"}]))

    await _client(stub).select_one("projects", user=_user(), params={"id": "eq.1"})

    assert stub.last("GET", "projects").url.params["limit"] == "1"


async def test_select_one_returns_none_when_nothing_matches() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))

    assert await _client(stub).select_one("projects", user=_user()) is None


async def test_count_asks_the_database_to_count_and_send_nothing() -> None:
    stub = PostgrestStub().on(
        "GET",
        "generation_runs",
        httpx.Response(200, json=[], headers={"content-range": "0-0/17"}),
    )

    total = await _client(stub).count("generation_runs", user=_user())

    assert total == 17
    request = stub.last("GET", "generation_runs")
    assert request.headers["prefer"] == "count=exact"
    assert request.headers["range"] == "0-0"


async def test_a_missing_row_count_is_an_error_not_a_zero() -> None:
    """A rate limiter reading zero would believe the user had spent nothing."""
    stub = PostgrestStub().on("GET", "generation_runs", httpx.Response(200, json=[]))

    with pytest.raises(UpstreamError, match="row count"):
        await _client(stub).count("generation_runs", user=_user())


async def test_an_unusable_row_count_is_an_error_not_a_zero() -> None:
    stub = PostgrestStub().on(
        "GET",
        "generation_runs",
        httpx.Response(200, json=[], headers={"content-range": "0-0/*"}),
    )

    with pytest.raises(UpstreamError, match="unusable row count"):
        await _client(stub).count("generation_runs", user=_user())


# ------------------------------------------------------------------ writing


async def test_insert_returns_what_the_database_stored() -> None:
    """Not what was submitted: they differ in id, defaults and trigger stamps."""
    stored = {"id": "generated", "title": "Cabin", "created_at": "2026-07-29T09:00:00+00:00"}
    stub = PostgrestStub().on("POST", "projects", httpx.Response(201, json=[stored]))

    row = await _client(stub).insert_one("projects", {"title": "Cabin"}, user=_user())

    assert row == stored
    assert stub.last("POST", "projects").headers["prefer"] == "return=representation"


async def test_an_insert_that_returns_nothing_is_an_error() -> None:
    stub = PostgrestStub().on("POST", "projects", httpx.Response(201, json=[]))

    with pytest.raises(UpstreamError, match="returned no row"):
        await _client(stub).insert_one("projects", {"title": "Cabin"}, user=_user())


async def test_a_unique_violation_becomes_a_conflict() -> None:
    stub = PostgrestStub().on(
        "POST",
        "resolutions",
        httpx.Response(409, json={"code": "23505", "message": "duplicate key value"}),
    )

    with pytest.raises(ConflictStateError):
        await _client(stub).insert_one("resolutions", {"rule_id": "x"}, user=_user())


async def test_the_upstream_error_message_is_not_returned_to_the_caller() -> None:
    """PostgREST quotes the offending row, which on a unique violation means
    quoting user data back over an error channel."""
    stub = PostgrestStub().on(
        "POST",
        "projects",
        httpx.Response(400, json={"code": "22001", "message": "value 'ada@example.test' too long"}),
    )

    with pytest.raises(UpstreamError) as raised:
        await _client(stub).insert_one("projects", {"title": "x"}, user=_user())

    assert "ada@example.test" not in str(raised.value)


@pytest.mark.parametrize("method", ["update", "delete"])
async def test_a_write_without_a_filter_is_refused(method: str) -> None:
    """PostgREST will happily rewrite an entire table when given no filter."""
    client = _client(PostgrestStub())

    with pytest.raises(ValueError, match="refusing to"):
        if method == "update":
            await client.update("projects", {"title": "x"}, user=_user(), params={})
        else:
            await client.delete("projects", user=_user(), params={})


async def test_update_sends_its_filter() -> None:
    stub = PostgrestStub().on("PATCH", "projects", httpx.Response(200, json=[{"id": "1"}]))

    await _client(stub).update("projects", {"title": "New"}, user=_user(), params={"id": "eq.1"})

    assert stub.last("PATCH", "projects").url.params["id"] == "eq.1"


async def test_delete_returns_what_was_removed() -> None:
    stub = PostgrestStub().on("DELETE", "projects", httpx.Response(200, json=[{"id": "1"}]))

    removed = await _client(stub).delete("projects", user=_user(), params={"id": "eq.1"})

    assert removed == [{"id": "1"}]


async def test_a_204_response_is_an_empty_result() -> None:
    stub = PostgrestStub().on("DELETE", "projects", httpx.Response(204))

    assert await _client(stub).delete("projects", user=_user(), params={"id": "eq.9"}) == []


# -------------------------------------------------------------- credentials


async def test_a_user_request_presents_the_users_token_and_the_anon_key() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))
    user = _user()

    await _client(stub).select("projects", user=user)

    headers = stub.last("GET", "projects").headers
    assert headers["authorization"] == f"Bearer {user.access_token}"
    assert headers["apikey"] == "anon-key-for-tests"


async def test_the_service_role_is_reachable_only_through_as_service() -> None:
    stub = PostgrestStub().on("POST", "usage_events", httpx.Response(201, json=[]))

    await _client(stub).as_service("usage_events", {"event_type": "generation"})

    headers = stub.last("POST", "usage_events").headers
    assert headers["authorization"] == "Bearer service-role-key-for-tests"
    assert headers["apikey"] == "service-role-key-for-tests"


def test_the_client_exposes_no_service_role_read_or_delete() -> None:
    """The single sanctioned bypass is an insert. Anything else would be a way
    around the guarantees the database is there to provide."""
    service_methods = [
        name for name in dir(SupabaseClient) if "service" in name and not name.startswith("_")
    ]

    assert service_methods == ["as_service"]


async def test_a_missing_anon_key_names_the_setting() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))
    client = SupabaseClient(settings(supabase_anon_key=None), transport=stub.transport())

    with pytest.raises(ConfigurationError, match="SUPABASE_ANON_KEY"):
        await client.select("projects", user=_user())


async def test_a_missing_service_role_key_names_the_setting() -> None:
    stub = PostgrestStub()
    client = SupabaseClient(settings(supabase_service_role_key=""), transport=stub.transport())

    with pytest.raises(ConfigurationError, match="SUPABASE_SERVICE_ROLE_KEY"):
        await client.as_service("usage_events", {"event_type": "generation"})


# ------------------------------------------------------------------ failures


async def test_an_unreachable_database_is_an_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = SupabaseClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(UpstreamError, match="could not be reached"):
        await client.select("projects", user=_user())


async def test_a_credential_the_database_refuses_is_an_upstream_error() -> None:
    """Not a 401 to the caller: their token verified here. The mismatch is ours."""
    stub = PostgrestStub().on("GET", "projects", httpx.Response(401, json={"message": "JWT"}))

    with pytest.raises(UpstreamError, match="credentials"):
        await _client(stub).select("projects", user=_user())


async def test_a_non_json_response_is_an_upstream_error() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, text="<html>gateway</html>"))

    with pytest.raises(UpstreamError, match="not JSON"):
        await _client(stub).select("projects", user=_user())


async def test_a_response_of_the_wrong_shape_is_an_upstream_error() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(200, json=42))

    with pytest.raises(UpstreamError, match="unexpected shape"):
        await _client(stub).select("projects", user=_user())


async def test_a_single_object_response_is_read_as_one_row() -> None:
    """PostgREST returns an object rather than an array when asked for one."""
    stub = PostgrestStub().on("GET", "profiles", httpx.Response(200, json={"id": "1"}))

    assert await _client(stub).select("profiles", user=_user()) == [{"id": "1"}]


async def test_an_error_body_that_is_not_json_still_raises_cleanly() -> None:
    stub = PostgrestStub().on("GET", "projects", httpx.Response(502, text="Bad Gateway"))

    with pytest.raises(UpstreamError, match="502"):
        await _client(stub).select("projects", user=_user())
