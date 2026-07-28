"""Layer 2: turning a resolved bundle into hard narrative bounds.

Where Layer 1 explains tensions, this decides the numbers the generator has to
work inside. The rule is uniform and has one direction: **the strictest
applicable value wins on every axis.** A concept that satisfies the tightest
board and the tightest budget satisfies all of them, and nothing downstream has
to re-derive that.

Content ceilings come from three places, and taking only the first would be the
easy mistake:

1. the target classification's own thresholds;
2. the equivalent classification in each selected territory's system, because a
   film released in India is judged by CBFC whatever the MPA rating says;
3. each territory's additional restrictions, where they bite.

That second source is why US plus India at PG-13 yields a CBFC-level ceiling
rather than an MPA one. It is not an extra restriction on top of PG-13; it is a
different board reading the same film.

Scope bounds come from the budget tier unchanged. They are already the
strictest thing that applies -- no territory restricts location count -- and
inventing pressure the knowledge base does not record would be fabrication.

Nothing here calls a language model. The prompt fragment is emitted as
key-value directives generated from the same fields the machine envelope
carries, so the text a model eventually sees cannot drift from the bounds it
was built from.
"""

from __future__ import annotations

import logging

from app.domain import (
    ContentDimension,
    ContentLevel,
    ContentThresholds,
    GenerationEnvelope,
    PromptDirective,
    RatingTarget,
    ResolvedBundle,
    ScopeEnvelope,
    ThresholdSource,
)
from app.engines.errors import UnknownReferenceError
from app.engines.territory import counterpart, effective_restrictions
from app.kb.loader import JsonObject, KnowledgeBase

logger = logging.getLogger(__name__)


def parameterize(resolved: ResolvedBundle, kb: KnowledgeBase) -> GenerationEnvelope:
    """Merge budget, rating and territory constraints into one envelope.

    Takes the :class:`~app.domain.ResolvedBundle` rather than a raw bundle
    because the writer's resolutions carry generator guidance that belongs in
    the envelope -- "violence must stay within the strictest selected
    territory's limit" is part of the brief, not a footnote to it.
    """
    bundle = resolved.bundle

    try:
        tier = kb.budget_tier(bundle.budget_tier_id)
    except KeyError as exc:
        raise UnknownReferenceError("budget tier", bundle.budget_tier_id) from exc

    scope = _scope_from(tier)
    levels, provenance = _ceilings(bundle.rating, bundle.territories.ids, kb)
    thresholds = ContentThresholds(**{d.value: levels[d] for d in ContentDimension})

    guidance = tuple(delta.guidance for delta in resolved.deltas if delta.guidance is not None)

    envelope = GenerationEnvelope(
        scope=scope,
        thresholds=thresholds,
        provenance=provenance,
        guidance=guidance,
        directives=_directives(scope, thresholds, guidance),
    )

    logger.info(
        "scope envelope built",
        extra={
            "kb_version": kb.version,
            "budget_tier": bundle.budget_tier_id,
            "territories": bundle.territories.count,
            "directives": len(envelope.directives),
        },
    )
    return envelope


def _scope_from(tier: JsonObject) -> ScopeEnvelope:
    scope: JsonObject = tier["scope"]
    return ScopeEnvelope(
        max_locations=scope["max_locations"],
        max_named_characters=scope["max_named_characters"],
        vfx_complexity=scope["vfx_complexity"],
        period_setting=scope["period_setting"],
        action_complexity=scope["action_complexity"],
        narrative_economy=scope["narrative_economy"],
    )


def _ceilings(
    rating: RatingTarget, territory_ids: tuple[str, ...], kb: KnowledgeBase
) -> tuple[dict[ContentDimension, ContentLevel], tuple[ThresholdSource, ...]]:
    """The strictest permitted level per dimension, and what imposed it."""
    try:
        target = kb.classification(rating.system, rating.classification)
    except KeyError as exc:
        raise UnknownReferenceError("classification", rating.qualified) from exc
    system = kb.rating_system(rating.system)

    levels: dict[ContentDimension, ContentLevel] = {}
    authorities: dict[ContentDimension, str] = {}
    details: dict[ContentDimension, str | None] = {}

    for dimension in ContentDimension:
        levels[dimension] = ContentLevel(target["thresholds"][dimension.value])
        authorities[dimension] = f"{system['label']} {target['label']}"
        details[dimension] = None

    for territory_id in territory_ids:
        try:
            territory = kb.territory(territory_id)
        except KeyError as exc:
            raise UnknownReferenceError("territory", territory_id) from exc

        board = counterpart(territory["rating_system"], rating, kb)
        if board is not None:
            board_system = kb.rating_system(territory["rating_system"])
            for dimension in ContentDimension:
                level = ContentLevel(board["thresholds"][dimension.value])
                if level < levels[dimension]:
                    levels[dimension] = level
                    authorities[dimension] = f"{board_system['label']} {board['label']}"
                    details[dimension] = (
                        f"{territory['label']} classifies this film under its own board."
                    )

        restrictions, notes = effective_restrictions(territory, rating, kb)
        for name, ceiling in restrictions.items():
            dimension = ContentDimension(name)
            if ContentLevel(ceiling) < levels[dimension]:
                levels[dimension] = ContentLevel(ceiling)
                authorities[dimension] = str(territory["regulator"])
                details[dimension] = str(notes[name]["description"])

    provenance = tuple(
        ThresholdSource(
            dimension=dimension,
            level=levels[dimension],
            authority=authorities[dimension],
            detail=details[dimension],
        )
        for dimension in ContentDimension
    )
    return levels, provenance


def _directives(
    scope: ScopeEnvelope, thresholds: ContentThresholds, guidance: tuple[str, ...]
) -> tuple[PromptDirective, ...]:
    """The structured prompt fragment.

    Ordering is fixed rather than dictionary order so the fragment is stable
    across runs: an unstable prompt would make generation irreproducible even
    with a deterministic envelope behind it.
    """
    directives = [
        PromptDirective(key="max_locations", value=_bound(scope.max_locations)),
        PromptDirective(key="max_named_characters", value=_bound(scope.max_named_characters)),
        PromptDirective(key="vfx_complexity", value=scope.vfx_complexity.value),
        PromptDirective(key="period_setting", value=scope.period_setting.value),
        PromptDirective(key="action_complexity", value=scope.action_complexity.value),
        PromptDirective(key="narrative_economy", value=scope.narrative_economy.value),
    ]
    directives.extend(
        PromptDirective(
            key=f"max_{dimension.value}",
            value=str(int(thresholds.level(dimension))),
        )
        for dimension in ContentDimension
    )
    directives.extend(PromptDirective(key="guidance", value=text) for text in guidance)
    return tuple(directives)


def _bound(value: int | None) -> str:
    """``unbounded`` rather than a large number, which would read as a real limit."""
    return "unbounded" if value is None else str(value)
