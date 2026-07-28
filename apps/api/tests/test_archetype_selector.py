"""Tests for Stage 2.5, archetype assignment.

Distinctness is the whole point. If this engine can ever return the same
archetype twice, the system's answer to "repeated sampling does not produce
structural diversity" is to sample repeatedly, which is the failure it was
built to correct.

The seed tests establish that reproducibility and variety are not in tension:
the same seed always gives the same assignment, and the seed can only reorder
archetypes that scored equally.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain import (
    AudienceSelection,
    ConstraintBundle,
    GenreSelection,
    RatingTarget,
    ResolvedBundle,
    TerritorySet,
)
from app.engines.archetype_selector import InsufficientArchetypesError, select
from app.engines.errors import UnknownReferenceError
from app.engines.scope_parameterizer import parameterize
from app.kb.loader import KnowledgeBase, load_knowledge_base


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_knowledge_base()


def _envelope(kb: KnowledgeBase, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "genre": GenreSelection(primary="horror"),
        "audience": AudienceSelection(min_age=15, max_age=40),
        "rating": RatingTarget(system="mpa", classification="pg_13"),
        "budget_tier_id": "micro",
        "territories": TerritorySet(ids=("us",)),
    }
    values.update(overrides)
    bundle = ConstraintBundle(**values)
    return parameterize(ResolvedBundle(original=bundle, bundle=bundle), kb)


# ------------------------------------------------------------------ acceptance


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_never_returns_duplicate_archetypes(kb: KnowledgeBase, n: int) -> None:
    """The first acceptance criterion, at every size the knowledge base allows."""
    for seed in range(8):
        assignments = select(_envelope(kb), n, kb, seed=seed)
        ids = [a.archetype_id for a in assignments]
        assert len(ids) == n
        assert len(set(ids)) == n


def test_at_micro_crucible_and_transformation_outrank_ensemble(kb: KnowledgeBase) -> None:
    """The second acceptance criterion.

    Ensemble Convergence scores 0 on budget affinity at micro — it needs a
    location count the tier cannot pay for — so it must never displace the two
    structures built for confinement.
    """
    for genre in (g["id"] for g in kb.genres):
        envelope = _envelope(kb, genre=GenreSelection(primary=genre))
        ranked = [a.archetype_id for a in select(envelope, len(kb.archetypes), kb)]
        assert ranked.index("crucible") < ranked.index("ensemble_convergence")
        assert ranked.index("transformation_arc") < ranked.index("ensemble_convergence")


def test_same_envelope_and_seed_give_the_same_assignment(kb: KnowledgeBase) -> None:
    """The third acceptance criterion."""
    envelope = _envelope(kb)
    for seed in (0, 1, 7, 20260728):
        first = select(envelope, 3, kb, seed=seed)
        second = select(envelope, 3, kb, seed=seed)
        assert first == second


# ------------------------------------------------------------------ ordering


def test_assignments_are_ordered_best_fit_first(kb: KnowledgeBase) -> None:
    scores = [a.score for a in select(_envelope(kb), len(kb.archetypes), kb)]
    assert scores == sorted(scores, reverse=True)


def test_variant_indices_are_sequential(kb: KnowledgeBase) -> None:
    assignments = select(_envelope(kb), 4, kb)
    assert [a.variant_index for a in assignments] == [0, 1, 2, 3]


def test_the_seed_only_permutes_equal_scores(kb: KnowledgeBase) -> None:
    """A seed must never promote a worse-fitting archetype above a better one."""
    envelope = _envelope(kb)
    baseline = {a.archetype_id: a.score for a in select(envelope, len(kb.archetypes), kb, seed=0)}
    for seed in range(25):
        ordered = select(envelope, len(kb.archetypes), kb, seed=seed)
        scores = [a.score for a in ordered]
        assert scores == sorted(scores, reverse=True)
        # The score of a given archetype cannot depend on the seed.
        for assignment in ordered:
            assert assignment.score == baseline[assignment.archetype_id]


def test_different_seeds_can_reorder_a_tie(kb: KnowledgeBase) -> None:
    """Otherwise the seed parameter would be decoration.

    Horror at micro ties crucible and non_linear_revelation at 6, so some seed
    must be able to put either first.
    """
    envelope = _envelope(kb)
    firsts = {select(envelope, 1, kb, seed=seed)[0].archetype_id for seed in range(40)}
    assert len(firsts) > 1


def test_scores_reflect_budget_and_genre_affinity(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb, budget_tier_id="micro", genre=GenreSelection(primary="horror"))
    assignments = {a.archetype_id: a for a in select(envelope, len(kb.archetypes), kb)}
    # crucible: budget 3 at micro, genre 3 for horror.
    assert assignments["crucible"].score == 6
    # ensemble_convergence: budget 0 at micro, genre 1 for horror.
    assert assignments["ensemble_convergence"].score == 1


def test_changing_the_budget_tier_changes_the_ranking(kb: KnowledgeBase) -> None:
    """The same story at a different budget wants a different shape.

    Action is the clearest case: Ensemble Convergence scores 0 on budget
    affinity at micro and 3 at studio, so it moves from last place to the
    front of the field.
    """
    action = GenreSelection(primary="action")
    micro = select(_envelope(kb, budget_tier_id="micro", genre=action), 5, kb)
    studio = select(_envelope(kb, budget_tier_id="studio", genre=action), 5, kb)

    micro_ids = [a.archetype_id for a in micro]
    studio_ids = [a.archetype_id for a in studio]
    assert micro_ids.index("ensemble_convergence") > studio_ids.index("ensemble_convergence")

    by_id = {a.archetype_id: a.score for a in micro} | {}
    studio_scores = {a.archetype_id: a.score for a in studio}
    assert studio_scores["ensemble_convergence"] > by_id["ensemble_convergence"]


def test_rationale_shows_the_arithmetic(kb: KnowledgeBase) -> None:
    """A reader who disagrees with a choice can check the sum."""
    assignment = select(_envelope(kb), 1, kb)[0]
    assert "Budget affinity" in assignment.rationale
    assert "genre affinity" in assignment.rationale
    assert f"total {assignment.score}" in assignment.rationale


# ------------------------------------------------------------------ boundaries


def test_requesting_more_archetypes_than_exist_is_rejected(kb: KnowledgeBase) -> None:
    """A short list would look like the diversity the caller asked for."""
    with pytest.raises(InsufficientArchetypesError) as exc:
        select(_envelope(kb), len(kb.archetypes) + 1, kb)
    assert exc.value.available == len(kb.archetypes)


@pytest.mark.parametrize("n", [0, -1])
def test_non_positive_counts_are_rejected(kb: KnowledgeBase, n: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        select(_envelope(kb), n, kb)


def test_requesting_every_archetype_returns_all_of_them(kb: KnowledgeBase) -> None:
    assignments = select(_envelope(kb), len(kb.archetypes), kb)
    assert {a.archetype_id for a in assignments} == {str(a["id"]) for a in kb.archetypes}


def test_unknown_budget_tier_is_rejected(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb).model_copy(update={"budget_tier_id": "colossal"})
    with pytest.raises(UnknownReferenceError) as exc:
        select(envelope, 1, kb)
    assert exc.value.kind == "budget tier"


def test_unknown_genre_is_rejected(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb).model_copy(update={"genre": GenreSelection(primary="westerns")})
    with pytest.raises(UnknownReferenceError) as exc:
        select(envelope, 1, kb)
    assert exc.value.kind == "genre"


def test_a_genre_with_no_recorded_affinity_scores_zero(kb: KnowledgeBase) -> None:
    """Silence in ``genre_affinity`` means no particular affinity, not an error.

    The knowledge base requires every *scored* genre to exist, not every genre
    to be scored, so a new genre must not break assignment before its affinity
    rows are curated.
    """
    import dataclasses

    stripped = tuple({**archetype, "genre_affinity": {}} for archetype in kb.archetypes)
    scoped = dataclasses.replace(kb, archetypes=stripped)
    assignments = select(_envelope(kb), 3, scoped)
    for assignment in assignments:
        tier = next(a for a in stripped if a["id"] == assignment.archetype_id)
        assert assignment.score == tier["budget_affinity"]["micro"]
