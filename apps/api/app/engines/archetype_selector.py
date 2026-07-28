"""Assigning structural containers, so variant diversity is architectural.

The research finding this implements is negative: sampling a model repeatedly
does not produce structurally different stories. Ask for five variants and you
get one shape told five ways. Diversity has to be imposed before generation,
not hoped for during it, which is what assigning each variant a distinct
narrative archetype does.

Scoring is exactly what the knowledge base records -- ``budget_affinity`` plus
``genre_affinity`` -- and nothing else. Location pressure is tempting as a
third term, since ``ensemble_convergence`` is marked ``high`` and a micro
budget allows three locations, but the budget affinity already encodes that
judgement (ensemble scores 0 at micro), and adding a second penalty for the
same fact would double-count it.

Ordering is deterministic, and the seed does not change that. Archetypes rank
by score; the seed only permutes archetypes whose scores are *equal*, so a
caller can ask for a different-but-equally-valid assignment without any run
becoming unreproducible. Same envelope and same seed always give the same
answer.
"""

from __future__ import annotations

import logging
import random

from app.domain import ArchetypeAssignment, GenerationEnvelope
from app.engines.errors import EngineError, UnknownReferenceError
from app.kb.loader import JsonObject, KnowledgeBase

logger = logging.getLogger(__name__)


class InsufficientArchetypesError(EngineError):
    """More distinct archetypes were requested than the knowledge base holds.

    Raised rather than returning a short list, because a caller that asked for
    five structurally distinct variants and silently received three would
    believe it had the diversity it asked for.
    """

    def __init__(self, requested: int, available: int) -> None:
        self.requested = requested
        self.available = available
        super().__init__(
            f"{requested} distinct archetypes requested but the knowledge base has {available}"
        )


def select(
    envelope: GenerationEnvelope,
    n: int,
    kb: KnowledgeBase,
    *,
    seed: int = 0,
) -> tuple[ArchetypeAssignment, ...]:
    """Assign ``n`` distinct archetypes, best fit first.

    Raises :class:`InsufficientArchetypesError` if ``n`` exceeds the number of
    archetypes available, and :class:`~app.engines.errors.UnknownReferenceError`
    if the envelope names a budget tier or genre the knowledge base lacks.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if n > len(kb.archetypes):
        raise InsufficientArchetypesError(n, len(kb.archetypes))

    _require_known(envelope, kb)

    ranked = _rank(envelope, kb, seed)
    assignments = tuple(
        ArchetypeAssignment(
            variant_index=index,
            archetype_id=str(archetype["id"]),
            score=score,
            rationale=_rationale(envelope, archetype, score),
        )
        for index, (score, archetype) in enumerate(ranked[:n])
    )

    logger.info(
        "archetypes assigned",
        extra={
            "kb_version": kb.version,
            "requested": n,
            "budget_tier": envelope.budget_tier_id,
            "genre": envelope.genre.primary,
            "seed": seed,
            "assigned": [a.archetype_id for a in assignments],
        },
    )
    return assignments


def _require_known(envelope: GenerationEnvelope, kb: KnowledgeBase) -> None:
    try:
        kb.budget_tier(envelope.budget_tier_id)
    except KeyError as exc:
        raise UnknownReferenceError("budget tier", envelope.budget_tier_id) from exc
    try:
        kb.genre(envelope.genre.primary)
    except KeyError as exc:
        raise UnknownReferenceError("genre", envelope.genre.primary) from exc


def _rank(
    envelope: GenerationEnvelope, kb: KnowledgeBase, seed: int
) -> list[tuple[int, JsonObject]]:
    """Rank every archetype, best first.

    The documented tie-break order, applied in sequence:

    1. total score, descending;
    2. a permutation of the equal-scoring group, drawn from ``seed``;
    3. archetype id ascending, which is what step 2 permutes and therefore the
       order at any seed that leaves the group unchanged.

    Step 2 sits inside the score groups rather than across them, so the seed
    can never promote a worse-fitting archetype above a better one.
    """
    scored = [(_score(envelope, archetype), archetype) for archetype in kb.archetypes]
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]["id"])))

    # Suppression justified: this must be reproducible, which is the opposite
    # of what a cryptographic generator provides. The seed is the caller's
    # handle on which of several equally-good assignments they get back.
    rng = random.Random(seed)  # noqa: S311
    ordered: list[tuple[int, JsonObject]] = []
    index = 0
    while index < len(scored):
        end = index
        while end < len(scored) and scored[end][0] == scored[index][0]:
            end += 1
        group = scored[index:end]
        rng.shuffle(group)
        ordered.extend(group)
        index = end
    return ordered


def _score(envelope: GenerationEnvelope, archetype: JsonObject) -> int:
    """Budget affinity plus genre affinity, both from the knowledge base.

    A genre absent from ``genre_affinity`` scores zero rather than raising: the
    knowledge base's integrity check requires every scored genre to exist, not
    every genre to be scored, so silence means "no particular affinity".
    """
    budget = int(archetype["budget_affinity"][envelope.budget_tier_id])
    genre = int(archetype["genre_affinity"].get(envelope.genre.primary, 0))
    return budget + genre


def _rationale(envelope: GenerationEnvelope, archetype: JsonObject, score: int) -> str:
    """Why this archetype, in the arithmetic that chose it.

    Selection is deterministic, so a reader who disagrees can check the sum
    rather than being asked to trust the ranking.
    """
    budget = int(archetype["budget_affinity"][envelope.budget_tier_id])
    genre = int(archetype["genre_affinity"].get(envelope.genre.primary, 0))
    return (
        f"Budget affinity {budget} for {envelope.budget_tier_id}, "
        f"genre affinity {genre} for {envelope.genre.primary}, total {score}."
    )
