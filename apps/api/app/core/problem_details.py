"""Rendering every failure as an RFC 9457 problem document.

Four handlers cover everything this application can fail with: its own
:class:`~app.core.errors.APIError` hierarchy, FastAPI's ``HTTPException``,
request validation, and the unhandled exception. They all produce the same
media type and the same members, so a client writes one parser.

The unhandled handler is the one that matters. Without it, an unexpected
exception becomes Starlette's plain-text ``Internal Server Error`` with a
stack trace in the log and no request id in the response — which is precisely
the failure a user reports and nobody can find. It returns the request id and
nothing else about the exception: the message may contain a connection string,
a row of someone else's data, or a prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import PROBLEM_TYPE_BASE, APIError, RateLimitedError
from app.core.request_context import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)

#: RFC 9457's media type. Set explicitly so a client can content-negotiate
#: errors, and so a proxy does not decide this is ordinary JSON to rewrite.
PROBLEM_JSON = "application/problem+json"


def problem_response(
    *,
    status_code: int,
    title: str,
    detail: str,
    problem_type: str,
    instance: str,
    request_id: str | None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build one problem document.

    ``request_id`` is a member of the body and not only a header, because the
    body is what a user copies out of a browser console and pastes into a
    support request.
    """
    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE_BASE}/{problem_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
    }
    response_headers = dict(headers or {})
    if request_id is not None:
        body["request_id"] = request_id
        # Set here and not left to RequestIdMiddleware. Starlette installs the
        # handler for unhandled exceptions as ServerErrorMiddleware, which is
        # the *outermost* layer — outside our middleware — so a 500 response
        # never passes back through it. That is precisely the response whose id
        # someone will need, so it is stamped at the point of construction.
        response_headers[REQUEST_ID_HEADER] = request_id
    if extra:
        body.update(jsonable_encoder(extra))

    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_JSON,
        headers=response_headers or None,
    )


async def handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    """Render the application's own errors."""
    assert isinstance(exc, APIError)
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitedError):
        # RFC 9110 §10.2.3. A 429 without Retry-After leaves a client guessing,
        # and a guessing client retries immediately.
        headers["Retry-After"] = str(exc.retry_after_seconds)
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # RFC 9110 §11.6.1 requires a challenge on every 401.
        headers["WWW-Authenticate"] = 'Bearer realm="scriptgenie"'

    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(
            "request failed",
            extra={
                "request_id": get_request_id(),
                "path": request.url.path,
                "problem_type": exc.problem_type,
                "detail": exc.detail,
            },
        )

    return problem_response(
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        problem_type=exc.problem_type,
        instance=request.url.path,
        request_id=get_request_id(),
        extra=exc.extra,
        headers=headers or None,
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    """Render ``HTTPException``, including the 404 Starlette raises for itself."""
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    headers = dict(exc.headers or {})
    return problem_response(
        status_code=exc.status_code,
        title=_TITLES.get(exc.status_code, "Request failed"),
        detail=detail,
        problem_type=_PROBLEM_TYPES.get(exc.status_code, "http-error"),
        instance=request.url.path,
        request_id=get_request_id(),
        headers=headers or None,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Render a malformed request body, keeping the per-field detail.

    FastAPI's own errors say exactly which field failed and why, which is worth
    far more to a client than a generic 422. They are carried through as
    ``errors`` rather than flattened into prose.
    """
    assert isinstance(exc, RequestValidationError)
    return problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        title="Request body is invalid",
        detail="The request body did not match the expected schema.",
        problem_type="invalid-body",
        instance=request.url.path,
        request_id=get_request_id(),
        extra={"errors": exc.errors()},
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Render anything that reached the top of the stack unhandled.

    The exception is logged with its traceback and the request id; the response
    carries the request id and nothing else. An exception message can contain a
    connection string, a fragment of another user's row, or a prompt, and none
    of those may leave this process in a response body.
    """
    logger.exception(
        "unhandled exception",
        extra={
            "request_id": get_request_id(),
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
        },
    )
    return problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal server error",
        detail=("The request could not be completed. Quote the request id when reporting this."),
        problem_type="internal-error",
        instance=request.url.path,
        request_id=get_request_id(),
    )


_TITLES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Bad request",
    status.HTTP_401_UNAUTHORIZED: "Authentication required",
    status.HTTP_403_FORBIDDEN: "Not permitted",
    status.HTTP_404_NOT_FOUND: "Not found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Method not allowed",
    status.HTTP_413_CONTENT_TOO_LARGE: "Request body too large",
    status.HTTP_429_TOO_MANY_REQUESTS: "Rate limit exceeded",
}

_PROBLEM_TYPES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad-request",
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not-found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method-not-allowed",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload-too-large",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate-limited",
}


def install(app: FastAPI) -> None:
    """Register every handler on ``app``."""
    app.add_exception_handler(APIError, handle_api_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
