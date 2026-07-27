"""Tests for the curated rating system data."""

from __future__ import annotations

from itertools import pairwise
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
def payload() -> dict[str, Any]:
    return load_data_file("rating_systems")


@pytest.fixture(scope="module")
def systems(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = payload["items"]
    return items


def test_all_required_systems_are_present(systems: list[dict[str, Any]]) -> None:
    assert {system["id"] for system in systems} == {"mpa", "bbfc", "cbfc", "fsk", "acb"}


def test_expected_classifications_per_system(systems: list[dict[str, Any]]) -> None:
    by_id = {system["id"]: system for system in systems}

    assert [c["id"] for c in by_id["mpa"]["classifications"]] == [
        "g",
        "pg",
        "pg_13",
        "r",
        "nc_17",
    ]
    assert [c["id"] for c in by_id["bbfc"]["classifications"]] == [
        "u",
        "pg",
        "twelve_a",
        "fifteen",
        "eighteen",
    ]
    assert [c["id"] for c in by_id["cbfc"]["classifications"]] == ["u", "ua", "a"]
    assert [c["id"] for c in by_id["fsk"]["classifications"]] == [
        "fsk_0",
        "fsk_6",
        "fsk_12",
        "fsk_16",
        "fsk_18",
    ]


def test_every_classification_scores_every_dimension(systems: list[dict[str, Any]]) -> None:
    for system in systems:
        for classification in system["classifications"]:
            assert set(classification["thresholds"]) == set(DIMENSIONS)
            assert set(classification["criteria"]) == set(DIMENSIONS), (
                f"{system['id']}.{classification['id']} must explain every threshold in prose, "
                "or a flagged conflict cannot say why in the board's own terms"
            )


def test_thresholds_never_tighten_as_a_classification_gets_older(
    systems: list[dict[str, Any]],
) -> None:
    """Within one system, a more permissive classification permits at least as much.

    An inversion would mean a writer could be told that raising their target
    rating makes a content element less acceptable.
    """
    for system in systems:
        classifications = sorted(system["classifications"], key=lambda c: c["order"])
        for lower, upper in pairwise(classifications):
            for dimension in DIMENSIONS:
                assert upper["thresholds"][dimension] >= lower["thresholds"][dimension], (
                    f"{system['id']}: {dimension} tightens from {lower['id']} to {upper['id']}"
                )


def test_minimum_audience_ages_are_non_decreasing(systems: list[dict[str, Any]]) -> None:
    for system in systems:
        classifications = sorted(system["classifications"], key=lambda c: c["order"])
        ages = [c["min_audience_age"] for c in classifications]
        assert ages == sorted(ages), f"{system['id']} audience ages are not ordered"


def test_cbfc_ua_is_stricter_on_violence_than_mpa_pg_13(
    systems: list[dict[str, Any]],
) -> None:
    """The specific asymmetry the worked example in the research turns on.

    A project targeting PG-13 for simultaneous US and Indian release is not
    automatically clear in India. If this ever became equal, the whole
    multi-territory conflict class would silently stop firing.
    """
    by_id = {system["id"]: system for system in systems}
    pg_13 = next(c for c in by_id["mpa"]["classifications"] if c["id"] == "pg_13")
    ua = next(c for c in by_id["cbfc"]["classifications"] if c["id"] == "ua")

    assert ua["thresholds"]["violence"] < pg_13["thresholds"]["violence"]
    assert ua["thresholds"]["drug_use"] < pg_13["thresholds"]["drug_use"]
    assert ua["thresholds"]["horror_intensity"] < pg_13["thresholds"]["horror_intensity"]


def test_cbfc_has_no_classification_as_permissive_as_an_adults_only_tier(
    systems: list[dict[str, Any]],
) -> None:
    by_id = {system["id"]: system for system in systems}
    cbfc_a = next(c for c in by_id["cbfc"]["classifications"] if c["id"] == "a")
    mpa_r = next(c for c in by_id["mpa"]["classifications"] if c["id"] == "r")

    assert cbfc_a["thresholds"]["sexual_content"] < mpa_r["thresholds"]["sexual_content"]


def test_equivalences_carry_confidence_and_flag_the_risky_one(
    payload: dict[str, Any],
) -> None:
    equivalences = payload["equivalences"]
    assert len(equivalences) >= 4

    for equivalence in equivalences:
        assert equivalence["confidence"] in {"high", "medium", "low"}
        assert len(equivalence["classifications"]) >= 2

    young_teen = next(e for e in equivalences if "mpa.pg_13" in e["classifications"])
    assert "cbfc.ua" in young_teen["classifications"]
    assert young_teen["confidence"] != "high", (
        "PG-13 and CBFC U/A are not interchangeable and must not be presented as such"
    )
    assert young_teen["note"]


def test_every_system_cites_a_source(systems: list[dict[str, Any]]) -> None:
    for system in systems:
        assert system["citations"], f"{system['id']} has no citation"
        assert system["authority"], f"{system['id']} names no authority"
