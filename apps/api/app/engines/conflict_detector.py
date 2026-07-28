"""Layer 1: deterministic conflict detection.

This is the research contribution in executable form. Every tension between a
writer's constraints is found by evaluating declarative rules from the
knowledge base against the bundle -- no language model is consulted, and the
same bundle against the same knowledge base always produces byte-identical
output. A conflict report is therefore a fact about the inputs, not an opinion
about them, and it can be replayed and audited months later.

The evaluation has three parts:

*Context.* The bundle names knowledge base rows by id; :func:`_build_context`
resolves them into the dotted namespace the rule paths address --
``genre.content_demands.violence``, ``budget.scope.max_locations``,
``territories.*.restrictions.violence``. This is also where a territory's
additional restrictions are filtered by whether they actually bite at the
target classification, which is the difference between a real HARD conflict and
one that blocks a writer for no reason.

*Predicates.* Exactly the vocabulary the schema defines and nothing more:
``dimension_exceeds``, ``scope_exceeds``, ``ordinal_exceeds``, ``equals``,
``not_equals``, ``includes``, ``count_gte``, and the ``all_of`` / ``any_of`` /
``none_of`` combinators. Adding a predicate type here without adding it to
``conflict_rule.schema.json`` would let a rule exist that the schema says is
invalid, so the vocabulary is closed on purpose.

*Rendering.* The knowledge base stores explanation templates; the detector
substitutes the values that actually fired the rule, so the writer reads "level
3 against a ceiling of 2" rather than a generic warning. A template that names
a value the match cannot supply raises instead of rendering an empty gap.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from app.domain import (
    ActionComplexity,
    Conflict,
    ConflictReport,
    ConstraintBundle,
    OrdinalVocabulary,
    PeriodSetting,
    ResolutionEffect,
    ResolutionOption,
    Severity,
    VfxComplexity,
)
from app.engines.errors import ConflictDetectionError, UnknownReferenceError
from app.engines.territory import effective_restrictions
from app.kb.loader import JsonObject, KnowledgeBase

logger = logging.getLogger(__name__)

#: Report order. HARD first because it is the only tier that stops the writer.
SEVERITY_ORDER: Final[Mapping[str, int]] = {
    Severity.HARD.value: 0,
    Severity.SOFT.value: 1,
    Severity.ADVISORY.value: 2,
}

#: Which ordinal vocabulary governs a field, keyed by the final path segment.
#: ``ordinal_exceeds`` compares declaration position, so it needs to know which
#: list the position is in.
ORDINAL_FIELDS: Final[Mapping[str, type[OrdinalVocabulary]]] = {
    "vfx_complexity": VfxComplexity,
    "period_setting": PeriodSetting,
    "action_complexity": ActionComplexity,
}

#: Placeholders the renderer knows how to fill. A template using anything else
#: is a knowledge base authoring error, and ``test_conflict_detector`` asserts
#: the shipped rule set stays inside this set.
RENDERABLE: Final[frozenset[str]] = frozenset(
    {
        "genre",
        "secondary_genre",
        "rating",
        "rating_system",
        "left",
        "right",
        "territory",
        "territory_restriction",
        "rating_criterion",
    }
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One value a path resolved to, with the territory that produced it.

    A wildcard path yields one candidate per territory. Carrying the territory
    alongside the value is what lets the explanation name *which* territory
    imposed the binding restriction instead of reporting an anonymous number.
    """

    value: Any
    territory: JsonObject | None = None


@dataclass(slots=True)
class _Bindings:
    """Values collected while a predicate evaluated, used to render its template.

    ``left`` and ``right`` are overwritten as comparisons are evaluated, so a
    combinator's last contributing comparison supplies them. That is what the
    shipped templates expect: ``germany_violence_glorification_bar`` combines a
    territory membership test with a violence-level test, and the sentence it
    renders is about the violence level.
    """

    left: Any = None
    right: Any = None
    territory: JsonObject | None = None
    dimension: str | None = None
    values: dict[str, str] = field(default_factory=dict)


def detect(bundle: ConstraintBundle, kb: KnowledgeBase) -> ConflictReport:
    """Evaluate every conflict rule against ``bundle``.

    Pure with respect to its arguments: no I/O beyond a structured log line,
    and no dependence on clock, randomness or process state. Two calls with
    equal inputs produce equal reports.

    Raises :class:`~app.engines.errors.UnknownReferenceError` if the bundle
    names a row the knowledge base does not have, and
    :class:`~app.engines.errors.ConflictDetectionError` if a rule cannot be
    evaluated or rendered.
    """
    context = _build_context(bundle, kb)

    found: list[Conflict] = []
    for rule in kb.conflict_rules:
        bindings = _Bindings()
        if _evaluate(rule["predicate"], context, bindings):
            found.append(_build_conflict(rule, context, bindings))

    conflicts = tuple(sorted(found, key=lambda c: (SEVERITY_ORDER[c.severity.value], c.rule_id)))

    logger.info(
        "conflict detection complete",
        extra={
            "kb_version": kb.version,
            "rules_evaluated": len(kb.conflict_rules),
            "conflicts_found": len(conflicts),
            "hard": sum(1 for c in conflicts if c.severity is Severity.HARD),
            "soft": sum(1 for c in conflicts if c.severity is Severity.SOFT),
            "advisory": sum(1 for c in conflicts if c.severity is Severity.ADVISORY),
        },
    )

    return ConflictReport(
        bundle=bundle,
        kb_version=kb.version,
        conflicts=conflicts,
        rules_evaluated=len(kb.conflict_rules),
    )


# ------------------------------------------------------------------ context


def _build_context(bundle: ConstraintBundle, kb: KnowledgeBase) -> JsonObject:
    """Resolve the bundle's identifiers into the namespace rule paths address."""
    genre = _require(kb.genre, bundle.genre.primary, "genre")
    budget = _require(kb.budget_tier, bundle.budget_tier_id, "budget tier")
    system = _require(kb.rating_system, bundle.rating.system, "rating system")

    try:
        classification = kb.classification(bundle.rating.system, bundle.rating.classification)
    except KeyError as exc:
        raise UnknownReferenceError("classification", bundle.rating.qualified) from exc
    # The board's name travels with the classification so an explanation can
    # say "CBFC U/A" rather than a bare "U/A", which means nothing on its own.
    classification = {**classification, "system_label": system["label"]}

    secondary: JsonObject | None = None
    if bundle.genre.secondary is not None:
        secondary = _require(kb.genre, bundle.genre.secondary, "genre")

    territories = [
        _territory_context(_require(kb.territory, territory_id, "territory"), bundle, kb)
        for territory_id in bundle.territories.ids
    ]

    return {
        "genre": genre,
        "secondary_genre": secondary,
        "rating": classification,
        "budget": budget,
        "audience": {"min_age": bundle.audience.min_age, "max_age": bundle.audience.max_age},
        "territories": {
            "count": bundle.territories.count,
            "ids": list(bundle.territories.ids),
            "items": territories,
        },
    }


def _require(lookup: Any, identifier: str, kind: str) -> JsonObject:
    try:
        row: JsonObject = lookup(identifier)
    except KeyError as exc:
        raise UnknownReferenceError(kind, identifier) from exc
    return row


def _territory_context(
    territory: JsonObject, bundle: ConstraintBundle, kb: KnowledgeBase
) -> JsonObject:
    """Attach the restrictions that actually bite at the target classification.

    Delegates to :mod:`app.engines.territory` so that detection and scope
    parameterisation read a territory the same way. If they disagreed, the
    parameteriser could hand the generator an envelope the detector had
    already refused.
    """
    restrictions, notes = effective_restrictions(territory, bundle.rating, kb)
    return {**territory, "restrictions": restrictions, "restriction_notes": notes}


# ------------------------------------------------------------------ resolution


def _resolve(path: str, context: JsonObject) -> tuple[_Candidate, ...]:
    """Walk a dotted path, expanding ``*`` across territories.

    Returns every candidate the path reaches, which is zero when the path does
    not exist for this bundle -- an absent secondary genre, a territory with no
    restriction on the dimension in question, or a ``null`` bound like the
    studio tier's ``max_locations``. Callers treat "no candidates" as "this
    rule does not apply", so an unset optional and an unbounded ceiling both
    fail to fire rather than raising. That is the correct reading of both: a
    ceiling that does not exist cannot be exceeded.
    """
    candidates: tuple[_Candidate, ...] = (_Candidate(context),)
    for segment in path.split("."):
        expanded: list[_Candidate] = []
        for candidate in candidates:
            container = candidate.value
            if segment == "*":
                if isinstance(container, Mapping):
                    expanded.extend(
                        _Candidate(item, territory=item) for item in container.get("items", [])
                    )
                continue
            if isinstance(container, Mapping) and container.get(segment) is not None:
                expanded.append(_Candidate(container[segment], territory=candidate.territory))
        candidates = tuple(expanded)
    return candidates


def _operand(reference: JsonObject, context: JsonObject) -> tuple[_Candidate, ...]:
    if "literal" in reference:
        return (_Candidate(reference["literal"]),)
    return _resolve(reference["path"], context)


def _dimension_of(reference: JsonObject) -> str | None:
    """Final path segment, used to pick an ordinal vocabulary and a criterion."""
    if "path" not in reference:
        return None
    tail: str = reference["path"].rsplit(".", 1)[-1]
    return tail


# ------------------------------------------------------------------ predicates


def _evaluate(predicate: JsonObject, context: JsonObject, bindings: _Bindings) -> bool:
    kind = predicate["type"]
    if kind == "all_of":
        return all(_evaluate(operand, context, bindings) for operand in predicate["operands"])
    if kind == "any_of":
        return any(_evaluate(operand, context, bindings) for operand in predicate["operands"])
    if kind == "none_of":
        return not any(_evaluate(operand, context, bindings) for operand in predicate["operands"])
    return _compare(predicate, context, bindings)


def _compare(predicate: JsonObject, context: JsonObject, bindings: _Bindings) -> bool:
    kind = predicate["type"]
    lefts = _operand(predicate["left"], context)
    rights = _operand(predicate["right"], context)
    if not lefts or not rights:
        return False

    if kind in ("equals", "not_equals", "includes", "count_gte"):
        return _compare_scalar(kind, lefts[0], rights[0], predicate, bindings)
    if kind in ("dimension_exceeds", "scope_exceeds", "ordinal_exceeds"):
        return _compare_ordered(kind, lefts, rights, predicate, bindings)
    raise ConflictDetectionError(f"unknown predicate type '{kind}'")


def _compare_scalar(
    kind: str,
    left: _Candidate,
    right: _Candidate,
    predicate: JsonObject,
    bindings: _Bindings,
) -> bool:
    if kind == "equals":
        outcome = bool(left.value == right.value)
    elif kind == "not_equals":
        outcome = bool(left.value != right.value)
    elif kind == "includes":
        container = left.value
        if not isinstance(container, Sequence) or isinstance(container, str):
            raise ConflictDetectionError(
                f"'includes' needs a collection on the left, got {type(container).__name__}"
            )
        outcome = bool(right.value in container)
    else:  # count_gte
        outcome = _number(left.value, predicate) >= _number(right.value, predicate)

    if outcome:
        _bind(left, right, predicate, bindings)
    return outcome


def _compare_ordered(
    kind: str,
    lefts: tuple[_Candidate, ...],
    rights: tuple[_Candidate, ...],
    predicate: JsonObject,
    bindings: _Bindings,
) -> bool:
    """Compare demand against permission, reducing wildcards to the tightest bound.

    A wildcard on the right means several territories each impose a ceiling;
    the binding one is the lowest, because a production must satisfy all of
    them. Ties resolve by territory id so the chosen territory -- and therefore
    the rendered explanation -- does not depend on the order the writer happened
    to list them in.
    """
    if kind == "ordinal_exceeds":
        vocabulary = _vocabulary_for(predicate)
        left = max(lefts, key=lambda c: vocabulary(c.value).rank)
        right = min(rights, key=lambda c: (vocabulary(c.value).rank, _territory_id(c)))
        outcome = vocabulary(left.value).rank > vocabulary(right.value).rank
    else:
        left = max(lefts, key=lambda c: _number(c.value, predicate))
        right = min(rights, key=lambda c: (_number(c.value, predicate), _territory_id(c)))
        outcome = _number(left.value, predicate) > _number(right.value, predicate)

    if outcome:
        _bind(left, right, predicate, bindings)
    return outcome


def _vocabulary_for(predicate: JsonObject) -> type[OrdinalVocabulary]:
    for side in ("left", "right"):
        name = _dimension_of(predicate[side])
        if name is not None and name in ORDINAL_FIELDS:
            return ORDINAL_FIELDS[name]
    raise ConflictDetectionError(
        f"'ordinal_exceeds' on a field with no declared order: {predicate}"
    )


def _number(value: Any, predicate: JsonObject) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConflictDetectionError(
            f"'{predicate['type']}' needs a number, got {value!r} ({type(value).__name__})"
        )
    return int(value)


def _territory_id(candidate: _Candidate) -> str:
    return "" if candidate.territory is None else str(candidate.territory["id"])


def _bind(left: _Candidate, right: _Candidate, predicate: JsonObject, bindings: _Bindings) -> None:
    bindings.left = left.value
    bindings.right = right.value
    bindings.territory = right.territory or left.territory
    for side in ("left", "right"):
        name = _dimension_of(predicate[side])
        if name is not None:
            bindings.dimension = name


# ------------------------------------------------------------------ rendering


def _build_conflict(rule: JsonObject, context: JsonObject, bindings: _Bindings) -> Conflict:
    return Conflict(
        rule_id=rule["id"],
        severity=Severity(rule["severity"]),
        title=rule["title"],
        explanation=_render(rule, context, bindings),
        hard_rationale=rule.get("hard_rationale"),
        resolutions=tuple(_option(resolution) for resolution in rule["resolutions"]),
        evidence=_evidence(bindings),
    )


def _option(resolution: JsonObject) -> ResolutionOption:
    effect = resolution.get("effect")
    return ResolutionOption(
        id=resolution["id"],
        label=resolution["label"],
        description=resolution["description"],
        effect=(
            None
            if effect is None
            else ResolutionEffect(
                kind=effect["kind"],
                dimension=effect.get("dimension"),
                guidance=effect.get("guidance"),
            )
        ),
    )


def _evidence(bindings: _Bindings) -> Mapping[str, str]:
    evidence: dict[str, str] = {}
    if bindings.left is not None:
        evidence["left"] = _format(bindings.left)
    if bindings.right is not None:
        evidence["right"] = _format(bindings.right)
    if bindings.dimension is not None:
        evidence["dimension"] = bindings.dimension
    if bindings.territory is not None:
        evidence["territory"] = str(bindings.territory["id"])
    return evidence


def _render(rule: JsonObject, context: JsonObject, bindings: _Bindings) -> str:
    template: str = rule["explanation_template"]
    substitutions = _substitutions(context, bindings)
    try:
        return template.format_map(substitutions)
    except KeyError as exc:
        raise ConflictDetectionError(
            f"rule '{rule['id']}' renders {exc} but the match did not supply it"
        ) from exc


def _substitutions(context: JsonObject, bindings: _Bindings) -> Mapping[str, str]:
    """Build the substitution map, omitting anything the match did not bind.

    Omission rather than a blank default: ``format_map`` then raises for a
    template that needs a value this match cannot supply, which surfaces the
    authoring error instead of rendering a sentence with a hole in it.
    """
    values: dict[str, str] = {"genre": str(context["genre"]["label"])}

    secondary = context["secondary_genre"]
    if secondary is not None:
        values["secondary_genre"] = str(secondary["label"])

    values["rating"] = str(context["rating"]["label"])
    # Always present: _build_context attaches it to every classification.
    values["rating_system"] = str(context["rating"]["system_label"])

    if bindings.left is not None:
        values["left"] = _format(bindings.left)
    if bindings.right is not None:
        values["right"] = _format(bindings.right)

    if bindings.territory is not None:
        values["territory"] = str(bindings.territory["label"])
        note = bindings.territory.get("restriction_notes", {}).get(bindings.dimension)
        if note is not None:
            values["territory_restriction"] = str(note["description"])

    criterion = context["rating"].get("criteria", {}).get(bindings.dimension)
    if criterion is not None:
        values["rating_criterion"] = str(criterion)

    return values


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value)
    return str(value)
