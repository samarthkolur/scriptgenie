"""Accumulating what one request spent on the model.

A generation makes many model calls — one per variant, plus one verification
extraction per variant — and the accounting row has to record the total. Adding
a return value to every function between the router and the client would thread
token counts through five signatures that are otherwise about story structure,
and the first helper added after that would drop them.

A :class:`contextvars.ContextVar` holding a mutable meter avoids that, and it
is correct rather than merely convenient. Asyncio tasks inherit a *copy of the
context*, so each of the five concurrent variant tasks sees the same meter
**object** the request installed; mutating it is visible to the request that
started them, and no other request can observe it. That is exactly the sharing
the accounting needs and exactly the isolation it requires.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from types import TracebackType


@dataclass
class UsageMeter:
    """Running totals for one request's model spend.

    ``cost_usd`` is ``None`` until something priceable is recorded, and stays
    ``None`` if no call had a published price. A zero would be summed into a
    total that reads as free, which is worse than an absent number because
    nothing downstream can tell it apart from a genuinely free call.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cost_usd: float | None = None
    models: set[str] = field(default_factory=set)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
    ) -> None:
        self.calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.models.add(model)
        if cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + cost_usd


_meter: ContextVar[UsageMeter | None] = ContextVar("usage_meter", default=None)


def current_meter() -> UsageMeter | None:
    """The meter for the current request, or ``None`` outside one."""
    return _meter.get()


def record(
    *, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float | None
) -> None:
    """Add one completion to the current request's totals.

    A no-op when no meter is installed. Model calls happen in tests, in scripts
    and from the engines' own tooling, and none of those should have to install
    a meter to be allowed to run.
    """
    meter = _meter.get()
    if meter is not None:
        meter.record(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )


class measured:
    """Install a fresh meter for the duration of a block.

    ``async with measured() as meter:`` — the meter is readable after the block
    exits, which is when the accounting row is written.
    """

    def __init__(self) -> None:
        self.meter = UsageMeter()
        self._token: object = None

    def __enter__(self) -> UsageMeter:
        self._token = _meter.set(self.meter)
        return self.meter

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        from contextvars import Token

        assert isinstance(self._token, Token)
        _meter.reset(self._token)
