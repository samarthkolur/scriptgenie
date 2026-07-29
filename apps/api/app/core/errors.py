"""Application errors and the RFC 9457 problem details they become.

One error hierarchy, one response shape. Routes raise a domain-meaningful
exception and never build a response body; the handlers in
:mod:`app.core.problem_details` render every one of them the same way, so a
client has exactly one error format to parse and cannot encounter an
undocumented one on the path nobody exercised.

Each class fixes its own status code and ``type`` URI. The ``type`` is a stable
identifier a client may branch on — status codes are too coarse (a 409 could be
an unresolved conflict or a duplicate title) and human-readable titles are not
a contract.

``ConfigurationError`` is the odd one: it is a 500 because a misconfigured
deployment is this service's fault and not the caller's, and its detail is
deliberately safe to return, naming the missing setting without revealing any
value.
"""

from __future__ import annotations

from typing import Any

#: Base for every ``type`` URI. Not dereferenced at runtime; it exists so the
#: identifiers are globally unique and can be documented at a stable address.
PROBLEM_TYPE_BASE = "https://scriptgenie.app/problems"


class APIError(Exception):
    """An error that has a defined HTTP representation.

    ``extra`` carries structured fields specific to one error — the conflicts
    that blocked a generation, the seconds until a rate limit resets. They are
    merged into the problem document as top-level members, which RFC 9457
    explicitly permits and which is what makes the envelope useful rather than
    merely uniform.
    """

    status_code: int = 500
    problem_type: str = "internal-error"
    title: str = "Internal server error"

    def __init__(self, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra: dict[str, Any] = extra

    @property
    def type_uri(self) -> str:
        return f"{PROBLEM_TYPE_BASE}/{self.problem_type}"


class AuthenticationError(APIError):
    """No credential, or one that does not verify.

    Always 401 and never 403: the caller has not established who they are, so
    there is nothing yet to deny them.
    """

    status_code = 401
    problem_type = "unauthenticated"
    title = "Authentication required"


class AuthorizationError(APIError):
    """A verified caller asking for something that is not theirs.

    Row level security means most of these never reach here — the database
    returns no row and the caller gets a 404, which is also the better answer
    because a 403 confirms the resource exists. This is raised where ownership
    is checked explicitly and the distinction is already public.
    """

    status_code = 403
    problem_type = "forbidden"
    title = "Not permitted"


class NotFoundError(APIError):
    """No such resource, or none this caller can see.

    Deliberately conflated. Distinguishing them would let anyone enumerate
    other users' project ids by watching for 403s.
    """

    status_code = 404
    problem_type = "not-found"
    title = "Not found"


class ValidationFailedError(APIError):
    """A request that parsed but does not describe anything the system can act on.

    Distinct from FastAPI's own 422 for a malformed body: this is for input
    that is well-formed and still wrong, such as a genre id no knowledge base
    row answers to.
    """

    status_code = 422
    problem_type = "invalid-request"
    title = "Request could not be processed"


class ConflictStateError(APIError):
    """The resource is not in a state where this operation makes sense.

    Carries the reason as ``extra`` so the client can act. Generation blocked
    by an unresolved HARD conflict is the case that matters, and it returns the
    conflicts themselves rather than only saying that some exist.
    """

    status_code = 409
    problem_type = "conflict-state"
    title = "Request conflicts with the current state"


class RateLimitedError(APIError):
    """The caller has spent their allowance for the current window."""

    status_code = 429
    problem_type = "rate-limited"
    title = "Rate limit exceeded"

    def __init__(self, detail: str, *, retry_after_seconds: int, **extra: Any) -> None:
        super().__init__(detail, retry_after_seconds=retry_after_seconds, **extra)
        self.retry_after_seconds = retry_after_seconds


class PayloadTooLargeError(APIError):
    """A request body beyond what any legitimate call needs."""

    status_code = 413
    problem_type = "payload-too-large"
    title = "Request body too large"


class ConfigurationError(APIError):
    """A required setting is missing or unusable.

    A 500 because the caller did nothing wrong. The detail names the setting
    and never its value, so the message is safe to return and still tells an
    operator what to fix.
    """

    status_code = 500
    problem_type = "misconfigured"
    title = "Service is misconfigured"


class UpstreamError(APIError):
    """A dependency this service needs did not answer usefully.

    503 rather than 500: the request may well succeed later, and a client that
    can distinguish the two can retry the one that is worth retrying.
    """

    status_code = 503
    problem_type = "upstream-unavailable"
    title = "Upstream service unavailable"
