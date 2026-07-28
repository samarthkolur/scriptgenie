"""What the writer asked for, and what the knowledge base says that permits.

Two kinds of model live here, and the split is deliberate.

*Selections* -- :class:`GenreSelection`, :class:`AudienceSelection`,
:class:`RatingTarget`, :class:`TerritorySet` and the :class:`ConstraintBundle`
that holds them -- are the writer's inputs. They carry identifiers, never
resolved knowledge base rows, so a bundle can be submitted, stored and replayed
without embedding a copy of the knowledge base that produced it. Replay against
a newer knowledge base is then an explicit act with a visible version change,
rather than something that silently cannot happen.

*Projections* -- :class:`ContentThresholds`, :class:`ScopeEnvelope`,
:class:`BudgetTier` -- are typed views of knowledge base rows, so the engines in
Phase 2 pass structured values around instead of raw ``dict[str, Any]``. They
are built from the knowledge base, never from user input.

Everything is frozen and forbids unknown fields. Frozen because a conflict
report must be reproducible from its bundle, and a mutable bundle makes that a
promise rather than a property. Unknown fields are rejected because the
knowledge base schemas set ``additionalProperties: false`` throughout, and a
silently dropped field is how a constraint goes missing.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.enums import (
    ActionComplexity,
    ContentDimension,
    ContentLevel,
    NarrativeEconomy,
    PeriodSetting,
    VfxComplexity,
)

#: Knowledge base identifier shape, from ``common.schema.json#/$defs/identifier``.
#: Applied to every field that names a knowledge base row so that an id which
#: could not possibly resolve is rejected at the boundary rather than at lookup.
Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=1),
]


class DomainModel(BaseModel):
    """Base for every domain model: immutable, closed, and strict about types."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
    )


class ContentThresholds(DomainModel):
    """A level on each of the six content dimensions.

    Used for both halves of a content conflict: a genre's conventional demand
    and a classification's permitted ceiling are the same shape, which is what
    reduces "does this genre fit this rating" to a comparison per axis.
    """

    violence: ContentLevel
    sexual_content: ContentLevel
    language: ContentLevel
    thematic_darkness: ContentLevel
    drug_use: ContentLevel
    horror_intensity: ContentLevel

    def level(self, dimension: ContentDimension) -> ContentLevel:
        """Return the level on ``dimension``.

        Lets callers hold a :class:`ContentDimension` and look up the value
        without string attribute access, so an unknown dimension is a typing
        error rather than an ``AttributeError`` at request time.
        """
        return ContentLevel(getattr(self, dimension.value))


class ScopeEnvelope(DomainModel):
    """The production bounds a story must fit inside.

    ``max_locations`` and ``max_named_characters`` are optional because the
    studio tier genuinely has no budget-imposed ceiling; it is bounded by genre
    convention instead. ``None`` states that, where an invented large number
    would look like knowledge the knowledge base does not have.
    """

    max_locations: int | None = Field(default=None, ge=1)
    max_named_characters: int | None = Field(default=None, ge=1)
    vfx_complexity: VfxComplexity
    period_setting: PeriodSetting
    action_complexity: ActionComplexity
    narrative_economy: NarrativeEconomy


class BudgetTier(DomainModel):
    """A budget band and the narrative scope it permits.

    ``order`` exists so tiers are compared by band rather than by label; the
    labels are prose and sort meaninglessly.
    """

    id: Identifier
    label: str = Field(min_length=3)
    order: int = Field(ge=0)
    min_usd: int = Field(ge=0)
    max_usd: int | None = Field(default=None, ge=0)
    guild_context: str
    scope: ScopeEnvelope

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Self:
        if self.max_usd is not None and self.max_usd < self.min_usd:
            raise ValueError(
                f"budget tier '{self.id}' has max_usd {self.max_usd} below min_usd {self.min_usd}"
            )
        return self


class GenreSelection(DomainModel):
    """A primary genre and an optional secondary modifier.

    The secondary is a modifier rather than an equal partner: hybrid rules read
    ``secondary_genre`` separately, and several compound the primary's demands
    rather than averaging them.
    """

    primary: Identifier
    secondary: Identifier | None = None

    @model_validator(mode="after")
    def _secondary_differs(self) -> Self:
        if self.secondary is not None and self.secondary == self.primary:
            raise ValueError(f"secondary genre must differ from primary; both are '{self.primary}'")
        return self


class AudienceSelection(DomainModel):
    """The age band the writer intends to reach.

    Compared against a classification's ``min_audience_age``. A bundle whose
    audience cannot be admitted to its own rating is an arithmetic
    contradiction between two of the writer's own inputs, which is why the
    rule that catches it is HARD.
    """

    min_age: int = Field(ge=0, le=120)
    max_age: int = Field(ge=0, le=120)

    @model_validator(mode="after")
    def _band_is_ordered(self) -> Self:
        if self.max_age < self.min_age:
            raise ValueError(f"audience max_age {self.max_age} is below min_age {self.min_age}")
        return self


class RatingTarget(DomainModel):
    """The classification being aimed at, qualified by its system.

    A classification id is only meaningful inside its system -- ``u_a`` means
    nothing without CBFC -- so the two travel together and are never split.
    """

    system: Identifier
    classification: Identifier

    @property
    def qualified(self) -> str:
        """``system.classification``, the form used in equivalence references."""
        return f"{self.system}.{self.classification}"


class TerritorySet(DomainModel):
    """The territories a production intends to release in.

    Order is not significant, but it is preserved and duplicates are rejected,
    so that two bundles naming the same territories differently still compare
    and hash alike after normalisation by the caller.
    """

    ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicates(self) -> Self:
        seen = sorted({t for t in self.ids if self.ids.count(t) > 1})
        if seen:
            raise ValueError(f"duplicate territories: {seen}")
        return self

    @property
    def count(self) -> int:
        """Number of territories, read by the multi-territory conflict rules."""
        return len(self.ids)


class ConstraintBundle(DomainModel):
    """Everything the writer specified, before any conflict has been detected.

    This is the unit of reproducibility. A conflict report is a pure function
    of a bundle and a knowledge base version, so the pair is enough to explain
    any verdict this system has ever issued.
    """

    genre: GenreSelection
    audience: AudienceSelection
    rating: RatingTarget
    budget_tier_id: Identifier
    territories: TerritorySet


class ThresholdSource(DomainModel):
    """Why one content ceiling is what it is.

    Provenance is not decoration. The system's claim is that a variant was
    verified against a stated envelope, and a ceiling nobody can trace is a
    number the writer has to take on faith. Recording which board or statute
    produced each level is what makes the envelope auditable.
    """

    dimension: ContentDimension
    level: ContentLevel
    authority: str = Field(min_length=1)
    detail: str | None = None


class PromptDirective(DomainModel):
    """One machine-readable constraint, ready to be rendered into a prompt.

    Deliberately a key and a value rather than a sentence. Free prose in a
    prompt fragment would be a second, untested statement of the constraints
    that could drift from the envelope it claims to describe.
    """

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class GenerationEnvelope(DomainModel):
    """The complete, resolved bounds one variant must be generated inside.

    Layer 2's output: budget scope bounds, content ceilings reduced to the
    strictest applicable across every selected territory, the provenance of
    each ceiling, and the guidance the writer's resolutions attached.

    It also names the budget tier and genre it was built from. Those are not
    bounds, but Layer 3 scores archetypes against them, and an envelope that
    could not say what produced it would force every later stage to carry the
    bundle alongside it and keep the two in step by hand.
    """

    budget_tier_id: Identifier
    genre: GenreSelection
    scope: ScopeEnvelope
    thresholds: ContentThresholds
    provenance: tuple[ThresholdSource, ...] = ()
    guidance: tuple[str, ...] = ()
    directives: tuple[PromptDirective, ...] = ()

    def prompt_fragment(self) -> str:
        """The directives as deterministic ``key: value`` lines.

        Generated from the same directives the machine fields carry, so the
        text a model sees cannot disagree with the envelope it was built from.
        """
        return "\n".join(f"{d.key}: {d.value}" for d in self.directives)
