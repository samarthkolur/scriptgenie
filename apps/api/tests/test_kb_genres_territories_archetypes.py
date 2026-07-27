"""Tests for genre, territory and archetype data."""

from __future__ import annotations

from typing import Any

import pytest

from app.kb.loader import load_data_file

DIMENSIONS = (
    "violence",
    "sexual_content",
    "language",
    "thematic_darkness",
    "drug_use",
    "horror_intensity",
)


@pytest.fixture(scope="module")
def genres() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = load_data_file("genres")["items"]
    return items


@pytest.fixture(scope="module")
def territories() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = load_data_file("territories")["items"]
    return items


@pytest.fixture(scope="module")
def archetypes() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = load_data_file("archetypes")["items"]
    return items


class TestGenres:
    def test_ten_genres_are_defined(self, genres: list[dict[str, Any]]) -> None:
        assert {genre["id"] for genre in genres} == {
            "horror",
            "thriller",
            "drama",
            "comedy",
            "action",
            "sci_fi",
            "romance",
            "mystery",
            "documentary_style",
            "family",
        }

    def test_demands_use_the_same_vocabulary_as_rating_thresholds(
        self, genres: list[dict[str, Any]]
    ) -> None:
        """The shared vocabulary is what makes conflict detection arithmetic."""
        rating_payload = load_data_file("rating_systems")
        threshold_keys = set(rating_payload["items"][0]["classifications"][0]["thresholds"])

        for genre in genres:
            assert set(genre["content_demands"]) == threshold_keys == set(DIMENSIONS)

    def test_every_genre_states_its_conventions(self, genres: list[dict[str, Any]]) -> None:
        for genre in genres:
            assert len(genre["conventions"]) >= 3, (
                f"{genre['id']} needs conventions to quote when explaining a conflict"
            )
            assert genre["citations"]

    def test_horror_demands_more_violence_than_pg_13_permits(
        self, genres: list[dict[str, Any]]
    ) -> None:
        """The tension the worked example in the research turns on.

        If horror's demand ever dropped to the PG-13 ceiling, the flagship
        genre-versus-rating conflict would stop firing and the product would
        silently lose its most demonstrable behaviour.
        """
        horror = next(genre for genre in genres if genre["id"] == "horror")
        rating_payload = load_data_file("rating_systems")
        mpa = next(system for system in rating_payload["items"] if system["id"] == "mpa")
        pg_13 = next(c for c in mpa["classifications"] if c["id"] == "pg_13")

        assert horror["content_demands"]["violence"] > pg_13["thresholds"]["violence"]
        assert (
            horror["content_demands"]["horror_intensity"] > pg_13["thresholds"]["horror_intensity"]
        )

    def test_family_demands_fit_inside_the_most_restrictive_ratings(
        self, genres: list[dict[str, Any]]
    ) -> None:
        family = next(genre for genre in genres if genre["id"] == "family")
        rating_payload = load_data_file("rating_systems")
        mpa = next(system for system in rating_payload["items"] if system["id"] == "mpa")
        g_rating = next(c for c in mpa["classifications"] if c["id"] == "g")

        for dimension in DIMENSIONS:
            assert family["content_demands"][dimension] <= g_rating["thresholds"][dimension], (
                f"family genre must not conflict with a G rating on {dimension}"
            )

    def test_hybrid_partnerships_are_symmetric_where_declared(
        self, genres: list[dict[str, Any]]
    ) -> None:
        """If A pairs with B, B must not silently exclude A.

        Asymmetry here would make hybrid suggestions depend on which genre the
        user happened to pick first.
        """
        partners = {genre["id"]: set(genre.get("hybrid_friendly", [])) for genre in genres}

        for genre_id, listed in partners.items():
            for partner in listed:
                assert genre_id in partners[partner], (
                    f"{genre_id} lists {partner} as a hybrid partner but not the reverse"
                )

    def test_action_demands_more_scope_than_a_micro_budget_allows(
        self, genres: list[dict[str, Any]]
    ) -> None:
        action = next(genre for genre in genres if genre["id"] == "action")
        micro = next(
            tier for tier in load_data_file("budget_tiers")["items"] if tier["id"] == "micro"
        )

        assert action["scope_demands"]["typical_locations"] > micro["scope"]["max_locations"]
        assert (
            action["scope_demands"]["typical_named_characters"]
            > micro["scope"]["max_named_characters"]
        )


class TestTerritories:
    def test_five_territories_with_regulators(self, territories: list[dict[str, Any]]) -> None:
        assert {t["id"] for t in territories} == {"us", "uk", "india", "germany", "australia"}
        for territory in territories:
            assert territory["regulator"]
            assert territory["citations"]

    def test_restrictions_are_tied_to_a_dimension_and_cited(
        self, territories: list[dict[str, Any]]
    ) -> None:
        for territory in territories:
            for restriction in territory.get("additional_restrictions", []):
                assert restriction["dimension"] in DIMENSIONS
                assert 0 <= restriction["max_level"] <= 4
                assert restriction["citation"]
                assert restriction["description"]

    def test_india_tightens_violence_below_its_own_rating_threshold(
        self, territories: list[dict[str, Any]]
    ) -> None:
        """A territory restriction only matters if it binds tighter than the rating.

        India is the case the multi-territory workflow exists for; a
        restriction at or above the rating threshold would be inert.
        """
        india = next(t for t in territories if t["id"] == "india")
        restriction = next(
            r for r in india["additional_restrictions"] if r["id"] == "cbfc_violence_against_women"
        )
        cbfc = next(
            system for system in load_data_file("rating_systems")["items"] if system["id"] == "cbfc"
        )
        ua = next(c for c in cbfc["classifications"] if c["id"] == "ua")

        assert restriction["max_level"] <= ua["thresholds"]["violence"]

    def test_every_territory_names_a_rating_system(self, territories: list[dict[str, Any]]) -> None:
        system_ids = {s["id"] for s in load_data_file("rating_systems")["items"]}
        for territory in territories:
            assert territory["rating_system"] in system_ids


class TestArchetypes:
    def test_five_archetypes_are_defined(self, archetypes: list[dict[str, Any]]) -> None:
        assert {a["id"] for a in archetypes} == {
            "crucible",
            "ensemble_convergence",
            "non_linear_revelation",
            "pursuit",
            "transformation_arc",
        }

    def test_blueprints_meet_their_declared_beat_minimum(
        self, archetypes: list[dict[str, Any]]
    ) -> None:
        for archetype in archetypes:
            assert len(archetype["structural_blueprint"]) >= archetype["min_beats"] >= 5
            for beat in archetype["structural_blueprint"]:
                assert beat["function"] and beat["description"]

    def test_beat_functions_are_unique_within_an_archetype(
        self, archetypes: list[dict[str, Any]]
    ) -> None:
        for archetype in archetypes:
            functions = [beat["function"] for beat in archetype["structural_blueprint"]]
            assert len(functions) == len(set(functions))

    def test_no_two_archetypes_share_a_beat_sequence(
        self, archetypes: list[dict[str, Any]]
    ) -> None:
        """Structural diversity is the product's claim; identical blueprints would void it."""
        sequences = [
            tuple(beat["function"] for beat in archetype["structural_blueprint"])
            for archetype in archetypes
        ]
        assert len(sequences) == len(set(sequences))

    def test_every_archetype_scores_every_budget_tier_and_genre(
        self, archetypes: list[dict[str, Any]]
    ) -> None:
        budget_ids = {t["id"] for t in load_data_file("budget_tiers")["items"]}
        genre_ids = {g["id"] for g in load_data_file("genres")["items"]}

        for archetype in archetypes:
            assert set(archetype["budget_affinity"]) == budget_ids
            assert set(archetype["genre_affinity"]) == genre_ids

    def test_at_least_two_archetypes_are_viable_at_micro_budget(
        self, archetypes: list[dict[str, Any]]
    ) -> None:
        """Variant sets need distinct archetypes, so the tightest tier must offer choice.

        With fewer than two strong options at micro budget, the selector could
        not produce a diverse set for the constraint bundle that most needs one.
        """
        strong = [a["id"] for a in archetypes if a["budget_affinity"]["micro"] >= 3]
        assert len(strong) >= 2
        assert "crucible" in strong

    def test_ensemble_convergence_is_unsuited_to_micro_budget(
        self, archetypes: list[dict[str, Any]]
    ) -> None:
        ensemble = next(a for a in archetypes if a["id"] == "ensemble_convergence")
        crucible = next(a for a in archetypes if a["id"] == "crucible")

        assert ensemble["budget_affinity"]["micro"] < crucible["budget_affinity"]["micro"]
        assert ensemble["location_pressure"] == "high"
        assert crucible["location_pressure"] == "very_low"
