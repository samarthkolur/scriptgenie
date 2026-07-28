"""Detected constraint tensions, the choices offered, and what was chosen.

These models carry the output of Layer 1. Two invariants from the knowledge
base schema are re-asserted here rather than assumed, because a conflict that
reaches the writer malformed is worse than one that was never detected:

* a HARD conflict must carry its ``hard_rationale``. HARD blocks the work, so
  the burden of justification sits on the rule that blocks it.
* every conflict must offer at least two resolutions. Offering one option is an
  instruction wearing the costume of a choice.

The engine that fills these in arrives at Stage 2.2; nothing here evaluates a
predicate or reads the knowledge base.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from pydantic import Field, model_validator

from app.domain.constraints import ConstraintBundle, DomainModel, Identifier
from app.domain.enums import ContentDimension, ContentLevel, ResolutionEffectKind, Severity


class ResolutionEffect(DomainModel):
    """How choosing a resolution moves the bundle, if it moves it at all.

    A resolution with no effect is legitimate and common: it records that the
    writer saw the tension and chose to proceed, which is the whole point of
    the SOFT tier.
    """

    kind: ResolutionEffectKind
    dimension: ContentDimension | None = None
    guidance: str | None = None

    @model_validator(mode="after")
    def _clamp_names_its_dimension(self) -> Self:
        if (
            self.kind is ResolutionEffectKind.CLAMP_DIMENSION_TO_PERMITTED
            and self.dimension is None
        ):
            raise ValueError("clamp_dimension_to_permitted requires the dimension it clamps")
        return self


class ResolutionOption(DomainModel):
    """One way out of a conflict, offered to the writer.

    ``description`` is phrased in production terms -- what actually changes on
    the page -- because a resolution the writer cannot picture is not a choice
    they can make.
    """

    id: Identifier
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    effect: ResolutionEffect | None = None


class Conflict(DomainModel):
    """One tension between two constraints the writer supplied.

    ``explanation`` is already rendered: the knowledge base stores a template,
    and the detector substitutes the real values before the conflict is built,
    so nothing downstream needs the knowledge base to display it. ``evidence``
    keeps those substituted values so a report can be audited without re-running
    detection.
    """

    rule_id: Identifier
    severity: Severity
    title: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    hard_rationale: str | None = None
    resolutions: tuple[ResolutionOption, ...] = Field(min_length=2)
    evidence: Mapping[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _hard_conflicts_justify_themselves(self) -> Self:
        if self.severity is Severity.HARD and not self.hard_rationale:
            raise ValueError(
                f"conflict '{self.rule_id}' is HARD and must carry a hard_rationale; "
                "HARD blocks generation, so the justification is not optional"
            )
        return self


class ConflictReport(DomainModel):
    """Everything Layer 1 found for one bundle.

    Self-contained on purpose: it carries the bundle it judged and the
    knowledge base version that judged it, so a verdict can be explained months
    later without reconstructing the request. ``rules_evaluated`` is retained
    for the research telemetry -- how much of the rule set a bundle actually
    exercises is a finding, not a debug detail.
    """

    bundle: ConstraintBundle
    kb_version: str = Field(min_length=1)
    conflicts: tuple[Conflict, ...] = ()
    rules_evaluated: int = Field(default=0, ge=0)

    @property
    def blocking(self) -> bool:
        """Whether any conflict prevents generation from proceeding."""
        return any(c.severity is Severity.HARD for c in self.conflicts)

    def of_severity(self, severity: Severity) -> tuple[Conflict, ...]:
        """Conflicts at ``severity``, in report order."""
        return tuple(c for c in self.conflicts if c.severity is severity)

    def counts(self) -> Mapping[Severity, int]:
        """Conflict count per severity, including severities with none.

        Every severity is present so a caller can render the summary without
        guarding for absent keys, and so "no HARD conflicts" is stated rather
        than inferred from a missing entry.
        """
        return {severity: len(self.of_severity(severity)) for severity in Severity}


class ResolutionChoice(DomainModel):
    """The writer's answer to one conflict."""

    rule_id: Identifier
    resolution_id: Identifier


class ResolutionDelta(DomainModel):
    """What a chosen resolution actually changed.

    Recorded per choice so the audit trail shows the movement, not just the
    intent. ``from_level`` and ``to_level`` are populated only for clamps;
    an acknowledgement moves nothing and says so by leaving them unset.
    """

    rule_id: Identifier
    resolution_id: Identifier
    effect_kind: ResolutionEffectKind
    dimension: ContentDimension | None = None
    from_level: ContentLevel | None = None
    to_level: ContentLevel | None = None
    guidance: str | None = None


class ResolvedBundle(DomainModel):
    """A bundle after the writer's resolutions have been applied.

    Keeps the original alongside the result. The pair is the audit trail: what
    was asked for, what was chosen, what moved, and what the constraints became.
    Stage 2.3 re-runs detection against ``bundle`` to prove no HARD conflict
    survived, which is only meaningful because ``original`` is still here to
    compare against.
    """

    original: ConstraintBundle
    bundle: ConstraintBundle
    choices: tuple[ResolutionChoice, ...] = ()
    deltas: tuple[ResolutionDelta, ...] = ()
