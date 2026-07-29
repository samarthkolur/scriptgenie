"""Correlating one request across middleware, handlers, logs and the response.

A request id has to be reachable from code that was never handed the request —
an exception handler, a service three calls deep, a log record built by a
library. Threading it through every signature would be the alternative, and it
would be abandoned the first time somebody added a helper.

:class:`contextvars.ContextVar` is the right tool and not merely the convenient
one: asyncio tasks inherit a *copy* of the context at creation, so the five
concurrent variant generations each carry the id of the request that started
them, and none can observe another's.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

#: The header both apps use. `X-Request-Id` is not standardised but it is what
#: Vercel, Fly.io and Render all propagate, so an id set at the edge survives.
REQUEST_ID_HEADER: Final[str] = "X-Request-Id"

#: An inbound id is honoured so a trace spans web -> api, but it is bounded and
#: filtered first. It is echoed into a response header and into log records,
#: and an unbounded attacker-controlled string in either is a header-injection
#: and log-forging primitive.
MAX_REQUEST_ID_LENGTH: Final[int] = 128

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """The current request's id, or ``None`` outside a request."""
    return _request_id.get()


def set_request_id(request_id: str) -> None:
    """Bind ``request_id`` to the current context. Used by the middleware."""
    _request_id.set(request_id)


def _is_safe(candidate: str) -> bool:
    """Whether an inbound id may be reused as-is.

    Restricted to the characters a UUID, a ULID or a hex trace id uses. Anything
    else gets a fresh id rather than a rejection: the caller's id being unusable
    is not a reason to fail their request.
    """
    if not candidate or len(candidate) > MAX_REQUEST_ID_LENGTH:
        return False
    return all(character.isalnum() or character in "-_" for character in candidate)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign or adopt a request id, and return it on every response.

    The id is set on the response whatever happened, including on the 500 path,
    because the response a user can quote is the only link they have to the log
    line that explains it.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if _is_safe(inbound) else str(uuid.uuid4())

        set_request_id(request_id)
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
