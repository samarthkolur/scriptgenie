"""Language-model failure types.

Typed rather than a single exception because the caller's correct response
differs sharply between them. A generation service can drop one variant and
keep the batch when a single call returns unusable JSON; it must not retry into
a rate limit, and it should surface a bad key immediately rather than burning
the retry budget on a request that can never succeed.

:attr:`LLMError.retryable` encodes that distinction once, so no caller has to
re-derive which failures are worth another attempt.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every language-model failure.

    ``retryable`` is a class attribute rather than a parameter so the answer
    is a property of the failure kind, not of the site that raised it.
    """

    retryable: bool = False


class LLMConfigurationError(LLMError):
    """The client is not usable as configured -- typically a missing API key.

    Never retryable, and deliberately distinct from an auth rejection: this one
    is detectable before any request is sent.
    """


class LLMAuthError(LLMError):
    """The provider rejected the credential (401 or 403).

    Not retryable. A key that is wrong now will be wrong in two seconds, and
    retrying only delays the operator seeing the real problem.
    """


class LLMRateLimitError(LLMError):
    """The provider applied a rate limit (429).

    Retryable, but the backoff honours ``retry_after`` when the provider sends
    one, because guessing shorter than the stated wait is how a client turns a
    rate limit into a ban.
    """

    retryable = True

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message)


class LLMServerError(LLMError):
    """The provider failed (5xx). Retryable."""

    retryable = True


class LLMTimeoutError(LLMError):
    """A single attempt exceeded its timeout. Retryable."""

    retryable = True


class LLMConnectionError(LLMError):
    """The request never reached the provider. Retryable."""

    retryable = True


class LLMDeadlineExceededError(LLMError):
    """The overall deadline elapsed across attempts.

    Not retryable by definition: the budget for this logical request is spent,
    which is the guarantee that a 5xx storm cannot hang a caller indefinitely.
    """


class LLMResponseError(LLMError):
    """The provider answered, but the body was not usable.

    Covers malformed JSON and a well-formed envelope with no content. Not
    retryable at the transport layer -- the request succeeded, so retrying it
    unchanged is unlikely to help. Stage 3.3 repairs these at a higher level,
    where the prompt can be amended.
    """


class CircuitOpenError(LLMError):
    """The breaker is open and the request was refused without being sent.

    Failing immediately is the point: once the provider is known to be down,
    queueing more work behind the same timeout multiplies the outage rather
    than riding it out.
    """
