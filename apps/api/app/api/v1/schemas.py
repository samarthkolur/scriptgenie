"""Request and response shapes for the v1 API.

Separate from ``app.domain`` on purpose. The domain models are the vocabulary
the engines speak and are free to change as the engines do; these are a
published contract that a browser and a generated TypeScript client depend on.
Collapsing the two would mean an internal refactor could silently change what
the API promises.

Where a shape is genuinely identical the domain model is reused directly —
:class:`~app.domain.ConstraintBundle` is the same thing on the wire as it is in
the engine, and restating it would create two definitions to keep in step.
What is defined here is everything the wire needs and the engines do not: ids,
timestamps, pagination, and the flattened views a UI actually renders.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain import (
    Conflict,
    ConstraintBundle,
    GenerationEnvelope,
    ResolutionChoice,
    ResolutionDelta,
    Severity,
)


class ApiModel(BaseModel):
    """Base for every wire model: closed to unknown fields.

    ``extra="forbid"`` on requests so a client sending ``varient_count`` is
    told rather than silently given the default, which is how a typo becomes a
    bug report about generation ignoring a setting.
    """

    model_config = ConfigDict(extra="forbid")


Title = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]
Description = Annotated[str, StringConstraints(max_length=2000)]
Notes = Annotated[str, StringConstraints(max_length=4000)]


# ------------------------------------------------------------- knowledge base


class GenreOption(ApiModel):
    id: str
    label: str
    hybrid_friendly: tuple[str, ...]


class ClassificationOption(ApiModel):
    id: str
    label: str
    min_audience_age: int


class RatingSystemOption(ApiModel):
    id: str
    label: str
    territory: str
    classifications: tuple[ClassificationOption, ...]


class BudgetTierOption(ApiModel):
    """A tier as the wizard shows it.

    ``scope`` is included because a writer choosing a tier is choosing a
    location count and a speaking-cast ceiling, and a picker that shows only
    dollar bands asks them to guess at the thing they actually care about.
    """

    id: str
    label: str
    order: int
    min_usd: int
    max_usd: int | None
    guild_context: str
    scope: dict[str, Any]


class TerritoryOption(ApiModel):
    id: str
    label: str
    rating_system: str


class ArchetypeOption(ApiModel):
    id: str
    label: str
    description: str
    min_beats: int


class KbOptions(ApiModel):
    """Everything the constraint wizard needs to render, in one request.

    One call rather than five: these are always needed together, and a wizard
    that renders its budget step before its genre step has arrived is a wizard
    that flickers.
    """

    kb_version: str
    genres: tuple[GenreOption, ...]
    rating_systems: tuple[RatingSystemOption, ...]
    budget_tiers: tuple[BudgetTierOption, ...]
    territories: tuple[TerritoryOption, ...]
    archetypes: tuple[ArchetypeOption, ...]


# ------------------------------------------------------------------ conflicts


class DetectRequest(ApiModel):
    bundle: ConstraintBundle


class SeverityCounts(ApiModel):
    hard: int
    soft: int
    advisory: int


class ConflictReportResponse(ApiModel):
    """A conflict report, with the counts a UI gates on already computed.

    ``blocking`` is derived server-side rather than left to the client. It is
    the flag that disables the Generate button, and a client that computed it
    itself could disagree with the endpoint that enforces it.
    """

    kb_version: str
    bundle: ConstraintBundle
    conflicts: tuple[Conflict, ...]
    counts: SeverityCounts
    rules_evaluated: int
    blocking: bool


class ResolveRequest(ApiModel):
    bundle: ConstraintBundle
    choices: tuple[ResolutionChoice, ...] = ()


class ResolveResponse(ApiModel):
    """The resolved bundle and the envelope it produces.

    Both, because they answer different questions: the deltas say what the
    writer's choices changed, and the envelope says what the generator will
    actually be held to.
    """

    kb_version: str
    original: ConstraintBundle
    bundle: ConstraintBundle
    choices: tuple[ResolutionChoice, ...]
    deltas: tuple[ResolutionDelta, ...]
    envelope: GenerationEnvelope
    remaining_conflicts: tuple[Conflict, ...]


# ------------------------------------------------------------------- projects


class ProjectCreate(ApiModel):
    title: Title
    description: Description | None = None


class ProjectUpdate(ApiModel):
    """A partial update. Every field optional; omitted means unchanged.

    Distinct from :class:`ProjectCreate` so that omitting a title on a PATCH is
    "leave it alone" rather than "clear it", which a shared model could not
    express.
    """

    title: Title | None = None
    description: Description | None = None
    status: str | None = None


class Project(ApiModel):
    id: UUID
    title: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectList(ApiModel):
    projects: tuple[Project, ...]
    total: int


# ----------------------------------------------------------------- generation


class GenerateRequest(ApiModel):
    """Ask for variants inside a bundle the writer has already resolved.

    The bundle and the choices are sent together rather than the client
    referencing a stored report. A report is a pure function of a bundle and a
    knowledge base version, so re-deriving it here costs microseconds and
    removes an entire class of bug where the stored report and the submitted
    bundle have drifted apart.
    """

    bundle: ConstraintBundle
    choices: tuple[ResolutionChoice, ...] = ()
    variant_count: int = Field(default=5, ge=1, le=10)
    #: Permutes only equally-scored archetypes, so a seed changes which of two
    #: equally good structures is chosen and never whether the choice was good.
    seed: int = Field(default=0, ge=0)


class BeatOut(ApiModel):
    index: int
    function: str
    summary: str


class DimensionCheckOut(ApiModel):
    dimension: str
    permitted: int
    observed: int
    satisfied: bool


class ScopeCheckOut(ApiModel):
    parameter: str
    limit: int | None
    observed: int
    satisfied: bool


class SatisfactionOut(ApiModel):
    dimension_checks: tuple[DimensionCheckOut, ...]
    scope_checks: tuple[ScopeCheckOut, ...]
    satisfied: bool
    violations: tuple[str, ...]


class VariantProvenanceOut(ApiModel):
    """What produced this variant.

    Every field is here so a concept can be reproduced or explained months
    later. A variant that cannot name its inputs is not a research artefact.
    """

    kb_version: str
    prompt_version: str
    model: str
    archetype_id: str
    seed: int
    attempts: int
    repaired: bool


class Variant(ApiModel):
    id: UUID
    variant_index: int
    archetype_id: str
    title: str
    logline: str
    beats: tuple[BeatOut, ...]
    locations: tuple[str, ...]
    named_characters: tuple[str, ...]
    relaxations: tuple[str, ...]
    satisfaction: SatisfactionOut
    #: Per-axis verdict: ``PASS``, ``FLAGGED`` or ``NEEDS_REVIEW``.
    verdicts: dict[str, str]
    #: True only when every axis returned PASS. FLAGGED and NEEDS_REVIEW both
    #: make it false — an axis nobody could check has not been checked.
    surfaceable: bool
    favourite: bool
    notes: str | None
    provenance: VariantProvenanceOut
    created_at: datetime


class FailedVariantOut(ApiModel):
    """A variant that could not be produced, and why.

    Returned alongside the successes rather than collapsing the batch. Naming
    the archetype means the caller can say which structure is missing rather
    than only that something is.
    """

    archetype_id: str
    variant_index: int
    reason: str
    error_type: str


class GenerationRun(ApiModel):
    id: UUID
    project_id: UUID
    status: str
    requested_count: int
    generated_count: int
    failed_count: int
    seed: int
    model: str
    prompt_version: str
    kb_version: str
    elapsed_ms: float | None
    created_at: datetime
    completed_at: datetime | None


class GenerationResponse(ApiModel):
    run: GenerationRun
    envelope: GenerationEnvelope
    variants: tuple[Variant, ...]
    failures: tuple[FailedVariantOut, ...]


class VariantList(ApiModel):
    variants: tuple[Variant, ...]
    total: int


# -------------------------------------------------------------------- feedback


class FeedbackRequest(ApiModel):
    """A rating, a note, or a report that a rule fired wrongly.

    The false-positive channel is the research contribution here: risk 1 in the
    analysis is that the rule set flags tensions working writers do not
    recognise, and without a first-class way to say so that evidence never
    reaches the knowledge base.
    """

    rating: int | None = Field(default=None, ge=1, le=5)
    notes: Notes | None = None
    false_positive_rule_id: str | None = None


class Feedback(ApiModel):
    id: UUID
    variant_id: UUID
    rating: int | None
    notes: str | None
    false_positive_rule_id: str | None
    created_at: datetime


# --------------------------------------------------------------------- export


class ExportBundle(ApiModel):
    """A project as a self-contained, reproducible document.

    Carries the constraint bundle, the resolutions, the envelope and every
    version that shaped the output. An export that named only the variants
    would be a set of loglines nobody could defend.
    """

    exported_at: datetime
    project: Project
    kb_version: str
    prompt_version: str
    bundle: ConstraintBundle | None
    conflicts: tuple[Conflict, ...]
    choices: tuple[ResolutionChoice, ...]
    envelope: GenerationEnvelope | None
    variants: tuple[Variant, ...]
    markdown: str


def counts_from(conflicts: tuple[Conflict, ...]) -> SeverityCounts:
    """Severity tallies, with every severity present rather than inferred."""
    by_severity = dict.fromkeys(Severity, 0)
    for conflict in conflicts:
        by_severity[conflict.severity] += 1
    return SeverityCounts(
        hard=by_severity[Severity.HARD],
        soft=by_severity[Severity.SOFT],
        advisory=by_severity[Severity.ADVISORY],
    )
