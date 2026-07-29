"""Reading and writing the domain's tables.

One function per question the application actually asks. The
:class:`~app.db.supabase.SupabaseClient` beneath knows about HTTP and knows
nothing about projects; this module knows about projects and nothing about
HTTP, and the split is what keeps PostgREST filter syntax out of the routers.

Two rules run through the whole file.

*Every call carries the user, and every write sets ``owner_id`` from the
verified token.* Never from the request body — a body-supplied owner is a
request to write as somebody else. The composite foreign keys in the schema
would refuse it and row level security would refuse it again, but neither is a
reason to hand the database a value the caller chose.

*Absence is returned, not raised.* Under row level security "no such row" and
"not yours" are the same answer, and both are answers the caller should decide
about. Turning one into a 404 is the router's job.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.security import AuthenticatedUser
from app.db.supabase import JsonObject, SupabaseClient
from app.domain import (
    Conflict,
    ConflictReport,
    ConstraintBundle,
    ConstraintSatisfactionReport,
    GenerationEnvelope,
    PlotVariant,
    ResolutionChoice,
    ResolutionDelta,
    Severity,
)
from app.services.generation_service import GeneratedVariant

#: Newest first, everywhere. A library is read as "what was I working on", and
#: nobody scrolls to the bottom for that.
NEWEST_FIRST = "created_at.desc"


def _eq(value: object) -> str:
    """A PostgREST equality filter."""
    return f"eq.{value}"


# ------------------------------------------------------------------- projects


async def create_project(
    db: SupabaseClient, user: AuthenticatedUser, *, title: str, description: str | None
) -> JsonObject:
    return await db.insert_one(
        "projects",
        {"owner_id": str(user.id), "title": title, "description": description},
        user=user,
    )


async def list_projects(
    db: SupabaseClient, user: AuthenticatedUser, *, limit: int, offset: int
) -> list[JsonObject]:
    return await db.select(
        "projects",
        user=user,
        params={"order": NEWEST_FIRST, "limit": str(limit), "offset": str(offset)},
    )


async def count_projects(db: SupabaseClient, user: AuthenticatedUser) -> int:
    return await db.count("projects", user=user)


async def get_project(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID
) -> JsonObject | None:
    return await db.select_one("projects", user=user, params={"id": _eq(project_id)})


async def update_project(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID, values: JsonObject
) -> JsonObject | None:
    rows = await db.update("projects", values, user=user, params={"id": _eq(project_id)})
    return rows[0] if rows else None


async def delete_project(db: SupabaseClient, user: AuthenticatedUser, project_id: UUID) -> bool:
    return bool(await db.delete("projects", user=user, params={"id": _eq(project_id)}))


async def set_project_status(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID, status: str
) -> None:
    await db.update("projects", {"status": status}, user=user, params={"id": _eq(project_id)})


# ------------------------------------------------- bundles, reports, envelopes


def _bundle_columns(bundle: ConstraintBundle) -> JsonObject:
    """A bundle shredded into the columns the library filters on."""
    return {
        "genre_primary": bundle.genre.primary,
        "genre_secondary": bundle.genre.secondary,
        "audience_min_age": bundle.audience.min_age,
        "audience_max_age": bundle.audience.max_age,
        "rating_system": bundle.rating.system,
        "rating_classification": bundle.rating.classification,
        "budget_tier_id": bundle.budget_tier_id,
        "territory_ids": list(bundle.territories.ids),
    }


async def save_bundle(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID, bundle: ConstraintBundle
) -> JsonObject:
    """Store the writer's inputs as a new row."""
    return await db.insert_one(
        "constraint_bundles",
        {
            "project_id": str(project_id),
            "owner_id": str(user.id),
            **_bundle_columns(bundle),
        },
        user=user,
    )


async def bundle_is_cited(db: SupabaseClient, user: AuthenticatedUser, bundle_id: UUID) -> bool:
    """Whether any conflict report was produced from this bundle."""
    return await db.count("conflict_reports", user=user, params={"bundle_id": _eq(bundle_id)}) > 0


async def save_draft_bundle(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID, bundle: ConstraintBundle
) -> JsonObject:
    """Store the project's working draft, overwriting the previous draft.

    The wizard saves on every step, so appending a row per save would leave a
    project carrying dozens of near-identical bundles and would make
    :func:`latest_bundle` — which the export reads — return whichever draft the
    writer last touched rather than the one a run was actually generated from.

    So a draft is overwritten in place, but only while it is still a draft. A
    bundle that a conflict report already cites is evidence: the report records
    what was detected *from that bundle*, and rewriting its columns would change
    what a stored verdict was about without changing the verdict. Once cited,
    the next save starts a new row and the old one stays as it was.
    """
    latest = await latest_bundle(db, user, project_id)
    if latest is not None:
        bundle_id = UUID(str(latest["id"]))
        if not await bundle_is_cited(db, user, bundle_id):
            rows = await db.update(
                "constraint_bundles",
                _bundle_columns(bundle),
                user=user,
                params={"id": _eq(bundle_id)},
            )
            if rows:
                return rows[0]
    return await save_bundle(db, user, project_id, bundle)


async def save_conflict_report(
    db: SupabaseClient,
    user: AuthenticatedUser,
    project_id: UUID,
    bundle_id: UUID,
    report: ConflictReport,
) -> JsonObject:
    counts = report.counts()
    return await db.insert_one(
        "conflict_reports",
        {
            "bundle_id": str(bundle_id),
            "project_id": str(project_id),
            "owner_id": str(user.id),
            "kb_version": report.kb_version,
            "rules_evaluated": report.rules_evaluated,
            "conflicts": [conflict.model_dump(mode="json") for conflict in report.conflicts],
            # Stored rather than derived on read: the generation endpoint gates
            # on "any unresolved HARD", and that question must not require
            # unpacking a JSONB array on every request.
            "hard_count": counts[Severity.HARD],
            "soft_count": counts[Severity.SOFT],
            "advisory_count": counts[Severity.ADVISORY],
        },
        user=user,
    )


async def save_resolutions(
    db: SupabaseClient,
    user: AuthenticatedUser,
    project_id: UUID,
    report_id: UUID,
    choices: tuple[ResolutionChoice, ...],
    deltas: tuple[ResolutionDelta, ...],
) -> list[JsonObject]:
    """Record each choice with what it actually moved.

    Nothing to store is a real outcome — a bundle with no conflicts has no
    choices — and inserting an empty list would be a request PostgREST rejects.
    """
    if not choices:
        return []

    by_rule = {delta.rule_id: delta for delta in deltas}
    rows = [
        {
            "report_id": str(report_id),
            "project_id": str(project_id),
            "owner_id": str(user.id),
            "rule_id": choice.rule_id,
            "resolution_id": choice.resolution_id,
            "delta": (
                by_rule[choice.rule_id].model_dump(mode="json") if choice.rule_id in by_rule else {}
            ),
        }
        for choice in choices
    ]
    return await db.insert("resolutions", rows, user=user)


async def save_envelope(
    db: SupabaseClient,
    user: AuthenticatedUser,
    project_id: UUID,
    report_id: UUID,
    kb_version: str,
    envelope: GenerationEnvelope,
) -> JsonObject:
    return await db.insert_one(
        "scope_envelopes",
        {
            "report_id": str(report_id),
            "project_id": str(project_id),
            "owner_id": str(user.id),
            "kb_version": kb_version,
            "envelope": envelope.model_dump(mode="json"),
        },
        user=user,
    )


async def latest_envelope(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID
) -> JsonObject | None:
    return await db.select_one(
        "scope_envelopes",
        user=user,
        params={"project_id": _eq(project_id), "order": NEWEST_FIRST},
    )


async def latest_report(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID
) -> JsonObject | None:
    return await db.select_one(
        "conflict_reports",
        user=user,
        params={"project_id": _eq(project_id), "order": NEWEST_FIRST},
    )


async def latest_bundle(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID
) -> JsonObject | None:
    return await db.select_one(
        "constraint_bundles",
        user=user,
        params={"project_id": _eq(project_id), "order": NEWEST_FIRST},
    )


async def resolutions_for_report(
    db: SupabaseClient, user: AuthenticatedUser, report_id: UUID
) -> list[JsonObject]:
    return await db.select(
        "resolutions",
        user=user,
        params={"report_id": _eq(report_id), "order": "created_at.asc"},
    )


# ------------------------------------------------------------ generation runs


async def open_run(
    db: SupabaseClient,
    user: AuthenticatedUser,
    *,
    project_id: UUID,
    envelope_id: UUID,
    requested: int,
    seed: int,
    model: str,
    prompt_version: str,
    kb_version: str,
) -> JsonObject:
    """Record the run before calling the model.

    Opened first so that a batch which crashes mid-flight leaves a row saying
    it was attempted. A run written only on success would make every failure
    invisible, including the ones that spent tokens.
    """
    return await db.insert_one(
        "generation_runs",
        {
            "envelope_id": str(envelope_id),
            "project_id": str(project_id),
            "owner_id": str(user.id),
            "status": "running",
            "requested_count": requested,
            "seed": seed,
            "model": model,
            "prompt_version": prompt_version,
            "kb_version": kb_version,
        },
        user=user,
    )


async def close_run(
    db: SupabaseClient,
    user: AuthenticatedUser,
    run_id: UUID,
    *,
    status: str,
    generated: int,
    failed: int,
    elapsed_ms: float,
    failures: list[JsonObject],
) -> JsonObject | None:
    rows = await db.update(
        "generation_runs",
        {
            "status": status,
            "generated_count": generated,
            "failed_count": failed,
            "elapsed_ms": elapsed_ms,
            "failures": failures,
            "completed_at": datetime.now(UTC).isoformat(),
        },
        user=user,
        params={"id": _eq(run_id)},
    )
    return rows[0] if rows else None


async def count_runs_since(db: SupabaseClient, user: AuthenticatedUser, since: datetime) -> int:
    """How many runs this user has started since ``since``.

    The rate limiter's whole question. Counted in the database rather than in
    process memory so the limit holds across every instance of this service,
    and so a restart does not hand everybody a fresh allowance.
    """
    return await db.count(
        "generation_runs",
        user=user,
        params={"created_at": f"gte.{since.isoformat()}"},
    )


# --------------------------------------------------------------- plot variants


async def save_variants(
    db: SupabaseClient,
    user: AuthenticatedUser,
    *,
    project_id: UUID,
    run_id: UUID,
    records: list[tuple[GeneratedVariant, ConstraintSatisfactionReport, dict[str, str], bool]],
) -> list[JsonObject]:
    if not records:
        return []

    rows = [
        {
            "run_id": str(run_id),
            "project_id": str(project_id),
            "owner_id": str(user.id),
            "variant_index": generated.variant.archetype.variant_index,
            "archetype_id": generated.provenance.archetype_id,
            "title": generated.variant.title,
            "logline": generated.variant.logline,
            "beats": [beat.model_dump(mode="json") for beat in generated.variant.beats],
            "locations": list(generated.locations),
            "named_characters": list(generated.named_characters),
            "relaxations": list(generated.relaxations),
            "satisfaction": _satisfaction_json(satisfaction),
            "verdicts": verdicts,
            # As the verifier decided it. A UI cannot re-derive this more
            # generously, and FLAGGED and NEEDS_REVIEW both make it false.
            "surfaceable": surfaceable,
            "provenance": {
                "kb_version": generated.provenance.kb_version,
                "prompt_version": generated.provenance.prompt_version,
                "model": generated.provenance.model,
                "archetype_id": generated.provenance.archetype_id,
                "seed": generated.provenance.seed,
                "attempts": generated.provenance.attempts,
                "repaired": generated.provenance.repaired,
            },
        }
        for generated, satisfaction, verdicts, surfaceable in records
    ]
    return await db.insert("plot_variants", rows, user=user)


def _satisfaction_json(report: ConstraintSatisfactionReport) -> JsonObject:
    """The satisfaction report as the wire and the database both want it.

    Passing checks are kept. A report listing only failures would make
    "verified for scope" indistinguishable from "not checked", and that
    distinction is the product.
    """
    return {
        "dimension_checks": [
            {
                "dimension": check.dimension.value,
                "permitted": int(check.permitted),
                "observed": int(check.observed),
                "satisfied": check.satisfied,
            }
            for check in report.dimension_checks
        ],
        "scope_checks": [
            {
                "parameter": check.parameter,
                "limit": check.limit,
                "observed": check.observed,
                "satisfied": check.satisfied,
            }
            for check in report.scope_checks
        ],
        "satisfied": report.satisfied,
        "violations": list(report.violations()),
    }


async def list_variants(
    db: SupabaseClient,
    user: AuthenticatedUser,
    project_id: UUID,
    *,
    limit: int,
    offset: int,
) -> list[JsonObject]:
    return await db.select(
        "plot_variants",
        user=user,
        params={
            "project_id": _eq(project_id),
            "order": "created_at.desc,variant_index.asc",
            "limit": str(limit),
            "offset": str(offset),
        },
    )


async def count_variants(db: SupabaseClient, user: AuthenticatedUser, project_id: UUID) -> int:
    return await db.count("plot_variants", user=user, params={"project_id": _eq(project_id)})


async def get_variant(
    db: SupabaseClient, user: AuthenticatedUser, variant_id: UUID
) -> JsonObject | None:
    return await db.select_one("plot_variants", user=user, params={"id": _eq(variant_id)})


# ------------------------------------------------------------------- feedback


async def save_feedback(
    db: SupabaseClient,
    user: AuthenticatedUser,
    variant_id: UUID,
    *,
    rating: int | None,
    notes: str | None,
    false_positive_rule_id: str | None,
) -> JsonObject:
    return await db.insert_one(
        "variant_feedback",
        {
            "variant_id": str(variant_id),
            "owner_id": str(user.id),
            "rating": rating,
            "notes": notes,
            "false_positive_rule_id": false_positive_rule_id,
        },
        user=user,
    )


# --------------------------------------------------------------- usage events


async def record_usage(
    db: SupabaseClient,
    *,
    owner_id: UUID,
    project_id: UUID | None,
    run_id: UUID | None,
    event_type: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float | None,
) -> None:
    """Write one accounting row under the service role.

    The single sanctioned row level security bypass. A client that could write
    here could understate its own spend, and one that could delete could erase
    the evidence of a rate limit it exceeded — so the policy denies every
    client and this writes it instead.
    """
    await db.as_service(
        "usage_events",
        {
            "owner_id": str(owner_id),
            "project_id": str(project_id) if project_id is not None else None,
            "run_id": str(run_id) if run_id is not None else None,
            "event_type": event_type,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
        },
    )


# --------------------------------------------------------------- rehydration


def bundle_from_row(row: JsonObject) -> ConstraintBundle:
    """Rebuild a bundle from its stored columns.

    Validated on the way back rather than trusted. The row was written by this
    application, but it can also have been written by a migration, a backfill
    or a support query, and a bundle that no longer validates should fail here
    rather than three layers further in.
    """
    genre: dict[str, Any] = {"primary": row["genre_primary"]}
    if row.get("genre_secondary") is not None:
        genre["secondary"] = row["genre_secondary"]

    return ConstraintBundle.model_validate(
        {
            "genre": genre,
            "audience": {
                "min_age": row["audience_min_age"],
                "max_age": row["audience_max_age"],
            },
            "rating": {
                "system": row["rating_system"],
                "classification": row["rating_classification"],
            },
            "budget_tier_id": row["budget_tier_id"],
            "territories": {"ids": list(row["territory_ids"])},
        }
    )


def conflicts_from_row(row: JsonObject) -> tuple[Conflict, ...]:
    stored = row.get("conflicts") or []
    return tuple(Conflict.model_validate(item) for item in stored)


def envelope_from_row(row: JsonObject) -> GenerationEnvelope:
    return GenerationEnvelope.model_validate(row["envelope"])


def variant_from_row(row: JsonObject) -> PlotVariant:
    """Rebuild the domain variant. Used by the export, which re-renders beats."""
    return PlotVariant.model_validate(
        {
            "id": f"variant_{row['variant_index']}",
            "title": row["title"],
            "logline": row["logline"],
            "archetype": {
                "variant_index": row["variant_index"],
                "archetype_id": row["archetype_id"],
                "score": 0,
                "rationale": "rehydrated from storage",
            },
            "beats": row["beats"],
        }
    )
