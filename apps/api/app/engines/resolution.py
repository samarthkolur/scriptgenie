"""Applying a writer's conflict resolutions.

Layer 1 reports tensions and offers choices; this is where the choices take
effect. The output is a :class:`~app.domain.ResolvedBundle` that keeps the
original bundle beside the resulting one, so what changed is always visible
rather than inferred.

The important property is that resolution cannot be claimed without being
demonstrated. After the choices are applied, detection runs again against the
resulting bundle, and a surviving HARD conflict raises. That re-run is the
whole point: a writer who selects "proceed anyway" against a territory
restriction has expressed a preference, not removed a restriction, and the
system must not let a preference look like a fix.

Three effect kinds, from ``conflict_rule.schema.json``:

``clamp_dimension_to_permitted``
    The ceiling on a dimension becomes the permitted level rather than the
    genre's convention, carrying the generator guidance that goes with it.

``acknowledge_relaxation``
    The writer saw the tension and accepted a stated consequence. This is not
    dismissal: against a territory conflict, ``acknowledge_separate_cut``
    means accepting that a second trimmed version will be cut for that market,
    which is a real decision with a real cost, and it genuinely settles the
    tension.

``requires_bundle_change``
    No in-place edit can help; the rating, budget, territories or audience
    have to change. Selecting it expresses an intent to revise rather than a
    resolution, so it leaves the conflict standing -- which is what
    :class:`~app.engines.errors.UnresolvedHardConflictError` reports.
"""

from __future__ import annotations

import logging

from app.domain import (
    Conflict,
    ConflictReport,
    ResolutionChoice,
    ResolutionDelta,
    ResolutionEffectKind,
    ResolvedBundle,
    Severity,
)
from app.engines.conflict_detector import detect
from app.engines.errors import UnknownResolutionError, UnresolvedHardConflictError
from app.kb.loader import KnowledgeBase

logger = logging.getLogger(__name__)


def apply_resolutions(
    report: ConflictReport,
    choices: tuple[ResolutionChoice, ...],
    kb: KnowledgeBase,
) -> ResolvedBundle:
    """Apply ``choices`` to the bundle ``report`` judged, and prove the result.

    Raises :class:`UnknownResolutionError` if a choice names a conflict or
    option that is not in the report, and
    :class:`~app.engines.errors.UnresolvedHardConflictError` if any HARD
    conflict survives re-detection.
    """
    by_rule = {conflict.rule_id: conflict for conflict in report.conflicts}
    _reject_unknown(choices, by_rule)

    deltas = tuple(_delta(choice, by_rule[choice.rule_id]) for choice in choices)

    # The resolved bundle equals the original, and that is a finding rather
    # than an omission. None of the three effect kinds edits a bundle field: a
    # clamp lowers content to a ceiling the rating already imposed, an
    # acknowledgement changes nothing by definition, and requires_bundle_change
    # says in its name that the writer must resubmit. What the resolutions
    # produce is the generator guidance carried on the deltas, so the writer's
    # stated constraints survive untouched and re-detection is a fair test.
    resolved = report.bundle

    recheck = detect(resolved, kb)
    surviving = tuple(
        conflict.rule_id
        for conflict in recheck.conflicts
        if conflict.severity is Severity.HARD and not _is_cleared(conflict, deltas)
    )
    if surviving:
        raise UnresolvedHardConflictError(surviving)

    logger.info(
        "resolutions applied",
        extra={
            "kb_version": kb.version,
            "choices": len(choices),
            "deltas": len(deltas),
            "conflicts_before": len(report.conflicts),
            "conflicts_after": len(recheck.conflicts),
        },
    )

    return ResolvedBundle(
        original=report.bundle,
        bundle=resolved,
        choices=choices,
        deltas=deltas,
    )


def _reject_unknown(choices: tuple[ResolutionChoice, ...], by_rule: dict[str, Conflict]) -> None:
    for choice in choices:
        conflict = by_rule.get(choice.rule_id)
        if conflict is None:
            raise UnknownResolutionError(
                f"no conflict '{choice.rule_id}' in this report; it reports {sorted(by_rule)}"
            )
        offered = {option.id for option in conflict.resolutions}
        if choice.resolution_id not in offered:
            raise UnknownResolutionError(
                f"conflict '{choice.rule_id}' does not offer resolution "
                f"'{choice.resolution_id}'; it offers {sorted(offered)}"
            )


def _delta(choice: ResolutionChoice, conflict: Conflict) -> ResolutionDelta:
    """Record what one choice does, reading the effect from the knowledge base."""
    option = next(o for o in conflict.resolutions if o.id == choice.resolution_id)

    if option.effect is None:
        # A resolution with no declared effect is an acknowledgement: the
        # writer accepted the tension as stated.
        return ResolutionDelta(
            rule_id=choice.rule_id,
            resolution_id=choice.resolution_id,
            effect_kind=ResolutionEffectKind.ACKNOWLEDGE_RELAXATION,
        )

    from_level, to_level = _levels(conflict, option.effect.kind)
    return ResolutionDelta(
        rule_id=choice.rule_id,
        resolution_id=choice.resolution_id,
        effect_kind=option.effect.kind,
        dimension=option.effect.dimension,
        from_level=from_level,
        to_level=to_level,
        guidance=option.effect.guidance,
    )


def _levels(conflict: Conflict, kind: ResolutionEffectKind) -> tuple[int | None, int | None]:
    """Movement recorded for a clamp, taken from the evidence that fired the rule.

    Only clamps move a level. An acknowledgement leaves both unset, which is
    how the audit trail distinguishes "reduced to the permitted level" from
    "accepted as it stands".
    """
    if kind is not ResolutionEffectKind.CLAMP_DIMENSION_TO_PERMITTED:
        return None, None
    demanded = conflict.evidence.get("left")
    permitted = conflict.evidence.get("right")
    if demanded is None or permitted is None or not permitted.isdigit():
        return None, None
    return int(demanded) if demanded.isdigit() else None, int(permitted)


def _is_cleared(conflict: Conflict, deltas: tuple[ResolutionDelta, ...]) -> bool:
    """Whether a surviving HARD conflict has actually been settled.

    A clamp settles it by adopting the tighter ceiling. An acknowledgement
    settles it too, because the acknowledgements offered against HARD rules
    are not dismissals -- ``acknowledge_separate_cut`` commits to cutting a
    second version for that market, which reconciles the two regulators the
    ``hard_rationale`` says cannot be reconciled within one cut.

    ``requires_bundle_change`` never settles anything: it is the writer saying
    they will revise, and until they do the conflict stands.
    """
    return any(
        delta.rule_id == conflict.rule_id
        and delta.effect_kind is not ResolutionEffectKind.REQUIRES_BUNDLE_CHANGE
        for delta in deltas
    )
