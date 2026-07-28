"""Reading a target classification through a territory's own board.

Shared by conflict detection and scope parameterisation, which must agree: a
detector that flags a territory conflict and a parameteriser that then ignores
the same restriction would produce variants the detector had already refused.

The mapping is deliberately partial. ``rating_systems.json`` carries
equivalences with a confidence, not an identity, because boards apply different
criteria -- CBFC has no counterpart to MPA PG, and pretending otherwise would
manufacture a ceiling the data does not support. Callers get ``None`` and
decide what to do with the uncertainty.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain import RatingTarget
from app.kb.loader import JsonObject, KnowledgeBase


def counterpart(system_id: str, rating: RatingTarget, kb: KnowledgeBase) -> JsonObject | None:
    """The classification in ``system_id`` corresponding to ``rating``.

    Returns the target itself when the systems match, the equivalent
    classification when the equivalence table relates them, and ``None`` when
    it does not.
    """
    if system_id == rating.system:
        return kb.classification(rating.system, rating.classification)

    for equivalence in kb.rating_equivalences:
        qualified: Sequence[str] = equivalence["classifications"]
        if rating.qualified not in qualified:
            continue
        for entry in qualified:
            entry_system, _, entry_classification = entry.partition(".")
            if entry_system == system_id:
                return kb.classification(entry_system, entry_classification)
    return None


def effective_restrictions(
    territory: JsonObject, rating: RatingTarget, kb: KnowledgeBase
) -> tuple[Mapping[str, int], Mapping[str, JsonObject]]:
    """The territory's extra ceilings that actually bite, plus the rule behind each.

    ``applies_from_classification`` names the classification at or below which
    a restriction applies; ``null`` means everywhere. Honouring it is what
    stops a U-rated family film being blocked by the UK drug-instruction rule,
    which governs BBFC 15 and above.

    When the target cannot be mapped into this territory's system the
    restriction is applied. An unnecessary conflict arrives with an
    explanation and resolutions; a missed one arrives as a refused
    certificate.
    """
    position = counterpart(territory["rating_system"], rating, kb)
    order = None if position is None else int(position["order"])

    ceilings: dict[str, int] = {}
    notes: dict[str, JsonObject] = {}
    for restriction in territory.get("additional_restrictions", []):
        if not _applies(restriction, territory["rating_system"], order, kb):
            continue
        dimension = restriction["dimension"]
        level = int(restriction["max_level"])
        # Several restrictions may govern one dimension; the tighter wins.
        if dimension not in ceilings or level < ceilings[dimension]:
            ceilings[dimension] = level
            notes[dimension] = restriction
    return ceilings, notes


def _applies(restriction: JsonObject, system_id: str, order: int | None, kb: KnowledgeBase) -> bool:
    threshold_id = restriction.get("applies_from_classification")
    if threshold_id is None:
        return True
    if order is None:
        return True
    return order <= int(kb.classification(system_id, threshold_id)["order"])
