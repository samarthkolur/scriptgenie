"""Tests for Stage 2.3, applying a writer's conflict resolutions.

The load-bearing test is that a HARD conflict cannot be resolved by asserting
it has been. Detection is re-run against the resulting bundle, and anything
still blocking raises rather than being reported as resolved -- which is what
makes "verified for scope" mean something downstream.

The rest establish that the audit trail is complete enough to reconstruct what
happened: the original bundle, the choices made, and the movement each choice
produced.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain import (
    AudienceSelection,
    ConstraintBundle,
    GenreSelection,
    RatingTarget,
    ResolutionChoice,
    ResolutionEffectKind,
    Severity,
    TerritorySet,
)
from app.engines.conflict_detector import detect
from app.engines.errors import UnknownResolutionError, UnresolvedHardConflictError
from app.engines.resolution import apply_resolutions
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


def _choices_clearing_every_hard(
    report: Any, option_index: int = 0
) -> tuple[ResolutionChoice, ...]:
    """Pick a settling option for each HARD conflict.

    Index 0 is the clamp on every territory rule, which is the co-production
    default the knowledge base documents.
    """
    return tuple(
        ResolutionChoice(
            rule_id=conflict.rule_id,
            resolution_id=conflict.resolutions[option_index].id,
        )
        for conflict in report.conflicts
        if conflict.severity is Severity.HARD
    )


# ------------------------------------------------------------------ blocking


def test_unresolved_hard_conflict_raises(kb: KnowledgeBase) -> None:
    """The acceptance criterion. Making no choice cannot clear a blocker."""
    report = detect(_bundle(), kb)
    assert report.blocking

    with pytest.raises(UnresolvedHardConflictError) as exc:
        apply_resolutions(report, (), kb)

    assert set(exc.value.rule_ids) == {
        "territory_violence_stricter_than_rating",
        "territory_drug_use_stricter_than_rating",
    }


def test_partially_resolved_hard_conflicts_still_raise(kb: KnowledgeBase) -> None:
    """Settling one blocker does not release the other."""
    report = detect(_bundle(), kb)
    one = _choices_clearing_every_hard(report)[:1]

    with pytest.raises(UnresolvedHardConflictError) as exc:
        apply_resolutions(report, one, kb)

    assert len(exc.value.rule_ids) == 1


def test_requires_bundle_change_does_not_clear_a_hard_conflict(kb: KnowledgeBase) -> None:
    """Intent to revise is not a revision.

    ``drop_strict_territory`` tells the writer to remove the territory. Until
    they resubmit without it, the conflict stands.
    """
    report = detect(_bundle(), kb)
    choices = tuple(
        ResolutionChoice(rule_id=c.rule_id, resolution_id=c.resolutions[1].id)
        for c in report.conflicts
        if c.severity is Severity.HARD
    )
    for choice in choices:
        conflict = next(c for c in report.conflicts if c.rule_id == choice.rule_id)
        option = next(o for o in conflict.resolutions if o.id == choice.resolution_id)
        assert option.effect is not None
        assert option.effect.kind is ResolutionEffectKind.REQUIRES_BUNDLE_CHANGE

    with pytest.raises(UnresolvedHardConflictError):
        apply_resolutions(report, choices, kb)


def test_clamping_every_hard_conflict_succeeds(kb: KnowledgeBase) -> None:
    report = detect(_bundle(), kb)
    resolved = apply_resolutions(report, _choices_clearing_every_hard(report), kb)
    assert len(resolved.deltas) == 2


def test_acknowledging_a_territory_cut_settles_the_conflict(kb: KnowledgeBase) -> None:
    """``acknowledge_separate_cut`` commits to a second cut; that is a decision.

    It is the one acknowledgement that clears a HARD conflict, and it does so
    because it reconciles the two regulators the rationale says cannot be
    reconciled within a single cut.
    """
    report = detect(_bundle(), kb)
    choices = _choices_clearing_every_hard(report, option_index=2)
    resolved = apply_resolutions(report, choices, kb)
    assert all(
        delta.effect_kind is ResolutionEffectKind.ACKNOWLEDGE_RELAXATION
        for delta in resolved.deltas
    )


def test_a_bundle_with_no_hard_conflicts_needs_no_choices(kb: KnowledgeBase) -> None:
    bundle = _bundle(
        genre=GenreSelection(primary="drama"),
        rating=RatingTarget(system="mpa", classification="r"),
        territories=TerritorySet(ids=("us",)),
        budget_tier_id="studio",
    )
    report = detect(bundle, kb)
    assert not report.blocking
    resolved = apply_resolutions(report, (), kb)
    assert resolved.deltas == ()


def test_a_hard_conflict_offering_only_bundle_change_can_never_be_cleared(
    kb: KnowledgeBase,
) -> None:
    """Some tensions genuinely require resubmission, and say so.

    Action at micro budget offers only ``requires_bundle_change`` options,
    because no in-place edit makes staged action affordable.
    """
    bundle = _bundle(
        genre=GenreSelection(primary="action"),
        budget_tier_id="micro",
        territories=TerritorySet(ids=("us",)),
        rating=RatingTarget(system="mpa", classification="r"),
    )
    report = detect(bundle, kb)
    blocker = next(c for c in report.conflicts if c.rule_id == "action_micro_budget_infeasible")
    choices = tuple(
        ResolutionChoice(rule_id=blocker.rule_id, resolution_id=option.id)
        for option in blocker.resolutions[:1]
    )
    with pytest.raises(UnresolvedHardConflictError):
        apply_resolutions(report, choices, kb)


def test_revising_the_bundle_actually_clears_the_conflict(kb: KnowledgeBase) -> None:
    """The path ``requires_bundle_change`` points at, followed to its end."""
    blocked = detect(_bundle(), kb)
    assert blocked.blocking

    # Drop India, which is what drop_strict_territory advises.
    revised = detect(_bundle(territories=TerritorySet(ids=("us",))), kb)
    assert not revised.blocking
    assert apply_resolutions(revised, (), kb).bundle.territories.ids == ("us",)


# ------------------------------------------------------------------ audit trail


def test_resolved_bundle_retains_the_full_audit_trail(kb: KnowledgeBase) -> None:
    """The second acceptance criterion: original, choices and deltas together."""
    bundle = _bundle()
    report = detect(bundle, kb)
    choices = _choices_clearing_every_hard(report)
    resolved = apply_resolutions(report, choices, kb)

    assert resolved.original == bundle
    assert resolved.choices == choices
    assert {d.rule_id for d in resolved.deltas} == {c.rule_id for c in choices}
    assert {d.resolution_id for d in resolved.deltas} == {c.resolution_id for c in choices}


def test_clamp_delta_records_the_movement(kb: KnowledgeBase) -> None:
    report = detect(_bundle(), kb)
    choices = _choices_clearing_every_hard(report)
    resolved = apply_resolutions(report, choices, kb)

    violence = next(
        d for d in resolved.deltas if d.rule_id == "territory_violence_stricter_than_rating"
    )
    assert violence.effect_kind is ResolutionEffectKind.CLAMP_DIMENSION_TO_PERMITTED
    assert violence.dimension is not None and violence.dimension.value == "violence"
    # PG-13 permitted 2; India's ceiling is 1.
    assert violence.from_level == 2
    assert violence.to_level == 1
    assert violence.guidance


def test_acknowledgement_delta_records_no_movement(kb: KnowledgeBase) -> None:
    """An acknowledgement changes nothing, and the trail must not imply it did."""
    report = detect(_bundle(), kb)
    resolved = apply_resolutions(report, _choices_clearing_every_hard(report, 2), kb)
    for delta in resolved.deltas:
        assert delta.from_level is None
        assert delta.to_level is None


def test_soft_and_advisory_choices_are_recorded_too(kb: KnowledgeBase) -> None:
    report = detect(_bundle(), kb)
    hard = _choices_clearing_every_hard(report)
    soft = next(c for c in report.conflicts if c.severity is Severity.SOFT)
    choices = (*hard, ResolutionChoice(rule_id=soft.rule_id, resolution_id=soft.resolutions[0].id))

    resolved = apply_resolutions(report, choices, kb)
    assert soft.rule_id in {delta.rule_id for delta in resolved.deltas}


def test_resolution_without_a_declared_effect_records_an_acknowledgement(
    kb: KnowledgeBase,
) -> None:
    """The schema makes ``effect`` optional; an absent one is an acknowledgement."""
    import dataclasses

    rule = {
        "id": "effectless_rule",
        "severity": "SOFT",
        "title": "Effectless",
        "predicate": {
            "type": "equals",
            "left": {"path": "genre.id"},
            "right": {"literal": "horror"},
        },
        "explanation_template": "No effect declared.",
        "resolutions": [
            {"id": "one", "label": "One", "description": "First."},
            {"id": "two", "label": "Two", "description": "Second."},
        ],
    }
    scoped = dataclasses.replace(kb, conflict_rules=(rule,))
    report = detect(_bundle(), scoped)
    resolved = apply_resolutions(
        report, (ResolutionChoice(rule_id="effectless_rule", resolution_id="one"),), scoped
    )
    assert resolved.deltas[0].effect_kind is ResolutionEffectKind.ACKNOWLEDGE_RELAXATION
    assert resolved.deltas[0].dimension is None


# ------------------------------------------------------------------ references


def test_choice_naming_an_absent_conflict_is_rejected(kb: KnowledgeBase) -> None:
    report = detect(_bundle(), kb)
    with pytest.raises(UnknownResolutionError, match="no conflict"):
        apply_resolutions(
            report, (ResolutionChoice(rule_id="invented_rule", resolution_id="x"),), kb
        )


def test_choice_naming_an_unoffered_resolution_is_rejected(kb: KnowledgeBase) -> None:
    report = detect(_bundle(), kb)
    blocker = next(c for c in report.conflicts if c.severity is Severity.HARD)
    with pytest.raises(UnknownResolutionError, match="does not offer"):
        apply_resolutions(
            report,
            (ResolutionChoice(rule_id=blocker.rule_id, resolution_id="invented_option"),),
            kb,
        )


def test_clamp_with_non_numeric_evidence_records_no_levels(kb: KnowledgeBase) -> None:
    """A clamp on a non-numeric axis has nothing to record as movement.

    ``ordinal_exceeds`` rules compare enum positions, not levels, so a clamp
    attached to one must leave from/to unset rather than inventing numbers
    from strings.
    """
    import dataclasses

    rule = {
        "id": "ordinal_clamp_rule",
        "severity": "SOFT",
        "title": "Ordinal clamp",
        "predicate": {
            "type": "ordinal_exceeds",
            "left": {"path": "genre.scope_demands.action_complexity"},
            "right": {"path": "budget.scope.action_complexity"},
        },
        "explanation_template": "Action at {left} against {right}.",
        "resolutions": [
            {
                "id": "clamp_it",
                "label": "Clamp",
                "description": "Stage within the tier.",
                "effect": {
                    "kind": "clamp_dimension_to_permitted",
                    "dimension": "violence",
                    "guidance": "Keep action within the tier.",
                },
            },
            {"id": "other", "label": "Other", "description": "Something else."},
        ],
    }
    scoped = dataclasses.replace(kb, conflict_rules=(rule,))
    report = detect(_bundle(), scoped)
    resolved = apply_resolutions(
        report, (ResolutionChoice(rule_id="ordinal_clamp_rule", resolution_id="clamp_it"),), scoped
    )
    delta = resolved.deltas[0]
    assert delta.effect_kind is ResolutionEffectKind.CLAMP_DIMENSION_TO_PERMITTED
    assert delta.from_level is None
    assert delta.to_level is None
    assert delta.guidance
