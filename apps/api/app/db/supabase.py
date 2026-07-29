"""Talking to Supabase's PostgREST endpoint.

Every call goes out under one of two identities, and choosing between them is
the security decision this module exists to make explicit.

*As the user.* The caller's own access token is presented, so PostgREST sets
the ``authenticated`` role and the request-scoped JWT claims, and the row level
security policies from ``supabase/migrations`` apply to every statement. A
repository that forgets its ``owner_id`` filter returns nothing instead of
returning somebody else's work. This is the default and covers everything a
user owns.

*As the service.* The service role key bypasses row level security entirely.
It is used for exactly one thing — writing ``usage_events``, which no client
may write — and :meth:`SupabaseClient.as_service` is the only way to reach it,
so every bypass is one greppable call.

The client is deliberately thin. It is not an ORM and does not know what a
project is; it turns a table name and a filter into an HTTP request and turns a
PostgREST error into one of this application's errors. What the tables mean
lives in :mod:`app.db.repositories`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, ConflictStateError, UpstreamError
from app.core.request_context import REQUEST_ID_HEADER, get_request_id
from app.core.security import AuthenticatedUser

logger = logging.getLogger(__name__)

JsonObject = dict[str, Any]

#: PostgREST returns the affected rows only when asked. Asked for on writes,
#: because an insert whose result nobody reads cannot report the generated id.
RETURN_REPRESENTATION: Final[str] = "return=representation"

#: SQLSTATE 23505. PostgREST surfaces it as a 409, which is also what a
#: duplicate means to a client, but the code is what identifies it reliably.
UNIQUE_VIOLATION: Final[str] = "23505"


class Identity(StrEnum):
    """Which credential a request travels under."""

    USER = "user"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class SupabaseClient:
    """An HTTP client for one Supabase project's REST interface.

    ``transport`` is injected so tests drive every branch through
    ``httpx.MockTransport``, and so a deployment can supply a pooled transport
    rather than opening a connection per request.
    """

    settings: Settings
    transport: httpx.AsyncBaseTransport | None = None

    # ------------------------------------------------------------- reading

    async def select(
        self,
        table: str,
        *,
        user: AuthenticatedUser,
        params: dict[str, str] | None = None,
    ) -> list[JsonObject]:
        """Rows from ``table`` visible to ``user``.

        An empty list is a legitimate answer and is never an error: under row
        level security, "no such row" and "not yours" are the same response,
        and that is the answer callers should be handling.
        """
        response = await self._request(
            "GET", table, identity=Identity.USER, user=user, params=params
        )
        return _rows(response)

    async def select_one(
        self,
        table: str,
        *,
        user: AuthenticatedUser,
        params: dict[str, str] | None = None,
    ) -> JsonObject | None:
        """The single row matching ``params``, or ``None``.

        Bounded with ``limit=1`` rather than trusting the filter to be unique.
        A caller expecting one row and receiving ten thousand is a bug that
        should cost one row of bandwidth, not all of them.
        """
        rows = await self.select(table, user=user, params={**(params or {}), "limit": "1"})
        return rows[0] if rows else None

    async def count(
        self,
        table: str,
        *,
        user: AuthenticatedUser,
        params: dict[str, str] | None = None,
    ) -> int:
        """How many rows ``user`` can see matching ``params``.

        Uses PostgREST's ``count=exact`` with a zero-length range, so the
        database counts and sends no rows. The rate limiter asks this question
        once per generation request and must not pay for the answer in
        bandwidth.
        """
        response = await self._request(
            "GET",
            table,
            identity=Identity.USER,
            user=user,
            params={**(params or {}), "select": "id"},
            headers={"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"},
        )
        return _parse_content_range(response.headers.get("content-range"))

    # ------------------------------------------------------------- writing

    async def insert(
        self,
        table: str,
        rows: JsonObject | list[JsonObject],
        *,
        user: AuthenticatedUser,
    ) -> list[JsonObject]:
        """Insert one row or many, returning what the database stored.

        The stored row is returned rather than the submitted one because they
        differ in every way that matters: generated id, defaulted columns,
        trigger-stamped timestamps.
        """
        response = await self._request(
            "POST",
            table,
            identity=Identity.USER,
            user=user,
            json=rows,
            headers={"Prefer": RETURN_REPRESENTATION},
        )
        return _rows(response)

    async def insert_one(
        self, table: str, row: JsonObject, *, user: AuthenticatedUser
    ) -> JsonObject:
        """Insert exactly one row and return it."""
        inserted = await self.insert(table, row, user=user)
        if not inserted:
            raise UpstreamError(f"the insert into {table} returned no row")
        return inserted[0]

    async def update(
        self,
        table: str,
        values: JsonObject,
        *,
        user: AuthenticatedUser,
        params: dict[str, str],
    ) -> list[JsonObject]:
        """Update the rows matching ``params``.

        ``params`` is required, not optional. PostgREST will happily update an
        entire table when given no filter, and a signature that permits it by
        omission is a signature that will one day be called that way.
        """
        if not params:
            raise ValueError("update requires a filter; refusing to update every row")
        response = await self._request(
            "PATCH",
            table,
            identity=Identity.USER,
            user=user,
            json=values,
            params=params,
            headers={"Prefer": RETURN_REPRESENTATION},
        )
        return _rows(response)

    async def delete(
        self, table: str, *, user: AuthenticatedUser, params: dict[str, str]
    ) -> list[JsonObject]:
        """Delete the rows matching ``params``, returning what was removed."""
        if not params:
            raise ValueError("delete requires a filter; refusing to delete every row")
        response = await self._request(
            "DELETE",
            table,
            identity=Identity.USER,
            user=user,
            params=params,
            headers={"Prefer": RETURN_REPRESENTATION},
        )
        return _rows(response)

    async def as_service(self, table: str, rows: JsonObject | list[JsonObject]) -> None:
        """Insert under the service role, bypassing row level security.

        The single sanctioned bypass, and it exists for ``usage_events``: a
        client that could write its own accounting could understate its spend,
        so the policy denies every client and the server writes it here.

        Deliberately insert-only and deliberately returns nothing. There is no
        service-role read, update or delete on this client, because none is
        needed and each would be a way around the database's own guarantees.
        """
        await self._request("POST", table, identity=Identity.SERVICE, json=rows)

    # ----------------------------------------------------------- internals

    async def _request(
        self,
        method: str,
        table: str,
        *,
        identity: Identity,
        user: AuthenticatedUser | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.settings.postgrest_url}/{table}"
        request_headers = self._headers(identity, user)
        if headers:
            request_headers.update(headers)

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.supabase_timeout_seconds, transport=self.transport
            ) as client:
                response = await client.request(
                    method, url, params=params, json=json, headers=request_headers
                )
        except httpx.HTTPError as exc:
            raise UpstreamError(
                f"the database could not be reached ({type(exc).__name__})"
            ) from exc

        if response.status_code >= 400:
            self._raise_for_status(response, method, table)
        return response

    def _headers(self, identity: Identity, user: AuthenticatedUser | None) -> dict[str, str]:
        """Assemble credentials, failing loudly when they are absent.

        ``apikey`` identifies the project to the gateway and ``Authorization``
        identifies the caller to the database. On a user request the two differ
        — anon key, user token — and that difference is what makes row level
        security apply.
        """
        if identity is Identity.SERVICE:
            key = self.settings.supabase_service_role_key
            if key is None or not key.get_secret_value():
                raise ConfigurationError(
                    "SUPABASE_SERVICE_ROLE_KEY is not set; usage accounting cannot be written"
                )
            secret = key.get_secret_value()
            headers = {"apikey": secret, "Authorization": f"Bearer {secret}"}
        else:
            anon = self.settings.supabase_anon_key
            if anon is None or not anon.get_secret_value():
                raise ConfigurationError(
                    "SUPABASE_ANON_KEY is not set; the database cannot be reached"
                )
            if user is None:  # pragma: no cover - unreachable via the public methods
                raise ConfigurationError("a user request was assembled without a user")
            headers = {
                "apikey": anon.get_secret_value(),
                "Authorization": f"Bearer {user.access_token}",
            }

        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        request_id = get_request_id()
        if request_id is not None:
            # Propagated so a slow query in Supabase's logs can be tied to the
            # request that caused it.
            headers[REQUEST_ID_HEADER] = request_id
        return headers

    def _raise_for_status(self, response: httpx.Response, method: str, table: str) -> None:
        """Translate a PostgREST failure into one of this application's errors.

        The upstream message is logged and not returned. PostgREST error detail
        quotes the offending row, which on a unique violation means quoting
        user data back over an error channel.
        """
        body: JsonObject = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            pass

        # Every key is prefixed, because `logging` reserves a set of attribute
        # names on LogRecord — `message` among them — and passing a reserved
        # name in `extra` raises a KeyError from inside the logging call. An
        # error path that throws while reporting an error is the worst place
        # for that to happen, and it only shows up when something has already
        # gone wrong.
        logger.error(
            "postgrest request failed",
            extra={
                "request_id": get_request_id(),
                "db_method": method,
                "db_table": table,
                "db_status": response.status_code,
                "db_code": body.get("code"),
                "db_message": body.get("message"),
            },
        )

        if body.get("code") == UNIQUE_VIOLATION:
            raise ConflictStateError(
                f"that {table[:-1] if table.endswith('s') else table} already exists"
            )

        if response.status_code in (401, 403):
            # The token verified here but the database refused it. In practice
            # this is an expired token racing its own expiry check, or a policy
            # that does not cover the statement.
            raise UpstreamError("the database refused this request's credentials")

        raise UpstreamError(f"the database rejected the request ({response.status_code})")


def _rows(response: httpx.Response) -> list[JsonObject]:
    """PostgREST's array body, or an empty list for a 204."""
    if response.status_code == 204 or not response.content:
        return []
    try:
        parsed = response.json()
    except ValueError as exc:
        raise UpstreamError("the database returned a response that was not JSON") from exc
    if isinstance(parsed, dict):
        return [parsed]
    if not isinstance(parsed, list):
        raise UpstreamError("the database returned a response of an unexpected shape")
    return [row for row in parsed if isinstance(row, dict)]


def _parse_content_range(header: str | None) -> int:
    """The total from a ``Content-Range: 0-0/12`` header.

    A ``*`` total means PostgREST was not asked to count; reporting it as zero
    would make a rate limiter believe a user had spent nothing, so it is an
    error rather than a default.
    """
    if header is None:
        raise UpstreamError("the database did not return a row count")
    _, _, total = header.partition("/")
    try:
        return int(total)
    except ValueError as exc:
        raise UpstreamError("the database returned an unusable row count") from exc


def build_client(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> SupabaseClient:
    """Construct the client the application factory installs."""
    return SupabaseClient(settings or get_settings(), transport=transport)
