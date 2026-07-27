"""Tests for the conflict rule set.

Severity discipline is what these tests mostly protect. HARD blocks a writer's
work, so every HARD rule has to justify itself; if HARD ever becomes the easy
default, the product reproduces the refusal behaviour it was built to replace.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.kb.loader import load_data_file, load_knowledge_base

DIMENSIONS = {
    "violence",
    "sexual_content",
    "language",
    "thematic_darkness",
    "drug_use",
    "horror_intensity",
}

COMPARISON_TYPES = {
    "dimension_exceeds",
    "scope_exceeds",
    "ordinal_exceeds",
    "equals",
    "not_equals",
    "includes",
    "count_gte",
}
LOGICAL_TYPES = {"all_of", "any_of", "none_of"}


@pytest.fixture(scope="module")
def rules() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = load_data_file("conflict_rules")["items"]
    return items


def walk_predicates(predicate: dict[str, Any]) -> list[dict[str, Any]]:
    if predicate["type"] in LOGICAL_TYPES:
        found: list[dict[str, Any]] = []
        for operand in predicate["operands"]:
            found.extend(walk_predicates(operand))
        return found
    return [predicate]


class TestCoverage:
    def test_rule_set_is_substantial(self, rules: list[dict[str, Any]]) -> None:
        assert len(rules) >= 25

    def test_every_severity_is_represented(self, rules: list[dict[str, Any]]) -> None:
        severities = {rule["severity"] for rule in rules}
        assert severities == {"HARD", "SOFT", "ADVISORY"}

    def test_every_content_dimension_has_a_genre_versus_rating_rule(
        self, rules: list[dict[str, Any]]
    ) -> None:
        """A dimension with no rule is a gap that fails silently."""
        covered = set()
        for rule in rules:
            for predicate in walk_predicates(rule["predicate"]):
                left = predicate["left"].get("path", "")
                right = predicate["right"].get("path", "")
                if left.startswith("genre.content_demands.") and right.startswith(
                    "rating.thresholds."
                ):
                    covered.add(left.rsplit(".", 1)[1])

        assert covered == DIMENSIONS

    def test_budget_scope_dimensions_are_covered(self, rules: list[dict[str, Any]]) -> None:
        covered = set()
        for rule in rules:
            for predicate in walk_predicates(rule["predicate"]):
                right = predicate["right"].get("path", "")
                if right.startswith("budget.scope."):
                    covered.add(right.rsplit(".", 1)[1])

        assert {
            "max_locations",
            "max_named_characters",
            "action_complexity",
            "vfx_complexity",
            "period_setting",
        } <= covered


class TestSeverityDiscipline:
    def test_hard_rules_stay_a_small_minority(self, rules: list[dict[str, Any]]) -> None:
        hard = [rule for rule in rules if rule["severity"] == "HARD"]
        assert len(hard) / len(rules) < 0.35, (
            "if most conflicts block generation, the tool refuses work instead of "
            "explaining tensions"
        )

    def test_every_hard_rule_justifies_blocking_the_user(self, rules: list[dict[str, Any]]) -> None:
        for rule in rules:
            if rule["severity"] != "HARD":
                continue
            rationale = rule.get("hard_rationale", "")
            assert len(rationale) > 150, (
                f"{rule['id']} blocks generation without a sufficient rationale"
            )

    def test_non_hard_rules_do_not_carry_a_hard_rationale(
        self, rules: list[dict[str, Any]]
    ) -> None:
        for rule in rules:
            if rule["severity"] != "HARD":
                assert "hard_rationale" not in rule, (
                    f"{rule['id']} is {rule['severity']} but carries a hard rationale"
                )

    def test_hard_rules_offer_a_route_that_changes_the_bundle(
        self, rules: list[dict[str, Any]]
    ) -> None:
        """A blocking conflict must tell the writer what to change."""
        for rule in rules:
            if rule["severity"] != "HARD":
                continue
            kinds = {resolution.get("effect", {}).get("kind") for resolution in rule["resolutions"]}
            assert "requires_bundle_change" in kinds or "clamp_dimension_to_permitted" in kinds, (
                f"{rule['id']} blocks the user without an actionable route out"
            )


class TestRuleShape:
    def test_identifiers_are_unique(self, rules: list[dict[str, Any]]) -> None:
        ids = [rule["id"] for rule in rules]
        assert len(ids) == len(set(ids))

    def test_every_rule_offers_at_least_two_resolutions(self, rules: list[dict[str, Any]]) -> None:
        for rule in rules:
            assert len(rule["resolutions"]) >= 2, (
                f"{rule['id']} offers an instruction, not a choice"
            )
            resolution_ids = [resolution["id"] for resolution in rule["resolutions"]]
            assert len(resolution_ids) == len(set(resolution_ids))

    def test_explanations_are_substantial(self, rules: list[dict[str, Any]]) -> None:
        for rule in rules:
            template = rule["explanation_template"]
            assert len(template) > 40, f"{rule['id']} explanation is too thin to act on"

    def test_comparison_rules_state_the_measured_gap(self, rules: list[dict[str, Any]]) -> None:
        """A rule that fires on a measured difference must report the numbers.

        "Horror wants 3, PG-13 permits 2" is actionable; "there is a tension"
        is not. Rules that fire on a fixed condition instead — a specific genre
        at a specific tier — have nothing to interpolate and are exempt.
        """
        measured = {"dimension_exceeds", "scope_exceeds", "ordinal_exceeds"}

        for rule in rules:
            predicates = walk_predicates(rule["predicate"])
            compares_two_paths = any(
                predicate["type"] in measured
                and "path" in predicate["left"]
                and "path" in predicate["right"]
                for predicate in predicates
            )
            if not compares_two_paths:
                continue

            template = rule["explanation_template"]
            assert "{left}" in template and "{right}" in template, (
                f"{rule['id']} compares two values but reports neither"
            )

    def test_predicate_types_are_known(self, rules: list[dict[str, Any]]) -> None:
        for rule in rules:
            for predicate in walk_predicates(rule["predicate"]):
                assert predicate["type"] in COMPARISON_TYPES

    def test_clamp_effects_name_a_dimension_and_carry_guidance(
        self, rules: list[dict[str, Any]]
    ) -> None:
        for rule in rules:
            for resolution in rule["resolutions"]:
                effect = resolution.get("effect")
                if effect and effect["kind"] == "clamp_dimension_to_permitted":
                    assert effect.get("dimension") in DIMENSIONS, (
                        f"{rule['id']}/{resolution['id']} clamps an unnamed dimension"
                    )
                    assert effect.get("guidance"), (
                        f"{rule['id']}/{resolution['id']} clamps without telling the "
                        "generator what to do instead"
                    )


class TestWorkedExample:
    """The scenario the research analysis works through end to end.

    Horror-comedy, PG-13, micro budget, released in the United States and
    India. The rule set must contain a rule for each tension that analysis
    identifies, at the severity it identifies.
    """

    def test_genre_versus_rating_tension_is_soft(self, rules: list[dict[str, Any]]) -> None:
        rule = next(r for r in rules if r["id"] == "genre_rating_violence_gap")
        assert rule["severity"] == "SOFT"

        resolution_ids = {resolution["id"] for resolution in rule["resolutions"]}
        assert "shift_to_implied_violence" in resolution_ids
        assert "raise_rating_target" in resolution_ids

    def test_india_stricter_than_target_rating_is_hard(self, rules: list[dict[str, Any]]) -> None:
        rule = next(r for r in rules if r["id"] == "territory_violence_stricter_than_rating")
        assert rule["severity"] == "HARD"
        assert rule["hard_rationale"]

    def test_micro_budget_location_pressure_is_advisory(self, rules: list[dict[str, Any]]) -> None:
        rule = next(r for r in rules if r["id"] == "budget_location_pressure")
        assert rule["severity"] == "ADVISORY", (
            "location economy is a craft problem, not a reason to block a writer"
        )

    def test_the_documented_resolution_path_exists(self, rules: list[dict[str, Any]]) -> None:
        """The analysis resolves this bundle by moving horror toward psychological
        dread and confining the story to one location. Both must be selectable."""
        intensity_rule = next(r for r in rules if r["id"] == "genre_rating_horror_intensity_gap")
        psychological = next(
            resolution
            for resolution in intensity_rule["resolutions"]
            if resolution["id"] == "psychological_dread"
        )
        assert psychological["effect"]["kind"] == "clamp_dimension_to_permitted"
        assert psychological["effect"]["guidance"]

        location_rule = next(r for r in rules if r["id"] == "budget_location_pressure")
        assert any(
            resolution["id"] == "internal_variety" for resolution in location_rule["resolutions"]
        )


class TestKnowledgeBaseLoadsCompletely:
    def test_the_shipped_knowledge_base_loads_and_passes_integrity(self) -> None:
        """Every data file is present, valid and mutually consistent."""
        kb = load_knowledge_base()

        assert kb.version
        assert len(kb.budget_tiers) == 4
        assert len(kb.rating_systems) == 5
        assert len(kb.genres) == 10
        assert len(kb.territories) == 5
        assert len(kb.archetypes) == 5
        assert len(kb.conflict_rules) >= 25

    def test_rules_reference_only_known_genres_and_budget_tiers(self) -> None:
        kb = load_knowledge_base()
        genre_ids = {genre["id"] for genre in kb.genres}
        budget_ids = {tier["id"] for tier in kb.budget_tiers}
        territory_ids = {territory["id"] for territory in kb.territories}

        for rule in kb.conflict_rules:
            for predicate in walk_predicates(rule["predicate"]):
                for side in ("left", "right"):
                    literal = predicate[side].get("literal")
                    path = predicate[side].get("path", "")
                    if not isinstance(literal, str):
                        continue
                    if path:
                        continue
                    other = predicate["left" if side == "right" else "right"].get("path", "")
                    if other.endswith("genre.id"):
                        assert literal in genre_ids, f"{rule['id']} names unknown genre {literal}"
                    elif other == "budget.id":
                        assert literal in budget_ids, f"{rule['id']} names unknown tier {literal}"
                    elif other == "territories.ids":
                        assert literal in territory_ids, (
                            f"{rule['id']} names unknown territory {literal}"
                        )
