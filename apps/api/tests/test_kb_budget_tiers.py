"""Tests for the curated budget tier data.

These assert on the shipped knowledge base, not on a fixture. The budget-to-
scope mapping is the part of this system that decides whether a concept is
producible, so its values are tested as facts, not as shapes.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import pytest

from app.kb.loader import load_data_file

VFX_ORDER = ["none", "practical_only", "limited_digital", "unrestricted"]
PERIOD_ORDER = [
    "contemporary_only",
    "contemporary_or_recent",
    "any_with_allocation",
    "any",
]
ACTION_ORDER = [
    "dialogue_driven",
    "limited_practical",
    "moderate_set_pieces",
    "unrestricted",
]


@pytest.fixture(scope="module")
def tiers() -> list[dict[str, Any]]:
    payload = load_data_file("budget_tiers")
    items: list[dict[str, Any]] = payload["items"]
    return items


def test_file_is_schema_valid_and_has_four_tiers(tiers: list[dict[str, Any]]) -> None:
    assert [tier["id"] for tier in tiers] == ["micro", "low_indie", "mid_indie", "studio"]


def test_orders_are_sequential_and_match_position(tiers: list[dict[str, Any]]) -> None:
    assert [tier["order"] for tier in tiers] == [0, 1, 2, 3]


def test_ranges_are_contiguous_and_ascending(tiers: list[dict[str, Any]]) -> None:
    for lower, upper in pairwise(tiers):
        assert lower["range_usd"]["max"] == upper["range_usd"]["min"], (
            "budget bands must be contiguous or a project falls between two tiers"
        )
    assert tiers[-1]["range_usd"]["max"] is None, "the top tier must be unbounded above"


def test_micro_budget_bounds_match_documented_production_reality(
    tiers: list[dict[str, Any]],
) -> None:
    scope = tiers[0]["scope"]

    assert scope["max_locations"] == 3
    assert scope["max_named_characters"] == 5
    assert scope["vfx_complexity"] == "none"
    assert scope["period_setting"] == "contemporary_only"
    assert scope["action_complexity"] == "dialogue_driven"
    assert scope["narrative_economy"] == "high"


def test_low_indie_and_mid_indie_bounds(tiers: list[dict[str, Any]]) -> None:
    low = tiers[1]["scope"]
    mid = tiers[2]["scope"]

    assert (low["max_locations"], low["max_named_characters"]) == (7, 10)
    assert low["vfx_complexity"] == "practical_only"
    assert (mid["max_locations"], mid["max_named_characters"]) == (15, 20)
    assert mid["vfx_complexity"] == "limited_digital"


def test_studio_tier_imposes_no_scope_ceiling(tiers: list[dict[str, Any]]) -> None:
    scope = tiers[3]["scope"]

    assert scope["max_locations"] is None
    assert scope["max_named_characters"] is None
    assert scope["vfx_complexity"] == "unrestricted"
    assert scope["action_complexity"] == "unrestricted"


def test_scope_relaxes_monotonically_as_budget_rises(tiers: list[dict[str, Any]]) -> None:
    """A higher tier may never be more restrictive than a lower one.

    If this ever inverted, raising a project's budget could make its
    generated concepts smaller, which would be incoherent advice.
    """
    for lower, upper in pairwise(tiers):
        low_scope, high_scope = lower["scope"], upper["scope"]

        for field in ("max_locations", "max_named_characters"):
            low_value, high_value = low_scope[field], high_scope[field]
            if high_value is None:
                continue
            assert low_value is not None and high_value >= low_value, (
                f"{field} decreases from {lower['id']} to {upper['id']}"
            )

        assert VFX_ORDER.index(high_scope["vfx_complexity"]) >= VFX_ORDER.index(
            low_scope["vfx_complexity"]
        )
        assert PERIOD_ORDER.index(high_scope["period_setting"]) >= PERIOD_ORDER.index(
            low_scope["period_setting"]
        )
        assert ACTION_ORDER.index(high_scope["action_complexity"]) >= ACTION_ORDER.index(
            low_scope["action_complexity"]
        )


def test_every_tier_cites_a_source_and_explains_itself(tiers: list[dict[str, Any]]) -> None:
    for tier in tiers:
        assert tier["citations"], f"{tier['id']} has no citation"
        assert tier["guild_context"], f"{tier['id']} has no guild context"
        assert len(tier["rationale"]) > 120, (
            f"{tier['id']} rationale is too thin to defend the numbers to a user"
        )
