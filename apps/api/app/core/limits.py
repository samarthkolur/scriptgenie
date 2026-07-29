"""Refusing a request body before it is read.

FastAPI parses the whole body into memory before a route or a validator sees
it, so a body-size check written as a dependency runs after the damage is done.
This runs as ASGI middleware, ahead of the framework.

Two checks, because either alone is bypassable:

*``Content-Length``* catches the honest oversized request in one comparison and
never reads a byte.

*A running total while streaming* catches the dishonest one. A chunked request
carries no ``Content-Length``, and a lying one carries a small value with a
large body — so the bytes are counted as they arrive and the connection is
refused the moment the total passes the ceiling, rather than after the last
chunk has been buffered.

Written as raw ASGI rather than ``BaseHTTPMiddleware`` deliberately.
``BaseHTTPMiddleware`` gives no access to the receive channel, so the streaming
half of this — the half that catches the lying request — cannot be written
there at all.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import PROBLEM_TYPE_BASE
from app.core.request_context import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)

PROBLEM_JSON = b"application/problem+json"


class RequestSizeLimitMiddleware:
    """Refuse a body larger than ``max_bytes`` with a 413."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._refuse(scope, send, declared)
            return

        # Count as the body arrives. `too_large` is a one-element list rather
        # than a closure variable because the wrapper below has to mutate it,
        # and it has to be readable after the app has finished consuming.
        too_large = [False]

        async def counting_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                counting_receive.seen += len(message.get("body", b""))  # type: ignore[attr-defined]
                if counting_receive.seen > self.max_bytes:  # type: ignore[attr-defined]
                    too_large[0] = True
                    # Stop the stream. The app sees a truncated body, fails to
                    # parse it, and this middleware turns that into the 413 it
                    # should have been — rather than buffering the rest of a
                    # body it has already decided to refuse.
                    return {"type": "http.disconnect"}
            return message

        counting_receive.seen = 0  # type: ignore[attr-defined]

        sent_response = [False]

        async def guarded_send(message: Message) -> None:
            if too_large[0] and not sent_response[0]:
                sent_response[0] = True
                await _send_problem(send, self.max_bytes, None)
                return
            if too_large[0]:
                return
            await send(message)

        await self.app(scope, counting_receive, guarded_send)

        if too_large[0] and not sent_response[0]:  # pragma: no cover - defensive
            await _send_problem(send, self.max_bytes, None)

    async def _refuse(self, scope: Scope, send: Send, declared: int) -> None:
        logger.warning(
            "request refused: body too large",
            extra={
                "request_id": get_request_id(),
                "path": scope.get("path"),
                "declared_bytes": declared,
                "limit_bytes": self.max_bytes,
            },
        )
        await _send_problem(send, self.max_bytes, declared)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                # An unparseable Content-Length is not a size we can trust, so
                # it is left to the streaming counter rather than guessed at.
                return None
    return None


async def _send_problem(send: Send, limit: int, declared: int | None) -> None:
    """The same RFC 9457 shape every other failure uses.

    Built by hand because this runs outside the application, where the
    exception handlers are not reachable.
    """
    detail = f"The request body exceeds the {limit} byte limit."
    if declared is not None:
        detail = f"The request body is {declared} bytes; the limit is {limit}."

    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE_BASE}/payload-too-large",
        "title": "Request body too large",
        "status": 413,
        "detail": detail,
        "limit_bytes": limit,
    }
    request_id = get_request_id()
    if request_id is not None:
        body["request_id"] = request_id

    payload = json.dumps(body).encode()
    headers = [
        (b"content-type", PROBLEM_JSON),
        (b"content-length", str(len(payload)).encode()),
    ]
    if request_id is not None:
        headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))

    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": payload})
