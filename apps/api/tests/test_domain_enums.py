"""Tests for the domain vocabulary.

The point of most of these is drift. ``app.domain.enums`` restates values the
knowledge base schemas already define, which buys type safety at the cost of a
second copy. These tests make the copy safe: they read the schema files and
assert member-for-member equality, so adding a content dimension or a rating
severity to the knowledge base without adding it here fails loudly instead of
producing an engine that silently ignores the new value.

The ordering tests exist because the ordinal vocabularies are the one place a
plausible-looking comparison gives a wrong answer with no error.
"""

from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any

import pytest

from app.domain.enums import (
    ActionComplexity,
    ContentDimension,
    ContentLevel,
    LocationPressure,
    NarrativeEconomy,
    OrdinalVocabulary,
    PeriodSetting,
    ResolutionEffectKind,
    Severity,
    VfxComplexity,
)
from app.kb.loader import default_kb_root

ORDINAL_VOCABULARIES = [VfxComplexity, PeriodSetting, ActionComplexity, LocationPressure]


def _schema(name: str) -> dict[str, Any]:
    path: Path = default_kb_root() / "schema" / f"{name}.schema.json"
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


@pytest.fixture(scope="module")
def common() -> dict[str, Any]:
    defs: dict[str, Any] = _schema("common")["$defs"]
    return defs


def test_content_dimensions_match_the_schema(common: dict[str, Any]) -> None:
    """The six axes are the contract between genre demand and rating permission."""
    schema_dimensions = list(common["contentDimensions"]["properties"])
    assert [d.value for d in ContentDimension] == schema_dimensions


def test_content_levels_span_the_schema_range(common: dict[str, Any]) -> None:
    level = common["contentLevel"]
    assert [int(v) for v in ContentLevel] == list(range(level["minimum"], level["maximum"] + 1))


def test_severities_match_the_schema(common: dict[str, Any]) -> None:
    assert [s.value for s in Severity] == common["severity"]["enum"]


@pytest.mark.parametrize(
    ("vocabulary", "schema_key"),
    [
        (VfxComplexity, "vfxComplexity"),
        (PeriodSetting, "periodSetting"),
        (ActionComplexity, "actionComplexity"),
    ],
)
def test_ordinal_vocabularies_match_the_schema_in_order(
    common: dict[str, Any],
    vocabulary: type[OrdinalVocabulary],
    schema_key: str,
) -> None:
    """Order is the semantics here, so this asserts the sequence, not the set."""
    assert [v.value for v in vocabulary] == common[schema_key]["enum"]


def test_narrative_economy_matches_the_budget_tier_schema() -> None:
    scope = _schema("budget_tier")["$defs"]["budgetTier"]["properties"]["scope"]
    expected = scope["properties"]["narrative_economy"]["enum"]
    assert [n.value for n in NarrativeEconomy] == expected


def test_location_pressure_matches_the_archetype_schema() -> None:
    archetype = _schema("archetype")["$defs"]["archetype"]["properties"]
    assert [p.value for p in LocationPressure] == archetype["location_pressure"]["enum"]


def test_resolution_effect_kinds_match_the_conflict_rule_schema() -> None:
    effect = _schema("conflict_rule")["$defs"]["resolution"]["properties"]["effect"]
    expected = effect["properties"]["kind"]["enum"]
    assert [k.value for k in ResolutionEffectKind] == expected


@pytest.mark.parametrize("vocabulary", ORDINAL_VOCABULARIES)
def test_rank_is_declaration_position(vocabulary: type[OrdinalVocabulary]) -> None:
    assert [member.rank for member in vocabulary] == list(range(len(vocabulary)))


@pytest.mark.parametrize("vocabulary", ORDINAL_VOCABULARIES)
def test_ordering_operators_are_refused(vocabulary: type[OrdinalVocabulary]) -> None:
    """The whole reason this base class exists.

    ``str`` would answer these alphabetically and never signal that the answer
    is meaningless, so the operators raise instead.
    """
    members = tuple(vocabulary)
    first, second = members[0], members[1]
    for compare in (operator.lt, operator.le, operator.gt, operator.ge):
        with pytest.raises(TypeError, match="rank"):
            compare(first, second)


def test_alphabetical_order_would_have_been_wrong() -> None:
    """Pins the specific trap: sorting VFX by value disagrees with the real order."""
    by_value = sorted(v.value for v in VfxComplexity)
    by_rank = [v.value for v in sorted(VfxComplexity, key=lambda v: v.rank)]
    assert by_value != by_rank


@pytest.mark.parametrize("vocabulary", ORDINAL_VOCABULARIES)
def test_equality_still_works(vocabulary: type[OrdinalVocabulary]) -> None:
    """Refusing ordering must not break equality, which pydantic relies on."""
    member = next(iter(vocabulary))
    assert member == member.value
    assert vocabulary(member.value) is member


def test_content_levels_compare_numerically() -> None:
    """The contrast with the ordinal vocabularies: here ``>`` is meaningful."""
    assert ContentLevel.EXPLICIT > ContentLevel.STRONG > ContentLevel.NONE
    assert ContentLevel.STRONG - ContentLevel.MILD == 2
