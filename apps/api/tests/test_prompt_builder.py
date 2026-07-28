"""Tests for the prompt builder.

The forbidden-phrase test is the one that matters. This system's claim is that
constraints are decided deterministically and the model fills a structure
inside them; a prompt that asks the model to weigh a budget or suggest a rating
quietly gives that decision back, and the resulting variant would contradict an
envelope nobody re-checked.

Snapshots cover three deliberately different envelopes -- a tightly bounded
micro production, an unbounded studio one, and a mid-tier single-territory case
-- so a change in rendering has to be reviewed as a diff rather than noticed
later in output quality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.domain import (
    AudienceSelection,
    ConstraintBundle,
    GenerationEnvelope,
    GenreSelection,
    RatingTarget,
    ResolutionChoice,
    ResolvedBundle,
    Severity,
    TerritorySet,
)
from app.engines.conflict_detector import detect
from app.engines.errors import UnknownReferenceError
from app.engines.prompt_builder import (
    FORBIDDEN_PHRASES,
    build,
    prompt_version,
    variant_schema,
)
from app.engines.resolution import apply_resolutions
from app.engines.scope_parameterizer import parameterize
from app.kb.loader import KnowledgeBase, load_knowledge_base

SNAPSHOTS = Path(__file__).parent / "snapshots"


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_knowledge_base()


def _envelope(kb: KnowledgeBase, *, settle: bool = False, **overrides: Any) -> GenerationEnvelope:
    values: dict[str, Any] = {
        "genre": GenreSelection(primary="horror", secondary="comedy"),
        "audience": AudienceSelection(min_age=15, max_age=40),
        "rating": RatingTarget(system="mpa", classification="pg_13"),
        "budget_tier_id": "micro",
        "territories": TerritorySet(ids=("us", "india")),
    }
    values.update(overrides)
    bundle = ConstraintBundle(**values)
    if not settle:
        return parameterize(ResolvedBundle(original=bundle, bundle=bundle), kb)
    report = detect(bundle, kb)
    choices = tuple(
        ResolutionChoice(rule_id=c.rule_id, resolution_id=c.resolutions[0].id)
        for c in report.conflicts
        if c.severity is Severity.HARD
    )
    return parameterize(apply_resolutions(report, choices, kb), kb)


#: The three representative cases the acceptance criterion asks for.
CASES: dict[str, dict[str, Any]] = {
    "micro_horror_comedy": {
        "archetype": "crucible",
        "overrides": {},
        "settle": True,
    },
    "studio_action_unbounded": {
        "archetype": "ensemble_convergence",
        "overrides": {
            "genre": GenreSelection(primary="action"),
            "budget_tier_id": "studio",
            "rating": RatingTarget(system="mpa", classification="nc_17"),
            "territories": TerritorySet(ids=("us",)),
        },
        "settle": False,
    },
    "low_indie_romance_uk": {
        "archetype": "transformation_arc",
        "overrides": {
            "genre": GenreSelection(primary="romance"),
            "budget_tier_id": "low_indie",
            "rating": RatingTarget(system="bbfc", classification="twelve_a"),
            "territories": TerritorySet(ids=("uk",)),
        },
        "settle": False,
    },
}


def _render(kb: KnowledgeBase, name: str) -> str:
    case = CASES[name]
    envelope = _envelope(kb, settle=bool(case["settle"]), **case["overrides"])
    system, user = build(envelope, str(case["archetype"]), kb)
    return f"{system}\n\n{'=' * 70}\n\n{user}\n"


# ------------------------------------------------------------------ snapshots


@pytest.mark.parametrize("name", sorted(CASES))
def test_rendered_prompt_matches_its_snapshot(kb: KnowledgeBase, name: str) -> None:
    """A rendering change must be reviewed as a diff, not discovered later.

    Regenerate deliberately with:
        uv run python -m tests.regenerate_prompt_snapshots
    """
    snapshot = SNAPSHOTS / f"{name}.md"
    assert snapshot.exists(), f"missing snapshot for {name}; regenerate it deliberately"
    assert _render(kb, name) == snapshot.read_text(encoding="utf-8")


# ------------------------------------------------------------------ no deciding


@pytest.mark.parametrize("name", sorted(CASES))
def test_prompt_never_asks_the_model_to_decide(kb: KnowledgeBase, name: str) -> None:
    """The acceptance criterion, over every representative envelope."""
    rendered = _render(kb, name).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in rendered, f"{name} contains deliberative phrasing: {phrase!r}"


def test_forbidden_phrases_are_absent_from_the_templates_themselves(
    kb: KnowledgeBase,
) -> None:
    """Catches a phrase added to a template that no case happens to render."""
    prompts = Path(__file__).parent.parent / "app" / "prompts"
    for template in prompts.glob("*.md"):
        text = template.read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text, f"{template.name} contains {phrase!r}"


def test_the_forbidden_phrase_check_can_fail(kb: KnowledgeBase) -> None:
    """Verifies the guard against a real violation rather than trusting it."""
    tampered = "You may want to raise the budget if the budget allows.".lower()
    hits = [phrase for phrase in FORBIDDEN_PHRASES if phrase in tampered]
    assert hits, "the guard would not catch obviously deliberative phrasing"


def test_prompt_instructs_against_reopening_constraints(kb: KnowledgeBase) -> None:
    system, _ = build(_envelope(kb), "crucible", kb)
    lowered = system.lower()
    assert "do not suggest changing any constraint" in lowered
    assert "settled facts" in lowered


# ------------------------------------------------------------------ constraints


def test_scope_bounds_are_explicit_numbered_hard_constraints(kb: KnowledgeBase) -> None:
    """The acceptance criterion: enumerated limits, not narrative context."""
    _, user = build(_envelope(kb), "crucible", kb)
    section = user.split("## Hard constraints")[1].split("## Content ceilings")[0]

    assert "1. Use at most 3 distinct shooting locations. This is a hard maximum." in section
    assert "2. Use at most 5 named speaking characters. This is a hard maximum." in section
    assert "3. Visual effects may not exceed: none." in section
    assert "4. Period setting is restricted to: contemporary_only." in section
    assert "5. Staged action may not exceed: dialogue_driven." in section
    assert "6. Narrative economy required: high." in section


def test_unbounded_scope_is_stated_as_unbounded(kb: KnowledgeBase) -> None:
    """A studio tier has no ceiling, and inventing one would be fabrication."""
    envelope = _envelope(kb, budget_tier_id="studio", genre=GenreSelection(primary="action"))
    _, user = build(envelope, "ensemble_convergence", kb)
    assert "no budget ceiling on distinct shooting locations" in user
    assert "Use at most None" not in user


def test_content_ceilings_name_their_authority(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb)
    _, user = build(envelope, "crucible", kb)
    assert "violence: maximum level 1 (set by CBFC" in user


def test_every_dimension_appears_in_the_ceiling_table(kb: KnowledgeBase) -> None:
    _, user = build(_envelope(kb), "crucible", kb)
    section = user.split("## Content ceilings")[1].split("## Additional")[0]
    for dimension in (
        "violence",
        "sexual_content",
        "language",
        "thematic_darkness",
        "drug_use",
        "horror_intensity",
    ):
        assert f"- {dimension}: maximum level" in section


# ------------------------------------------------------------------ structure


def test_the_assigned_blueprint_is_reproduced_in_order(kb: KnowledgeBase) -> None:
    archetype = kb.archetype("crucible")
    _, user = build(_envelope(kb), "crucible", kb)
    functions = [beat["function"] for beat in archetype["structural_blueprint"]]
    positions = [user.index(function) for function in functions]
    assert positions == sorted(positions), "blueprint functions are out of order"


def test_secondary_genre_conventions_are_attributed(kb: KnowledgeBase) -> None:
    _, user = build(_envelope(kb), "crucible", kb)
    assert "(from Comedy)" in user


def test_absent_secondary_genre_renders_no_modifier_line(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb, genre=GenreSelection(primary="horror"))
    _, user = build(envelope, "crucible", kb)
    assert "Secondary modifier" not in user
    assert "(from " not in user


def test_resolution_guidance_reaches_the_prompt(kb: KnowledgeBase) -> None:
    _, user = build(_envelope(kb, settle=True), "crucible", kb)
    assert "strictest selected territory" in user


def test_absent_guidance_renders_none(kb: KnowledgeBase) -> None:
    _, user = build(_envelope(kb), "crucible", kb)
    assert "## Additional directives\n\nNone." in user


# ------------------------------------------------------------------ contract


def test_schema_requires_the_archetype_minimum_beats(kb: KnowledgeBase) -> None:
    """Minimums differ per structure, so a shared floor would under-specify."""
    crucible = variant_schema(kb.archetype("crucible"))
    transformation = variant_schema(kb.archetype("transformation_arc"))
    assert crucible["properties"]["beats"]["minItems"] == 5
    assert transformation["properties"]["beats"]["minItems"] == 6


def test_schema_requires_a_per_dimension_satisfaction_statement(kb: KnowledgeBase) -> None:
    satisfaction = variant_schema(kb.archetype("crucible"))["properties"]["satisfaction"]
    assert set(satisfaction["required"]) == {
        "violence",
        "sexual_content",
        "language",
        "thematic_darkness",
        "drug_use",
        "horror_intensity",
    }
    for dimension in satisfaction["required"]:
        fields = satisfaction["properties"][dimension]["required"]
        assert set(fields) == {"level", "statement"}


def test_schema_requires_relaxation_flags(kb: KnowledgeBase) -> None:
    schema = variant_schema(kb.archetype("crucible"))
    assert "relaxations" in schema["required"]


def test_schema_is_strict_about_unknown_fields(kb: KnowledgeBase) -> None:
    """Groq's strict mode rejects a schema that permits extra properties."""
    schema = variant_schema(kb.archetype("crucible"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["beats"]["items"]["additionalProperties"] is False


def test_output_contract_is_embedded_in_the_prompt(kb: KnowledgeBase) -> None:
    _, user = build(_envelope(kb), "crucible", kb)
    assert '"relaxations"' in user
    assert "at least 5 entries" in user


# ------------------------------------------------------------------ versioning


def test_prompt_version_is_semver(kb: KnowledgeBase) -> None:
    parts = prompt_version().split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_rendering_is_deterministic(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb, settle=True)
    assert build(envelope, "crucible", kb) == build(envelope, "crucible", kb)


# ------------------------------------------------------------------ references


def test_unknown_archetype_is_rejected(kb: KnowledgeBase) -> None:
    with pytest.raises(UnknownReferenceError) as exc:
        build(_envelope(kb), "spiral_of_doom", kb)
    assert exc.value.kind == "archetype"


def test_unknown_primary_genre_is_rejected(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb).model_copy(update={"genre": GenreSelection(primary="westerns")})
    with pytest.raises(UnknownReferenceError) as exc:
        build(envelope, "crucible", kb)
    assert exc.value.kind == "genre"


def test_unknown_secondary_genre_is_rejected(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb).model_copy(
        update={"genre": GenreSelection(primary="horror", secondary="westerns")}
    )
    with pytest.raises(UnknownReferenceError) as exc:
        build(envelope, "crucible", kb)
    assert exc.value.kind == "genre"
