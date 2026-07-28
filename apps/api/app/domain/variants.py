"""Generated plot variants and the evidence that they respect their constraints.

The models here are the output side of the system, but the verification models
matter more than the variant models. :class:`ConstraintSatisfactionReport` is
what separates this system from asking a model nicely: a variant is not
"probably fine", it is checked axis by axis against the envelope it was
generated for, and every check is reported whether it passed or failed.

:class:`ArchetypeAssignment` exists because variant diversity has to be
architectural. Assigning a distinct structural container to each variant before
generation is what makes them genuinely different, rather than hoping repeated
sampling produces variety -- which the research shows it does not.

Nothing in this module calls a model. Generation belongs to Phase 3; these are
the shapes it must fill and the shapes Layer 3 checks.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.domain.constraints import (
    ContentThresholds,
    DomainModel,
    Identifier,
    ScopeEnvelope,
)
from app.domain.enums import ContentDimension, ContentLevel


class ArchetypeAssignment(DomainModel):
    """The structural container one variant is generated into.

    ``score`` and ``rationale`` are carried so the assignment can be defended.
    Selection is deterministic (Stage 2.5), so a reader who disagrees with the
    choice can see the affinity arithmetic that produced it rather than being
    asked to trust it.
    """

    variant_index: int = Field(ge=0)
    archetype_id: Identifier
    score: int = Field(ge=0)
    rationale: str = Field(min_length=1)


class PlotBeat(DomainModel):
    """One story beat, filling one slot of an archetype's blueprint.

    ``function`` is the slot from the blueprint and ``summary`` is what the
    generator put in it. Keeping both means a variant can be checked against the
    structure it was supposed to follow, instead of only being read.
    """

    index: int = Field(ge=0)
    function: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class PlotVariant(DomainModel):
    """One generated concept: a logline and the beats that carry it."""

    id: Identifier
    title: str = Field(min_length=1)
    logline: str = Field(min_length=1)
    archetype: ArchetypeAssignment
    beats: tuple[PlotBeat, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _beats_are_sequential(self) -> Self:
        expected = tuple(range(len(self.beats)))
        actual = tuple(beat.index for beat in self.beats)
        if actual != expected:
            raise ValueError(
                f"variant '{self.id}' has beat indices {list(actual)}; "
                f"expected {list(expected)} in order"
            )
        return self


class DimensionCheck(DomainModel):
    """One content axis, checked against what the bundle permits."""

    dimension: ContentDimension
    permitted: ContentLevel
    observed: ContentLevel

    @property
    def satisfied(self) -> bool:
        return self.observed <= self.permitted


class ScopeCheck(DomainModel):
    """One production bound, checked against what the budget permits.

    ``limit`` is optional because an unbounded tier imposes none; a check with
    no limit is satisfied by definition and is still reported, so the envelope
    reads completely rather than appearing to skip an axis.
    """

    parameter: str = Field(min_length=1)
    limit: int | None = None
    observed: int = Field(ge=0)

    @property
    def satisfied(self) -> bool:
        return self.limit is None or self.observed <= self.limit


class ConstraintSatisfactionReport(DomainModel):
    """Axis-by-axis evidence that one variant fits its constraints.

    Passing checks are retained deliberately. A report that listed only
    failures would make "verified for scope" indistinguishable from "not
    checked", and that distinction is the product.
    """

    variant_id: Identifier
    thresholds: ContentThresholds
    envelope: ScopeEnvelope
    dimension_checks: tuple[DimensionCheck, ...] = ()
    scope_checks: tuple[ScopeCheck, ...] = ()

    @property
    def satisfied(self) -> bool:
        return all(check.satisfied for check in self.dimension_checks) and all(
            check.satisfied for check in self.scope_checks
        )

    def violations(self) -> tuple[str, ...]:
        """Names of the axes that failed, in report order."""
        return tuple(
            [c.dimension.value for c in self.dimension_checks if not c.satisfied]
            + [c.parameter for c in self.scope_checks if not c.satisfied]
        )


class VerificationResult(DomainModel):
    """The verdict on a batch of variants, with the evidence behind it.

    ``verified`` is derived from the reports rather than stored, so it cannot
    disagree with them. A result claiming success while carrying a failed check
    is not a state this model can be constructed in.
    """

    kb_version: str = Field(min_length=1)
    reports: tuple[ConstraintSatisfactionReport, ...] = ()

    @property
    def verified(self) -> bool:
        return all(report.satisfied for report in self.reports)

    def failed_variants(self) -> tuple[Identifier, ...]:
        """Ids of variants with at least one failed check, in report order."""
        return tuple(report.variant_id for report in self.reports if not report.satisfied)
