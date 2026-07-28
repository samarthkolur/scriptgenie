"""Tests for Layer 1, the deterministic conflict detector.

Three things are being established here, in descending order of importance.

*The worked example produces the verdicts the research assigns.* This is the
golden test, and it is the claim the whole system rests on.

*The same inputs always produce the same output.* Byte-identical, not
merely equivalent. A conflict report that varied between runs would make every
downstream claim unfalsifiable.

*Every predicate in the schema's vocabulary is implemented and no others.*
Including the two combinators the shipped rule set does not currently use,
which are tested against synthetic rules because an unused branch is exactly
where an implementation quietly diverges from its schema.
"""

from __future__ import annotations

import dataclasses
import random
import re
import time
from typing import Any

import pytest

from app.domain import (
    AudienceSelection,
    ConstraintBundle,
    GenreSelection,
    RatingTarget,
    Severity,
    TerritorySet,
)
from app.engines.conflict_detector import RENDERABLE, detect
from app.engines.errors import ConflictDetectionError, UnknownReferenceError
from app.kb.loader import JsonObject, KnowledgeBase, load_knowledge_base

TEMPLATE_PLACEHOLDER = re.compile(r"{(\w+)}")


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


def _with_rules(kb: KnowledgeBase, *rules: JsonObject) -> KnowledgeBase:
    """A knowledge base carrying only the given rules, for isolating behaviour."""
    return dataclasses.replace(kb, conflict_rules=tuple(rules))


def _rule(predicate: JsonObject, **overrides: Any) -> JsonObject:
    rule: JsonObject = {
        "id": "synthetic_rule",
        "severity": "ADVISORY",
        "title": "Synthetic",
        "predicate": predicate,
        "explanation_template": "synthetic",
        "resolutions": [
            {"id": "one", "label": "One", "description": "First option."},
            {"id": "two", "label": "Two", "description": "Second option."},
        ],
    }
    rule.update(overrides)
    return rule


# ------------------------------------------------------------------ golden


class TestWorkedExample:
    """Horror-comedy, PG-13, micro budget, released in the US and India.

    The scenario the research analysis works through end to end. Stage 1.5
    encoded the three tensions it identifies; this asserts the detector
    actually produces them, which is the claim that could not be tested until
    a detector existed.
    """

    def test_genre_versus_rating_violence_is_soft(self, kb: KnowledgeBase) -> None:
        conflict = next(
            c for c in detect(_bundle(), kb).conflicts if c.rule_id == "genre_rating_violence_gap"
        )
        assert conflict.severity is Severity.SOFT
        # Horror conventionally works at violence 3; PG-13 permits 2.
        assert conflict.evidence["left"] == "3"
        assert conflict.evidence["right"] == "2"
        resolution_ids = {r.id for r in conflict.resolutions}
        assert {"shift_to_implied_violence", "raise_rating_target"} <= resolution_ids

    def test_india_stricter_than_target_rating_is_hard(self, kb: KnowledgeBase) -> None:
        conflict = next(
            c
            for c in detect(_bundle(), kb).conflicts
            if c.rule_id == "territory_violence_stricter_than_rating"
        )
        assert conflict.severity is Severity.HARD
        assert conflict.hard_rationale
        # PG-13 permits violence 2; CBFC restricts to 1 for this classification.
        assert conflict.evidence == {
            "left": "2",
            "right": "1",
            "dimension": "violence",
            "territory": "india",
        }
        assert "India" in conflict.explanation

    def test_micro_budget_location_pressure_is_advisory(self, kb: KnowledgeBase) -> None:
        conflict = next(
            c for c in detect(_bundle(), kb).conflicts if c.rule_id == "budget_location_pressure"
        )
        assert conflict.severity is Severity.ADVISORY
        # Horror moves across 5 locations; micro supports 3.
        assert conflict.evidence["left"] == "5"
        assert conflict.evidence["right"] == "3"

    def test_the_bundle_is_blocked(self, kb: KnowledgeBase) -> None:
        assert detect(_bundle(), kb).blocking is True

    def test_the_complete_report_is_pinned(self, kb: KnowledgeBase) -> None:
        """The full report, not only the three documented tensions.

        BUILD_PLAN describes this bundle as returning exactly one conflict per
        severity. That was written from the research analysis, which works
        through three tensions; the rule set curated later in Stage 1.5 finds
        thirteen, and the three documented ones are among them at the
        documented severities. Pinning the whole list means a rule change that
        alters this bundle's verdict has to be an explicit decision rather
        than a surprise.
        """
        report = detect(_bundle(), kb)
        assert [(c.severity.value, c.rule_id) for c in report.conflicts] == [
            ("HARD", "territory_drug_use_stricter_than_rating"),
            ("HARD", "territory_violence_stricter_than_rating"),
            ("SOFT", "budget_action_complexity_gap"),
            ("SOFT", "budget_period_setting_gap"),
            ("SOFT", "budget_vfx_complexity_gap"),
            ("SOFT", "genre_rating_horror_intensity_gap"),
            ("SOFT", "genre_rating_thematic_darkness_gap"),
            ("SOFT", "genre_rating_violence_gap"),
            ("ADVISORY", "budget_cast_pressure"),
            ("ADVISORY", "budget_location_pressure"),
            ("ADVISORY", "micro_budget_ensemble_pressure"),
            ("ADVISORY", "secondary_genre_content_conflict"),
            ("ADVISORY", "secondary_genre_location_pressure"),
        ]

    def test_explanations_carry_real_values_not_placeholders(self, kb: KnowledgeBase) -> None:
        for conflict in detect(_bundle(), kb).conflicts:
            assert "{" not in conflict.explanation, f"{conflict.rule_id} left a placeholder"
            assert conflict.explanation.strip()


# ------------------------------------------------------------------ ordering


def test_conflicts_are_ordered_by_severity_then_rule_id(kb: KnowledgeBase) -> None:
    conflicts = detect(_bundle(), kb).conflicts
    ranks = {Severity.HARD: 0, Severity.SOFT: 1, Severity.ADVISORY: 2}
    keys = [(ranks[c.severity], c.rule_id) for c in conflicts]
    assert keys == sorted(keys)


def test_report_carries_its_bundle_and_kb_version(kb: KnowledgeBase) -> None:
    bundle = _bundle()
    report = detect(bundle, kb)
    assert report.bundle == bundle
    assert report.kb_version == kb.version
    assert report.rules_evaluated == len(kb.conflict_rules)


def test_territory_order_does_not_change_the_verdict(kb: KnowledgeBase) -> None:
    """The binding territory is chosen by restriction, not by listing order."""
    forward = detect(_bundle(territories=TerritorySet(ids=("us", "india"))), kb)
    reverse = detect(_bundle(territories=TerritorySet(ids=("india", "us"))), kb)
    assert [c.rule_id for c in forward.conflicts] == [c.rule_id for c in reverse.conflicts]
    assert [c.explanation for c in forward.conflicts] == [c.explanation for c in reverse.conflicts]


# ------------------------------------------------------------------ determinism


def test_five_hundred_random_bundles_are_byte_identical_across_runs(kb: KnowledgeBase) -> None:
    """The property the research claim depends on.

    Serialised and compared as JSON rather than by model equality, because
    equality could hold while field order or numeric formatting differed, and
    a report that serialises differently is not reproducible in practice.
    """
    rng = random.Random(20260728)
    genres = [g["id"] for g in kb.genres]
    tiers = [b["id"] for b in kb.budget_tiers]
    territories = [t["id"] for t in kb.territories]
    systems = [(s["id"], c["id"]) for s in kb.rating_systems for c in s["classifications"]]

    for _ in range(500):
        primary = rng.choice(genres)
        secondary_pool = [g for g in genres if g != primary]
        secondary = rng.choice(secondary_pool) if rng.random() < 0.5 else None
        system, classification = rng.choice(systems)
        chosen = rng.sample(territories, rng.randint(1, len(territories)))
        low = rng.randint(0, 60)

        bundle = ConstraintBundle(
            genre=GenreSelection(primary=primary, secondary=secondary),
            audience=AudienceSelection(min_age=low, max_age=low + rng.randint(0, 40)),
            rating=RatingTarget(system=system, classification=classification),
            budget_tier_id=rng.choice(tiers),
            territories=TerritorySet(ids=tuple(chosen)),
        )

        first = detect(bundle, kb).model_dump_json()
        second = detect(bundle, kb).model_dump_json()
        assert first == second


def test_detection_is_within_the_latency_budget(kb: KnowledgeBase) -> None:
    """p95 under 100 ms for a six-constraint bundle against the full rule set."""
    bundle = _bundle(territories=TerritorySet(ids=("us", "india", "uk", "germany")))
    samples: list[float] = []
    for _ in range(200):
        started = time.perf_counter()
        detect(bundle, kb)
        samples.append((time.perf_counter() - started) * 1000)

    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 100, f"p95 was {p95:.2f} ms"


# ------------------------------------------------------------------ context


def test_territory_restriction_that_does_not_bite_is_not_applied(kb: KnowledgeBase) -> None:
    """The false-HARD guard.

    The UK drug restriction applies from BBFC 15 upward. A U-rated family film
    is nowhere near it, so it must not raise a HARD conflict. Applying every
    restriction unconditionally would be the easy implementation and would
    block writers over rules that do not apply to them.
    """
    bundle = _bundle(
        genre=GenreSelection(primary="family"),
        rating=RatingTarget(system="bbfc", classification="u"),
        territories=TerritorySet(ids=("uk",)),
        budget_tier_id="studio",
    )
    rule_ids = {c.rule_id for c in detect(bundle, kb).conflicts}
    assert "territory_drug_use_stricter_than_rating" not in rule_ids


def test_territory_restriction_that_does_bite_is_applied(kb: KnowledgeBase) -> None:
    """The same restriction at a classification it governs must fire.

    ``applies_from_classification`` is ``fifteen``, meaning the restriction
    bites at BBFC 15 and below. At 15 the category permits drug depiction at
    level 3 while the territory restriction caps it at 2, so this is a real
    HARD conflict — and at 18, tested above the boundary, it correctly is not.
    """
    bundle = _bundle(
        genre=GenreSelection(primary="drama"),
        rating=RatingTarget(system="bbfc", classification="fifteen"),
        territories=TerritorySet(ids=("uk",)),
        budget_tier_id="studio",
    )
    conflict = next(
        c
        for c in detect(bundle, kb).conflicts
        if c.rule_id == "territory_drug_use_stricter_than_rating"
    )
    assert conflict.severity is Severity.HARD
    assert conflict.evidence["territory"] == "uk"


def test_unbounded_ceiling_is_never_exceeded(kb: KnowledgeBase) -> None:
    """The studio tier stores null bounds; a ceiling that does not exist cannot bind."""
    bundle = _bundle(genre=GenreSelection(primary="action"), budget_tier_id="studio")
    rule_ids = {c.rule_id for c in detect(bundle, kb).conflicts}
    assert "budget_location_pressure" not in rule_ids
    assert "budget_cast_pressure" not in rule_ids


def test_absent_secondary_genre_fires_no_secondary_rules(kb: KnowledgeBase) -> None:
    bundle = _bundle(genre=GenreSelection(primary="horror"))
    rule_ids = {c.rule_id for c in detect(bundle, kb).conflicts}
    assert not any(rule_id.startswith("secondary_genre") for rule_id in rule_ids)


def test_most_restrictive_territory_binds(kb: KnowledgeBase) -> None:
    """Several territories each impose a ceiling; the production must satisfy all."""
    bundle = _bundle(
        genre=GenreSelection(primary="drama"),
        rating=RatingTarget(system="mpa", classification="nc_17"),
        territories=TerritorySet(ids=("us", "india", "germany")),
        budget_tier_id="studio",
    )
    conflict = next(
        c
        for c in detect(bundle, kb).conflicts
        if c.rule_id == "territory_violence_stricter_than_rating"
    )
    # India restricts violence to 1, Germany to 3; India is the binding one.
    assert conflict.evidence["territory"] == "india"
    assert conflict.evidence["right"] == "1"


# ------------------------------------------------------------------ references


@pytest.mark.parametrize(
    ("overrides", "kind"),
    [
        ({"genre": GenreSelection(primary="westerns")}, "genre"),
        ({"budget_tier_id": "enormous"}, "budget tier"),
        ({"territories": TerritorySet(ids=("atlantis",))}, "territory"),
        ({"rating": RatingTarget(system="ofcom", classification="pg_13")}, "rating system"),
        ({"rating": RatingTarget(system="mpa", classification="pg_99")}, "classification"),
        ({"genre": GenreSelection(primary="horror", secondary="westerns")}, "genre"),
    ],
)
def test_unknown_references_are_rejected(
    kb: KnowledgeBase, overrides: dict[str, Any], kind: str
) -> None:
    """Shape validation cannot know that 'westerns' is not a genre; this can."""
    with pytest.raises(UnknownReferenceError) as exc:
        detect(_bundle(**overrides), kb)
    assert exc.value.kind == kind


# ------------------------------------------------------------------ predicates


def test_any_of_fires_when_one_operand_holds(kb: KnowledgeBase) -> None:
    """``any_of`` is unused by the shipped rule set, so it is tested directly."""
    rule = _rule(
        {
            "type": "any_of",
            "operands": [
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "nope"}},
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "horror"}},
            ],
        }
    )
    assert len(detect(_bundle(), _with_rules(kb, rule)).conflicts) == 1


def test_any_of_does_not_fire_when_no_operand_holds(kb: KnowledgeBase) -> None:
    rule = _rule(
        {
            "type": "any_of",
            "operands": [
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "nope"}}
            ],
        }
    )
    assert detect(_bundle(), _with_rules(kb, rule)).conflicts == ()


def test_none_of_fires_when_no_operand_holds(kb: KnowledgeBase) -> None:
    rule = _rule(
        {
            "type": "none_of",
            "operands": [
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "nope"}}
            ],
        }
    )
    assert len(detect(_bundle(), _with_rules(kb, rule)).conflicts) == 1


def test_none_of_does_not_fire_when_an_operand_holds(kb: KnowledgeBase) -> None:
    rule = _rule(
        {
            "type": "none_of",
            "operands": [
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "horror"}}
            ],
        }
    )
    assert detect(_bundle(), _with_rules(kb, rule)).conflicts == ()


def test_all_of_does_not_fire_when_one_operand_fails(kb: KnowledgeBase) -> None:
    rule = _rule(
        {
            "type": "all_of",
            "operands": [
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "horror"}},
                {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "nope"}},
            ],
        }
    )
    assert detect(_bundle(), _with_rules(kb, rule)).conflicts == ()


def test_not_equals(kb: KnowledgeBase) -> None:
    rule = _rule(
        {"type": "not_equals", "left": {"path": "genre.id"}, "right": {"literal": "comedy"}}
    )
    assert len(detect(_bundle(), _with_rules(kb, rule)).conflicts) == 1


def test_includes_on_a_missing_member_does_not_fire(kb: KnowledgeBase) -> None:
    rule = _rule(
        {"type": "includes", "left": {"path": "territories.ids"}, "right": {"literal": "japan"}}
    )
    assert detect(_bundle(), _with_rules(kb, rule)).conflicts == ()


def test_unresolvable_path_does_not_fire(kb: KnowledgeBase) -> None:
    """A path that reaches nothing means the rule does not apply, not an error."""
    rule = _rule(
        {"type": "equals", "left": {"path": "genre.nonexistent"}, "right": {"literal": "x"}}
    )
    assert detect(_bundle(), _with_rules(kb, rule)).conflicts == ()


def test_unknown_predicate_type_is_rejected(kb: KnowledgeBase) -> None:
    rule = _rule({"type": "resembles", "left": {"path": "genre.id"}, "right": {"literal": "x"}})
    with pytest.raises(ConflictDetectionError, match="unknown predicate type"):
        detect(_bundle(), _with_rules(kb, rule))


def test_includes_requires_a_collection(kb: KnowledgeBase) -> None:
    rule = _rule({"type": "includes", "left": {"path": "genre.id"}, "right": {"literal": "horror"}})
    with pytest.raises(ConflictDetectionError, match="needs a collection"):
        detect(_bundle(), _with_rules(kb, rule))


def test_numeric_predicate_on_a_non_number_is_rejected(kb: KnowledgeBase) -> None:
    rule = _rule(
        {"type": "count_gte", "left": {"path": "genre.id"}, "right": {"literal": 3}},
    )
    with pytest.raises(ConflictDetectionError, match="needs a number"):
        detect(_bundle(), _with_rules(kb, rule))


def test_boolean_is_not_accepted_as_a_number(kb: KnowledgeBase) -> None:
    """``True == 1`` in Python; the domain does not mean that."""
    rule = _rule(
        {"type": "count_gte", "left": {"literal": True}, "right": {"literal": 1}},
    )
    with pytest.raises(ConflictDetectionError, match="needs a number"):
        detect(_bundle(), _with_rules(kb, rule))


def test_ordinal_comparison_on_an_unordered_field_is_rejected(kb: KnowledgeBase) -> None:
    rule = _rule(
        {
            "type": "ordinal_exceeds",
            "left": {"path": "genre.id"},
            "right": {"path": "budget.id"},
        }
    )
    with pytest.raises(ConflictDetectionError, match="no declared order"):
        detect(_bundle(), _with_rules(kb, rule))


# ------------------------------------------------------------------ rendering


def test_template_naming_an_unbindable_value_is_rejected(kb: KnowledgeBase) -> None:
    """A hole in an explanation is worse than a loud failure."""
    rule = _rule(
        {"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "horror"}},
        explanation_template="This needs {territory_restriction} which never bound.",
    )
    with pytest.raises(ConflictDetectionError, match="did not supply it"):
        detect(_bundle(), _with_rules(kb, rule))


def test_every_shipped_template_stays_inside_the_renderable_vocabulary(
    kb: KnowledgeBase,
) -> None:
    """Static guard on the whole rule set, including rules no test fires."""
    for rule in kb.conflict_rules:
        used = set(TEMPLATE_PLACEHOLDER.findall(rule["explanation_template"]))
        assert used <= RENDERABLE, f"{rule['id']} uses unknown placeholders {used - RENDERABLE}"


def test_list_values_render_readably(kb: KnowledgeBase) -> None:
    rule = _rule(
        {"type": "count_gte", "left": {"path": "territories.count"}, "right": {"literal": 1}},
        explanation_template="Selected {left} territories.",
    )
    conflict = detect(_bundle(), _with_rules(kb, rule)).conflicts[0]
    assert conflict.explanation == "Selected 2 territories."


def test_resolution_effects_are_carried_through(kb: KnowledgeBase) -> None:
    conflict = next(
        c for c in detect(_bundle(), kb).conflicts if c.rule_id == "genre_rating_violence_gap"
    )
    clamp = next(r for r in conflict.resolutions if r.id == "shift_to_implied_violence")
    assert clamp.effect is not None
    assert clamp.effect.dimension is not None
    assert clamp.effect.guidance


def test_resolution_without_an_effect_is_carried_through(kb: KnowledgeBase) -> None:
    rule = _rule({"type": "equals", "left": {"path": "genre.id"}, "right": {"literal": "horror"}})
    conflict = detect(_bundle(), _with_rules(kb, rule)).conflicts[0]
    assert all(option.effect is None for option in conflict.resolutions)


def test_no_conflicts_is_a_valid_report(kb: KnowledgeBase) -> None:
    report = detect(_bundle(), _with_rules(kb))
    assert report.conflicts == ()
    assert report.blocking is False
    assert report.rules_evaluated == 0


# ------------------------------------------------------------------ edge branches


def test_the_tighter_of_two_restrictions_on_one_dimension_governs(kb: KnowledgeBase) -> None:
    """The schema permits several restrictions per dimension; the data has none yet.

    Tested against a synthetic territory rather than left to chance, because a
    territory adding a second restriction later must tighten the ceiling, not
    replace it with whichever entry happened to be last.
    """
    territory = {
        "id": "testland",
        "label": "Testland",
        "regulator": "Test Board",
        "rating_system": "mpa",
        "additional_restrictions": [
            {
                "id": "tight",
                "dimension": "violence",
                "max_level": 0,
                "applies_from_classification": None,
                "description": "The tighter rule.",
                "citation": "Test statute s.1",
            },
            {
                "id": "loose",
                "dimension": "violence",
                "max_level": 3,
                "applies_from_classification": None,
                "description": "The looser rule.",
                "citation": "Test statute s.2",
            },
        ],
        "citations": ["Test statute"],
    }
    scoped = dataclasses.replace(kb, territories=(*kb.territories, territory))
    bundle = _bundle(
        genre=GenreSelection(primary="drama"),
        territories=TerritorySet(ids=("testland",)),
        budget_tier_id="studio",
    )
    conflict = next(
        c
        for c in detect(bundle, scoped).conflicts
        if c.rule_id == "territory_violence_stricter_than_rating"
    )
    assert conflict.evidence["right"] == "0"
    assert "tighter" in conflict.explanation


def test_wildcard_over_a_non_collection_resolves_to_nothing(kb: KnowledgeBase) -> None:
    rule = _rule({"type": "equals", "left": {"path": "genre.id.*"}, "right": {"literal": "horror"}})
    assert detect(_bundle(), _with_rules(kb, rule)).conflicts == ()


def test_territory_binds_without_a_restriction_note(kb: KnowledgeBase) -> None:
    """The US has no additional restrictions, so there is no note to quote."""
    rule = _rule(
        {"type": "equals", "left": {"path": "territories.*.id"}, "right": {"literal": "us"}},
        explanation_template="Bound to {territory}.",
    )
    conflict = detect(_bundle(), _with_rules(kb, rule)).conflicts[0]
    assert conflict.explanation == "Bound to United States."


@pytest.mark.parametrize(
    ("literal", "rendered"),
    [
        (True, "True"),
        (3.0, "3"),
        (["a", "b"], "a, b"),
    ],
)
def test_literal_values_render_predictably(kb: KnowledgeBase, literal: Any, rendered: str) -> None:
    """Every literal shape the schema allows must render as something readable."""
    rule = _rule(
        {"type": "equals", "left": {"literal": literal}, "right": {"literal": literal}},
        explanation_template="Value is {left}.",
    )
    conflict = detect(_bundle(), _with_rules(kb, rule)).conflicts[0]
    assert conflict.explanation == f"Value is {rendered}."


def test_non_integer_float_renders_unchanged(kb: KnowledgeBase) -> None:
    rule = _rule(
        {"type": "equals", "left": {"literal": 2.5}, "right": {"literal": 2.5}},
        explanation_template="Value is {left}.",
    )
    conflict = detect(_bundle(), _with_rules(kb, rule)).conflicts[0]
    assert conflict.explanation == "Value is 2.5."
