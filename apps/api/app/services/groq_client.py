"""Resilient Groq client.

Everything here exists because a language model is a remote dependency that
fails in ways the rest of this system must not inherit. The deterministic
engines are reproducible; this is the boundary where that stops being true, so
the boundary is where the guarantees are enforced.

**A deadline that actually binds.** Per-attempt timeouts alone do not bound a
request: three attempts at thirty seconds is ninety seconds plus backoff. Every
call carries one deadline covering all attempts and all sleeps, checked before
each attempt and used to shorten the last timeout, so a 5xx storm cannot hang a
caller past the configured budget.

**Backoff that is bounded and jittered.** Exponential, capped, with full
jitter. Without jitter, N variants that fail together retry together and
recreate the burst that caused the failure.

**A breaker that fails fast.** After enough consecutive failures the client
refuses to send, until a cooldown lets one trial request through. Queueing work
behind a dead provider multiplies an outage. The breaker counts failed
*attempts*, not failed calls, so a single request that burns its whole retry
budget against a dead provider trips it — which is the intent: five failures in
a row mean the same thing however they were grouped.

**A key that cannot leak.** It is a ``SecretStr`` in settings, read exactly
once at header construction, and never placed in a log record or an exception
message. ``test_groq_client`` asserts this against real log capture.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

from app.core.config import Settings, get_settings
from app.services.errors import (
    CircuitOpenError,
    LLMAuthError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMDeadlineExceededError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

#: USD per million tokens, from Groq's published pricing. A model that is not
#: listed reports ``None`` cost rather than a guess: an invented number in
#: telemetry is worse than an absent one, because it will be summed.
PRICING: Final[dict[str, tuple[float, float]]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}

#: Base for exponential backoff, and the ceiling any single sleep may reach.
BACKOFF_BASE_SECONDS: Final[float] = 0.5
BACKOFF_MAX_SECONDS: Final[float] = 8.0


@dataclass(frozen=True, slots=True)
class Completion:
    """One successful model response and what it cost to obtain."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    attempts: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def cost_usd(self) -> float | None:
        """Estimated cost, or ``None`` for a model with no published price."""
        price = PRICING.get(self.model)
        if price is None:
            return None
        prompt_rate, completion_rate = price
        return (self.prompt_tokens * prompt_rate + self.completion_tokens * completion_rate) / 1e6

    def parse_json(self) -> dict[str, Any]:
        """Parse the content as a JSON object.

        Raises :class:`~app.services.errors.LLMResponseError` rather than
        letting a ``JSONDecodeError`` escape, so callers handle one hierarchy.
        """
        try:
            parsed = json.loads(self.content)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"model returned malformed JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError(f"expected a JSON object, got {type(parsed).__name__}")
        return parsed


@dataclass
class _Breaker:
    """Consecutive-failure circuit breaker.

    Deliberately counts *consecutive* failures: an intermittent error rate is a
    fact of remote calls and should not trip a breaker, while five failures in
    a row means the provider is down and further requests are waste.
    """

    threshold: int
    cooldown_seconds: float
    failures: int = 0
    opened_at: float | None = None

    def allow(self, now: float) -> bool:
        if self.opened_at is None:
            return True
        if now - self.opened_at >= self.cooldown_seconds:
            # Half-open: let one trial through. It either resets the breaker or
            # re-opens it, and either way the cooldown starts again.
            self.opened_at = None
            self.failures = 0
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self, now: float) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = now


@dataclass
class GroqClient:
    """Async client for Groq's OpenAI-compatible chat completions endpoint.

    The transport is injected so tests can drive every branch through
    ``httpx.MockTransport`` without a network, and so a caller can supply a
    pooled client in production.
    """

    settings: Settings = field(default_factory=get_settings)
    transport: httpx.AsyncBaseTransport | None = None
    _breaker: _Breaker = field(init=False)

    def __post_init__(self) -> None:
        self._breaker = _Breaker(
            threshold=self.settings.groq_breaker_threshold,
            cooldown_seconds=self.settings.groq_breaker_cooldown_seconds,
        )

    # -------------------------------------------------------------- public

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
    ) -> Completion:
        """Request a JSON completion, retrying transient failures within the deadline.

        ``schema`` selects strict schema-constrained decoding where the model
        supports it; without one the request still asks for JSON, which every
        Groq model honours syntactically.
        """
        payload = self._payload(system, user, schema, temperature, max_tokens)
        started = time.monotonic()
        deadline = started + self.settings.groq_deadline_seconds

        last: LLMError | None = None
        for attempt in range(1, self.settings.groq_max_retries + 2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMDeadlineExceededError(
                    f"deadline of {self.settings.groq_deadline_seconds}s elapsed "
                    f"after {attempt - 1} attempt(s)"
                ) from last

            if not self._breaker.allow(time.monotonic()):
                raise CircuitOpenError(
                    f"circuit open after {self._breaker.failures} consecutive failures"
                )

            try:
                completion = await self._attempt(payload, remaining, started, attempt)
            except LLMError as exc:
                last = exc
                self._breaker.record_failure(time.monotonic())
                if not exc.retryable or attempt > self.settings.groq_max_retries:
                    raise
                await self._backoff(attempt, exc, deadline)
                continue

            self._breaker.record_success()
            self._log(completion)
            return completion

        # Unreachable: the loop either returns or raises. Kept as a typed
        # guarantee rather than relying on the reader to prove it.
        raise LLMDeadlineExceededError("retries exhausted")  # pragma: no cover

    # -------------------------------------------------------------- internals

    def _payload(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        response_format: dict[str, Any] = {"type": "json_object"}
        if schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": "plot_variant", "strict": True, "schema": schema},
            }
        return {
            "model": self.settings.groq_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
        }

    def _headers(self) -> dict[str, str]:
        """The only place the key is read.

        Raises before any request when it is absent, so a misconfigured
        deployment fails with a clear message instead of a 401 the operator has
        to interpret.
        """
        key = self.settings.groq_api_key
        if key is None or not key.get_secret_value():
            raise LLMConfigurationError(
                "GROQ_API_KEY is not set; the Groq client cannot send requests"
            )
        return {
            "Authorization": f"Bearer {key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    async def _attempt(
        self, payload: dict[str, Any], remaining: float, started: float, attempt: int
    ) -> Completion:
        timeout = min(self.settings.groq_timeout_seconds, remaining)
        url = f"{self.settings.groq_base_url.rstrip('/')}/chat/completions"

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"attempt {attempt} timed out after {timeout:.1f}s") from exc
        except httpx.HTTPError as exc:
            # Deliberately not interpolating the exception's repr, which can
            # carry the request headers and therefore the key.
            raise LLMConnectionError(
                f"attempt {attempt} could not reach the provider ({type(exc).__name__})"
            ) from exc

        self._raise_for_status(response)
        return self._to_completion(response, started, attempt)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code in (401, 403):
            raise LLMAuthError(f"provider rejected the credential ({response.status_code})")
        if response.status_code == 429:
            raise LLMRateLimitError(
                "provider rate limit reached", retry_after=_retry_after(response)
            )
        if response.status_code >= 500:
            raise LLMServerError(f"provider error {response.status_code}")
        raise LLMResponseError(f"unexpected status {response.status_code}")

    def _to_completion(self, response: httpx.Response, started: float, attempt: int) -> Completion:
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMResponseError("provider returned a non-JSON envelope") from exc

        choices = body.get("choices") or []
        if not choices:
            raise LLMResponseError("provider returned no choices")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise LLMResponseError("provider returned an empty message")

        usage = body.get("usage") or {}
        return Completion(
            content=content,
            model=str(body.get("model", self.settings.groq_model)),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=(time.monotonic() - started) * 1000,
            attempts=attempt,
        )

    async def _backoff(self, attempt: int, exc: LLMError, deadline: float) -> None:
        """Sleep before the next attempt, never past the deadline.

        Full jitter over the exponential window: N variants failing together
        must not retry together and recreate the burst.
        """
        window = min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)
        # Suppression justified: this jitter spreads retries, it is not a
        # security primitive.
        delay = random.uniform(0, window)  # noqa: S311
        if isinstance(exc, LLMRateLimitError) and exc.retry_after is not None:
            # Never retry sooner than the provider asked.
            delay = max(delay, exc.retry_after)

        remaining = deadline - time.monotonic()
        if delay >= remaining:
            raise LLMDeadlineExceededError(
                f"backoff of {delay:.1f}s would exceed the remaining deadline"
            ) from exc
        await asyncio.sleep(delay)

    def _log(self, completion: Completion) -> None:
        logger.info(
            "groq completion",
            extra={
                "model": completion.model,
                "prompt_tokens": completion.prompt_tokens,
                "completion_tokens": completion.completion_tokens,
                "total_tokens": completion.total_tokens,
                "latency_ms": round(completion.latency_ms, 2),
                "attempts": completion.attempts,
                "cost_usd": completion.cost_usd(),
            },
        )


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        # The header also permits an HTTP date. Rather than parse it and risk
        # a wrong number, fall back to the client's own backoff.
        return None
