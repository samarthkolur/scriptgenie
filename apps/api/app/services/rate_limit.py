"""Per-user generation limits, a global concurrency cap, and usage accounting.

Three separate protections against three separate failure modes, and conflating
them would leave two of the three unhandled.

*The per-user limit* stops one account consuming the shared model allowance.
It is counted in the **database**, over ``generation_runs`` in a rolling
window, not in process memory. In-process counters are the usual shortcut and
they are wrong in two ways that matter here: a second instance doubles every
user's allowance, and a restart hands everybody a fresh one — so the limit
would be loosest exactly when the service is least healthy.

*The concurrency cap* stops the service exceeding Groq's rate limit in
aggregate. That one is a property of this process's own outbound calls, so
unlike the per-user limit it genuinely belongs in memory — it lives as a
semaphore inside :class:`~app.services.groq_client.GroqClient`, where it wraps
every call rather than only the ones a caller remembered to route through it.

*Usage accounting* records what each run actually spent. It is written under
the service role because ``usage_events`` denies every client: an account that
could write its own accounting could understate its spend, and one that could
delete could erase the evidence of a limit it exceeded.

The counting window is deliberately a simple rolling one — "runs started in the
last hour" — rather than a token bucket. A writer who has spent their hour
should get their allowance back gradually as those runs age out, which is what
a rolling count does and what a fixed window resetting on the hour does not.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.api.v1 import schemas
from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.security import AuthenticatedUser
from app.db import repositories
from app.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


async def enforce_generation_limit(
    db: SupabaseClient, user: AuthenticatedUser, settings: Settings
) -> None:
    """Refuse a caller who has spent their allowance for the current window.

    Checked before anything is written and before any model is called, so a
    refused request costs one counting query and nothing else.

    ``Retry-After`` is computed from the window rather than fixed. Telling a
    caller to retry in an hour when their oldest run ages out in four minutes
    is technically safe and practically useless, and a client that is told a
    useless number ignores the header.
    """
    if settings.rate_limit_generations_per_window <= 0:
        # A limit of zero would be a service that refuses everything, which is
        # never the intent of setting a limit; it is how an operator disables
        # one. Stated here so the disabled path is deliberate rather than a
        # comparison that happens to pass.
        return

    window = timedelta(seconds=settings.rate_limit_window_seconds)
    since = datetime.now(UTC) - window

    used = await repositories.count_runs_since(db, user, since)
    if used < settings.rate_limit_generations_per_window:
        return

    retry_after = _retry_after_seconds(settings)
    logger.warning(
        "generation refused: rate limit reached",
        extra={
            "owner_id": str(user.id),
            "used": used,
            "window_seconds": settings.rate_limit_window_seconds,
        },
    )
    raise RateLimitedError(
        f"you have started {used} generation runs in the last "
        f"{_humanise(settings.rate_limit_window_seconds)}; the limit is "
        f"{settings.rate_limit_generations_per_window}",
        retry_after_seconds=retry_after,
        limit=settings.rate_limit_generations_per_window,
        used=used,
        window_seconds=settings.rate_limit_window_seconds,
    )


def _retry_after_seconds(settings: Settings) -> int:
    """How long until at least one run ages out of the window.

    Approximated as an even spread across the window rather than queried. The
    exact answer needs the oldest run's timestamp, which is a second round trip
    on a request that is already being refused; an even spread is never longer
    than the window and is always a number the client can act on.
    """
    limit = max(settings.rate_limit_generations_per_window, 1)
    spread = settings.rate_limit_window_seconds // limit
    return max(int(spread), 1)


def _humanise(seconds: int) -> str:
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "hour" if hours == 1 else f"{hours} hours"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return "minute" if minutes == 1 else f"{minutes} minutes"
    return f"{seconds} seconds"


async def record_generation_usage(
    db: SupabaseClient,
    user: AuthenticatedUser,
    project_id: UUID,
    response: schemas.GenerationResponse,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float | None,
) -> None:
    """Write the accounting row for one run.

    Never allowed to fail the request. The variants were generated, the tokens
    were spent, and losing the response because the accounting write failed
    would cost the user the thing they were charged for. The failure is logged
    loudly instead, because silent accounting loss is how a bill stops matching
    reality.
    """
    try:
        await repositories.record_usage(
            db,
            owner_id=user.id,
            project_id=project_id,
            run_id=response.run.id,
            event_type="generation",
            model=response.run.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    except Exception:
        logger.exception(
            "usage accounting could not be written",
            extra={
                "owner_id": str(user.id),
                "run_id": str(response.run.id),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )
