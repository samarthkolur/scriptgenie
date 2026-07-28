"""Tests for Layer 2, the scope parameteriser.

The claim under test is that the envelope is the *strictest* applicable value
on every axis, and that each ceiling can be traced to the body that imposed it.
A merge that silently took the target rating's numbers would pass a naive test
and ship variants that cannot be released in half the selected territories.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.domain import (
    AudienceSelection,
    ConstraintBundle,
    ContentDimension,
    ContentLevel,
    GenreSelection,
    RatingTarget,
    ResolutionChoice,
    ResolvedBundle,
    Severity,
    TerritorySet,
)
from app.engines.conflict_detector import detect
from app.engines.errors import UnknownReferenceError
from app.engines.resolution import apply_resolutions
from app.engines.scope_parameterizer import parameterize
from app.kb.loader import KnowledgeBase, load_knowledge_base


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_knowledge_base()


def _bundle(**overrides: Any) -> ConstraintBundle:
    values: dict[str, Any] = {
        "genre": GenreSelection(primary="horror", secondary="comedy"),
        "audience": AudienceSelection(min_age=15, max_age=40),
        "rating": RatingTarget(system="mpa", classification="pg_13"),
        "budget_tier_id": "micro",
        "territories": TerritorySet(ids=("us", "india")),
    }
    values.update(overrides)
    return ConstraintBundle(**values)


def _resolved(bundle: ConstraintBundle) -> ResolvedBundle:
    """A resolved bundle with no choices, for testing the merge in isolation."""
    return ResolvedBundle(original=bundle, bundle=bundle)


def _settled(bundle: ConstraintBundle, kb: KnowledgeBase) -> ResolvedBundle:
    """A genuinely resolved bundle, clamping every HARD conflict."""
    report = detect(bundle, kb)
    choices = tuple(
        ResolutionChoice(rule_id=c.rule_id, resolution_id=c.resolutions[0].id)
        for c in report.conflicts
        if c.severity is Severity.HARD
    )
    return apply_resolutions(report, choices, kb)


def _levels(envelope: Any) -> dict[str, int]:
    return {d.value: int(envelope.thresholds.level(d)) for d in ContentDimension}


# ------------------------------------------------------------------ acceptance


def test_us_and_india_at_pg13_yields_a_cbfc_violence_ceiling(kb: KnowledgeBase) -> None:
    """The acceptance criterion, and the reason the merge is not a one-liner.

    MPA PG-13 permits violence at 2. CBFC U/A, the classification India's board
    applies to the same film, permits 1. The envelope must be 1: it is not an
    extra restriction layered onto PG-13, it is a different board reading the
    same film.
    """
    envelope = parameterize(_resolved(_bundle()), kb)
    assert _levels(envelope)["violence"] == 1

    us_only = parameterize(_resolved(_bundle(territories=TerritorySet(ids=("us",)))), kb)
    assert _levels(us_only)["violence"] == 2


def test_micro_tier_always_yields_its_documented_bounds(kb: KnowledgeBase) -> None:
    """The second acceptance criterion, across every rating and territory mix."""
    for rating in (
        RatingTarget(system="mpa", classification="g"),
        RatingTarget(system="mpa", classification="nc_17"),
        RatingTarget(system="cbfc", classification="a"),
    ):
        for territories in (("us",), ("us", "india", "germany", "uk", "australia")):
            envelope = parameterize(
                _resolved(
                    _bundle(
                        budget_tier_id="micro",
                        rating=rating,
                        territories=TerritorySet(ids=territories),
                    )
                ),
                kb,
            )
            assert envelope.scope.max_locations == 3
            assert envelope.scope.max_named_characters == 5
            assert envelope.scope.vfx_complexity.value == "none"
            assert envelope.scope.period_setting.value == "contemporary_only"


def test_scope_bounds_come_from_the_budget_tier(kb: KnowledgeBase) -> None:
    envelope = parameterize(_resolved(_bundle(budget_tier_id="mid_indie")), kb)
    assert envelope.scope.max_locations == 15
    assert envelope.scope.max_named_characters == 20
    assert envelope.scope.narrative_economy.value == "standard"


def test_studio_tier_reports_unbounded_rather_than_a_number(kb: KnowledgeBase) -> None:
    envelope = parameterize(_resolved(_bundle(budget_tier_id="studio")), kb)
    assert envelope.scope.max_locations is None
    fragment = dict(line.split(": ", 1) for line in envelope.prompt_fragment().splitlines())
    assert fragment["max_locations"] == "unbounded"


# ------------------------------------------------------------------ strictness


def test_the_strictest_territory_wins_on_every_dimension(kb: KnowledgeBase) -> None:
    wide = parameterize(
        _resolved(
            _bundle(
                rating=RatingTarget(system="mpa", classification="nc_17"),
                territories=TerritorySet(ids=("us", "india", "germany", "uk", "australia")),
            )
        ),
        kb,
    )
    narrow = parameterize(
        _resolved(_bundle(rating=RatingTarget(system="mpa", classification="nc_17"))), kb
    )
    for dimension in ContentDimension:
        assert _levels(wide)[dimension.value] <= _levels(narrow)[dimension.value]


def test_territory_restriction_tightens_below_its_own_board(kb: KnowledgeBase) -> None:
    """India's statutory violence limit is tighter than CBFC's own U/A threshold."""
    envelope = parameterize(
        _resolved(
            _bundle(
                rating=RatingTarget(system="cbfc", classification="a"),
                territories=TerritorySet(ids=("india",)),
            )
        ),
        kb,
    )
    # CBFC A permits drug_use 2; the glamorisation rule caps it at 1 everywhere.
    assert _levels(envelope)["drug_use"] == 1
    source = next(p for p in envelope.provenance if p.dimension is ContentDimension.DRUG_USE)
    assert source.authority == "Central Board of Film Certification"
    assert source.detail


def test_adding_a_territory_never_loosens_a_ceiling(kb: KnowledgeBase) -> None:
    base = parameterize(_resolved(_bundle(territories=TerritorySet(ids=("us",)))), kb)
    for extra in ("india", "uk", "germany", "australia"):
        wider = parameterize(_resolved(_bundle(territories=TerritorySet(ids=("us", extra)))), kb)
        for dimension in ContentDimension:
            assert _levels(wider)[dimension.value] <= _levels(base)[dimension.value]


def test_unmappable_classification_falls_back_to_the_target(kb: KnowledgeBase) -> None:
    """CBFC has no counterpart to MPA PG, and none is invented.

    The equivalence table relates PG to BBFC, FSK and ACB but not to CBFC. The
    Indian board therefore contributes only its statutory restrictions, not a
    fabricated threshold.
    """
    envelope = parameterize(
        _resolved(
            _bundle(
                rating=RatingTarget(system="mpa", classification="pg"),
                territories=TerritorySet(ids=("india",)),
            )
        ),
        kb,
    )
    # MPA PG permits thematic_darkness 2 and CBFC contributes no equivalent.
    darkness = next(
        p for p in envelope.provenance if p.dimension is ContentDimension.THEMATIC_DARKNESS
    )
    assert "MPA" in darkness.authority


# ------------------------------------------------------------------ provenance


def test_every_dimension_is_traceable(kb: KnowledgeBase) -> None:
    envelope = parameterize(_resolved(_bundle()), kb)
    assert {p.dimension for p in envelope.provenance} == set(ContentDimension)
    for source in envelope.provenance:
        assert source.authority
        assert source.level == envelope.thresholds.level(source.dimension)


def test_single_territory_provenance_names_the_target_board(kb: KnowledgeBase) -> None:
    envelope = parameterize(_resolved(_bundle(territories=TerritorySet(ids=("us",)))), kb)
    for source in envelope.provenance:
        assert "MPA" in source.authority
        assert source.detail is None


# ------------------------------------------------------------------ guidance


def test_resolution_guidance_reaches_the_envelope(kb: KnowledgeBase) -> None:
    """Guidance is part of the brief, which is why this takes a ResolvedBundle."""
    envelope = parameterize(_settled(_bundle(), kb), kb)
    assert envelope.guidance
    assert any("strictest selected territory" in text for text in envelope.guidance)
    assert any(d.key == "guidance" for d in envelope.directives)


def test_no_resolutions_means_no_guidance(kb: KnowledgeBase) -> None:
    envelope = parameterize(_resolved(_bundle()), kb)
    assert envelope.guidance == ()
    assert not any(d.key == "guidance" for d in envelope.directives)


# ------------------------------------------------------------------ prompt


def test_prompt_fragment_is_structured_and_matches_the_machine_fields(
    kb: KnowledgeBase,
) -> None:
    """No free-form prose: every line is a key and a value from the envelope."""
    envelope = parameterize(_resolved(_bundle()), kb)
    lines = envelope.prompt_fragment().splitlines()
    assert all(": " in line for line in lines)

    fragment = dict(line.split(": ", 1) for line in lines)
    assert fragment["max_locations"] == str(envelope.scope.max_locations)
    assert fragment["vfx_complexity"] == envelope.scope.vfx_complexity.value
    for dimension in ContentDimension:
        assert fragment[f"max_{dimension.value}"] == str(int(envelope.thresholds.level(dimension)))


def test_prompt_fragment_is_stable_across_runs(kb: KnowledgeBase) -> None:
    resolved = _settled(_bundle(), kb)
    first = parameterize(resolved, kb)
    second = parameterize(resolved, kb)
    assert first.prompt_fragment() == second.prompt_fragment()
    assert first.model_dump_json() == second.model_dump_json()


def test_territory_order_does_not_change_the_envelope(kb: KnowledgeBase) -> None:
    forward = parameterize(
        _resolved(_bundle(territories=TerritorySet(ids=("us", "india", "uk")))), kb
    )
    reverse = parameterize(
        _resolved(_bundle(territories=TerritorySet(ids=("uk", "india", "us")))), kb
    )
    assert _levels(forward) == _levels(reverse)


# ------------------------------------------------------------------ references


def test_unknown_budget_tier_is_rejected(kb: KnowledgeBase) -> None:
    bundle = _bundle(budget_tier_id="colossal")
    with pytest.raises(UnknownReferenceError) as exc:
        parameterize(_resolved(bundle), kb)
    assert exc.value.kind == "budget tier"


def test_unknown_classification_is_rejected(kb: KnowledgeBase) -> None:
    bundle = _bundle(rating=RatingTarget(system="mpa", classification="pg_99"))
    with pytest.raises(UnknownReferenceError) as exc:
        parameterize(_resolved(bundle), kb)
    assert exc.value.kind == "classification"


def test_unknown_territory_is_rejected(kb: KnowledgeBase) -> None:
    bundle = _bundle(territories=TerritorySet(ids=("atlantis",)))
    with pytest.raises(UnknownReferenceError) as exc:
        parameterize(_resolved(bundle), kb)
    assert exc.value.kind == "territory"


def test_territory_without_extra_restrictions_contributes_only_its_board(
    kb: KnowledgeBase,
) -> None:
    """A territory carrying no ``additional_restrictions`` must still merge."""
    territory = {
        "id": "plainland",
        "label": "Plainland",
        "regulator": "Plain Board",
        "rating_system": "mpa",
        "citations": ["Plain statute"],
    }
    scoped = dataclasses.replace(kb, territories=(*kb.territories, territory))
    envelope = parameterize(
        _resolved(_bundle(territories=TerritorySet(ids=("plainland",)))), scoped
    )
    assert _levels(envelope)["violence"] == 2


def test_a_stricter_board_on_an_already_strict_dimension_does_not_double_count(
    kb: KnowledgeBase,
) -> None:
    """Ceilings are a minimum, so re-applying the same bound changes nothing."""
    once = parameterize(_resolved(_bundle(territories=TerritorySet(ids=("india",)))), kb)
    twice = parameterize(_resolved(_bundle(territories=TerritorySet(ids=("india", "us")))), kb)
    assert _levels(once)["violence"] == _levels(twice)["violence"] == 1


def test_levels_are_content_levels_not_bare_integers(kb: KnowledgeBase) -> None:
    envelope = parameterize(_resolved(_bundle()), kb)
    assert isinstance(envelope.thresholds.level(ContentDimension.VIOLENCE), ContentLevel)
