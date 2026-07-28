"""Tests for the constraint, conflict and variant domain models.

Stage 2.1's acceptance criterion is that an invalid value is rejected at model
construction *with a field-level error*, so most of these assert on the
``loc`` of the reported error rather than only that something raised. An error
that says "the bundle is invalid" without naming the field would satisfy a
looser test and would be useless in an API response.

The rest cover the invariants the models are responsible for holding: a HARD
conflict that justifies itself, a conflict that offers a real choice, a variant
whose beats are in order, and derived verdicts that cannot disagree with the
evidence they are derived from.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain import (
    ArchetypeAssignment,
    AudienceSelection,
    BudgetTier,
    Conflict,
    ConflictReport,
    ConstraintBundle,
    ConstraintSatisfactionReport,
    ContentDimension,
    ContentLevel,
    ContentThresholds,
    DimensionCheck,
    GenreSelection,
    PlotBeat,
    PlotVariant,
    RatingTarget,
    ResolutionEffect,
    ResolutionEffectKind,
    ResolutionOption,
    ScopeCheck,
    ScopeEnvelope,
    Severity,
    TerritorySet,
    VerificationResult,
)


def _thresholds(**overrides: int) -> ContentThresholds:
    values: dict[str, Any] = {
        "violence": 2,
        "sexual_content": 1,
        "language": 2,
        "thematic_darkness": 2,
        "drug_use": 1,
        "horror_intensity": 1,
    }
    values.update(overrides)
    return ContentThresholds(**values)


def _envelope(**overrides: Any) -> ScopeEnvelope:
    values: dict[str, Any] = {
        "max_locations": 5,
        "max_named_characters": 6,
        "vfx_complexity": "practical_only",
        "period_setting": "contemporary_only",
        "action_complexity": "dialogue_driven",
        "narrative_economy": "high",
    }
    values.update(overrides)
    return ScopeEnvelope(**values)


def _bundle(**overrides: Any) -> ConstraintBundle:
    values: dict[str, Any] = {
        "genre": GenreSelection(primary="horror", secondary="thriller"),
        "audience": AudienceSelection(min_age=15, max_age=35),
        "rating": RatingTarget(system="mpa", classification="pg_13"),
        "budget_tier_id": "micro",
        "territories": TerritorySet(ids=("us", "in")),
    }
    values.update(overrides)
    return ConstraintBundle(**values)


def _options() -> tuple[ResolutionOption, ...]:
    return (
        ResolutionOption(id="soften", label="Soften it", description="Imply rather than show."),
        ResolutionOption(id="reclassify", label="Move up", description="Accept a higher rating."),
    )


def _locs(exc: pytest.ExceptionInfo[ValidationError]) -> list[tuple[int | str, ...]]:
    return [error["loc"] for error in exc.value.errors()]


# --------------------------------------------------------------- enum rejection


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("vfx_complexity", "photoreal"),
        ("period_setting", "medieval"),
        ("action_complexity", "explosive"),
        ("narrative_economy", "loose"),
    ],
)
def test_invalid_scope_enum_is_rejected_at_its_own_field(field: str, bad_value: str) -> None:
    """The acceptance criterion: the error names the field, not just the model."""
    with pytest.raises(ValidationError) as exc:
        _envelope(**{field: bad_value})
    assert (field,) in _locs(exc)


def test_invalid_content_level_is_rejected_at_its_own_field() -> None:
    with pytest.raises(ValidationError) as exc:
        _thresholds(violence=9)
    assert ("violence",) in _locs(exc)


def test_invalid_severity_is_rejected_at_its_own_field() -> None:
    with pytest.raises(ValidationError) as exc:
        Conflict(
            rule_id="r",
            severity="CRITICAL",
            title="t",
            explanation="e",
            resolutions=_options(),
        )
    assert ("severity",) in _locs(exc)


def test_nested_enum_error_reports_the_full_path() -> None:
    """A bad value deep in a payload must still be locatable by a client.

    Built from a raw dict rather than a nested model, because that is how a
    request arrives: the whole tree is validated in one pass, and the error has
    to say *which* scope field was wrong.
    """
    with pytest.raises(ValidationError) as exc:
        BudgetTier.model_validate(
            {
                "id": "micro",
                "label": "Micro budget",
                "order": 0,
                "min_usd": 0,
                "max_usd": 250_000,
                "guild_context": "SAG-AFTRA Micro Budget",
                "scope": {
                    "max_locations": 5,
                    "max_named_characters": 6,
                    "vfx_complexity": "photoreal",
                    "period_setting": "contemporary_only",
                    "action_complexity": "dialogue_driven",
                    "narrative_economy": "high",
                },
            }
        )
    assert ("scope", "vfx_complexity") in _locs(exc)


def test_deeply_nested_bundle_error_reports_the_full_path() -> None:
    """The same guarantee through three levels, which is what an API returns."""
    with pytest.raises(ValidationError) as exc:
        ConstraintBundle.model_validate(
            {
                "genre": {"primary": "horror", "secondary": "thriller"},
                "audience": {"min_age": 15, "max_age": 35},
                "rating": {"system": "MPA", "classification": "pg_13"},
                "budget_tier_id": "micro",
                "territories": {"ids": ["us", "in"]},
            }
        )
    assert ("rating", "system") in _locs(exc)


@pytest.mark.parametrize("bad_id", ["MPA", "1st", "has-dash", "has space", ""])
def test_identifiers_that_cannot_name_a_knowledge_base_row_are_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError) as exc:
        RatingTarget(system=bad_id, classification="pg_13")
    assert ("system",) in _locs(exc)


def test_unknown_fields_are_rejected() -> None:
    """``extra="forbid"`` mirrors the knowledge base schemas.

    A silently dropped field is how a constraint goes missing.
    """
    with pytest.raises(ValidationError) as exc:
        RatingTarget(system="mpa", classification="pg_13", teritory="us")  # type: ignore[call-arg]
    assert ("teritory",) in _locs(exc)


def test_models_are_frozen() -> None:
    bundle = _bundle()
    with pytest.raises(ValidationError):
        bundle.budget_tier_id = "studio"  # type: ignore[misc]


# --------------------------------------------------------------- constraints


def test_content_thresholds_lookup_by_dimension() -> None:
    thresholds = _thresholds(violence=3)
    assert thresholds.level(ContentDimension.VIOLENCE) is ContentLevel.STRONG
    assert thresholds.level(ContentDimension.DRUG_USE) is ContentLevel.MILD


def test_unbounded_scope_is_expressible() -> None:
    """The studio tier has no budget-imposed ceiling, and says so with ``None``."""
    envelope = _envelope(max_locations=None, max_named_characters=None)
    assert envelope.max_locations is None


def test_secondary_genre_must_differ_from_primary() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        GenreSelection(primary="horror", secondary="horror")


def test_audience_band_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="below min_age"):
        AudienceSelection(min_age=30, max_age=12)


def test_single_age_audience_is_valid() -> None:
    assert AudienceSelection(min_age=18, max_age=18).max_age == 18


def test_budget_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="below min_usd"):
        BudgetTier(
            id="micro",
            label="Micro budget",
            order=0,
            min_usd=250_000,
            max_usd=1_000,
            guild_context="SAG-AFTRA Micro Budget",
            scope=_envelope(),
        )


def test_unbounded_budget_tier_is_valid() -> None:
    tier = BudgetTier(
        id="studio",
        label="Studio",
        order=3,
        min_usd=50_000_000,
        guild_context="SAG-AFTRA Theatrical",
        scope=_envelope(max_locations=None, max_named_characters=None),
    )
    assert tier.max_usd is None


def test_rating_target_qualifies_its_classification() -> None:
    assert RatingTarget(system="cbfc", classification="u_a").qualified == "cbfc.u_a"


def test_territories_reject_duplicates_and_count() -> None:
    with pytest.raises(ValidationError, match="duplicate territories"):
        TerritorySet(ids=("us", "in", "us"))
    assert TerritorySet(ids=("us", "in", "de")).count == 3


def test_territory_set_cannot_be_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        TerritorySet(ids=())
    assert ("ids",) in _locs(exc)


# --------------------------------------------------------------- conflicts


def test_hard_conflict_must_carry_its_rationale() -> None:
    """HARD blocks the writer, so the justification is not optional."""
    with pytest.raises(ValidationError, match="hard_rationale"):
        Conflict(
            rule_id="cbfc_stricter",
            severity=Severity.HARD,
            title="Territory stricter than rating",
            explanation="CBFC restricts below the target.",
            resolutions=_options(),
        )


def test_hard_conflict_with_rationale_is_valid() -> None:
    conflict = Conflict(
        rule_id="cbfc_stricter",
        severity=Severity.HARD,
        title="Territory stricter than rating",
        explanation="CBFC restricts below the target.",
        hard_rationale="No narrative satisfies both ceilings at once.",
        resolutions=_options(),
    )
    assert conflict.severity is Severity.HARD


@pytest.mark.parametrize("severity", [Severity.SOFT, Severity.ADVISORY])
def test_non_hard_conflicts_need_no_rationale(severity: Severity) -> None:
    conflict = Conflict(
        rule_id="genre_rating_violence",
        severity=severity,
        title="Genre exceeds rating",
        explanation="Horror conventionally uses more violence than PG-13 permits.",
        resolutions=_options(),
    )
    assert conflict.hard_rationale is None


def test_a_conflict_must_offer_a_real_choice() -> None:
    """One option is an instruction, not a choice; the schema requires two."""
    with pytest.raises(ValidationError) as exc:
        Conflict(
            rule_id="r",
            severity=Severity.SOFT,
            title="t",
            explanation="e",
            resolutions=(_options()[0],),
        )
    assert ("resolutions",) in _locs(exc)


def test_clamp_effect_must_name_its_dimension() -> None:
    with pytest.raises(ValidationError, match="requires the dimension"):
        ResolutionEffect(kind=ResolutionEffectKind.CLAMP_DIMENSION_TO_PERMITTED)


def test_acknowledgement_effect_needs_no_dimension() -> None:
    effect = ResolutionEffect(kind=ResolutionEffectKind.ACKNOWLEDGE_RELAXATION)
    assert effect.dimension is None


def _conflict(severity: Severity, rule_id: str) -> Conflict:
    return Conflict(
        rule_id=rule_id,
        severity=severity,
        title="t",
        explanation="e",
        hard_rationale="r" if severity is Severity.HARD else None,
        resolutions=_options(),
    )


def test_report_blocks_only_on_hard_conflicts() -> None:
    soft_only = ConflictReport(
        bundle=_bundle(),
        kb_version="0.1.0",
        conflicts=(_conflict(Severity.SOFT, "a"), _conflict(Severity.ADVISORY, "b")),
    )
    assert soft_only.blocking is False

    with_hard = ConflictReport(
        bundle=_bundle(),
        kb_version="0.1.0",
        conflicts=(_conflict(Severity.SOFT, "a"), _conflict(Severity.HARD, "c")),
    )
    assert with_hard.blocking is True


def test_empty_report_is_not_blocking() -> None:
    report = ConflictReport(bundle=_bundle(), kb_version="0.1.0")
    assert report.blocking is False
    assert report.conflicts == ()


def test_report_counts_every_severity_even_when_zero() -> None:
    """ "No HARD conflicts" must be stated, not inferred from a missing key."""
    report = ConflictReport(
        bundle=_bundle(),
        kb_version="0.1.0",
        conflicts=(_conflict(Severity.SOFT, "a"),),
    )
    counts = report.counts()
    assert set(counts) == set(Severity)
    assert counts[Severity.SOFT] == 1
    assert counts[Severity.HARD] == 0


def test_report_filters_by_severity_in_order() -> None:
    report = ConflictReport(
        bundle=_bundle(),
        kb_version="0.1.0",
        conflicts=(
            _conflict(Severity.SOFT, "a"),
            _conflict(Severity.HARD, "b"),
            _conflict(Severity.SOFT, "c"),
        ),
    )
    assert [c.rule_id for c in report.of_severity(Severity.SOFT)] == ["a", "c"]


# --------------------------------------------------------------- variants


def _variant(**overrides: Any) -> PlotVariant:
    values: dict[str, Any] = {
        "id": "variant_one",
        "title": "The Quiet House",
        "logline": "A caretaker discovers the house is keeping someone.",
        "archetype": ArchetypeAssignment(
            variant_index=0,
            archetype_id="siege",
            score=3,
            rationale="Single location suits the micro tier.",
        ),
        "beats": (
            PlotBeat(index=0, function="setup", summary="She takes the job."),
            PlotBeat(index=1, function="disruption", summary="The cellar is warm."),
        ),
    }
    values.update(overrides)
    return PlotVariant(**values)


def test_variant_beats_must_be_sequential() -> None:
    with pytest.raises(ValidationError, match="expected"):
        _variant(
            beats=(
                PlotBeat(index=0, function="setup", summary="a"),
                PlotBeat(index=2, function="disruption", summary="b"),
            )
        )


def test_variant_beats_must_be_in_order() -> None:
    with pytest.raises(ValidationError, match="expected"):
        _variant(
            beats=(
                PlotBeat(index=1, function="disruption", summary="b"),
                PlotBeat(index=0, function="setup", summary="a"),
            )
        )


def test_valid_variant_is_accepted() -> None:
    assert len(_variant().beats) == 2


def test_dimension_check_compares_against_permission() -> None:
    assert DimensionCheck(
        dimension=ContentDimension.VIOLENCE,
        permitted=ContentLevel.MODERATE,
        observed=ContentLevel.MODERATE,
    ).satisfied
    assert not DimensionCheck(
        dimension=ContentDimension.VIOLENCE,
        permitted=ContentLevel.MODERATE,
        observed=ContentLevel.STRONG,
    ).satisfied


def test_scope_check_with_no_limit_is_satisfied() -> None:
    """An unbounded tier imposes no ceiling, and the axis is still reported."""
    assert ScopeCheck(parameter="locations", limit=None, observed=40).satisfied
    assert ScopeCheck(parameter="locations", limit=5, observed=5).satisfied
    assert not ScopeCheck(parameter="locations", limit=5, observed=6).satisfied


def _satisfaction(*, failing: bool) -> ConstraintSatisfactionReport:
    return ConstraintSatisfactionReport(
        variant_id="variant_one",
        thresholds=_thresholds(),
        envelope=_envelope(),
        dimension_checks=(
            DimensionCheck(
                dimension=ContentDimension.VIOLENCE,
                permitted=ContentLevel.MODERATE,
                observed=ContentLevel.STRONG if failing else ContentLevel.MILD,
            ),
        ),
        scope_checks=(ScopeCheck(parameter="locations", limit=5, observed=9 if failing else 3),),
    )


def test_satisfaction_report_names_every_failed_axis() -> None:
    report = _satisfaction(failing=True)
    assert report.satisfied is False
    assert report.violations() == ("violence", "locations")


def test_satisfaction_report_passes_when_every_axis_fits() -> None:
    report = _satisfaction(failing=False)
    assert report.satisfied is True
    assert report.violations() == ()


def test_verification_cannot_claim_success_over_a_failed_report() -> None:
    """``verified`` is derived, so it cannot disagree with its evidence."""
    result = VerificationResult(
        kb_version="0.1.0",
        reports=(_satisfaction(failing=False), _satisfaction(failing=True)),
    )
    assert result.verified is False
    assert result.failed_variants() == ("variant_one",)


def test_verification_of_all_passing_reports_is_verified() -> None:
    result = VerificationResult(kb_version="0.1.0", reports=(_satisfaction(failing=False),))
    assert result.verified is True
    assert result.failed_variants() == ()


def test_empty_verification_is_vacuously_verified() -> None:
    assert VerificationResult(kb_version="0.1.0").verified is True
