"""Building the generation prompt from structured fields only.

The system's claim is that constraints are decided deterministically and the
model fills a structure inside them. That claim survives only if the prompt
never invites the model to reopen a settled question. So this module renders
from computed values -- the envelope's directives, the archetype's blueprint,
the knowledge base's genre conventions -- and never from free prose written at
call time.

Two rules follow, and both are enforced by tests rather than convention:

*No deliberative phrasing.* A prompt that says "consider whether the budget
allows" invites the model to re-decide what Layer 2 already decided, and a
model that obliges will silently contradict the envelope. ``FORBIDDEN_PHRASES``
is checked against every rendered prompt.

*Scope bounds appear as numbered hard constraints.* Not as narrative context a
model may weigh, but as an enumerated list it can be held to. The verifier in
Stage 3.4 checks the output against the same numbers.

Templates live in ``app/prompts/`` as versioned files and ``PROMPT_VERSION`` is
recorded on every generation. A prompt change alters the output distribution,
so a variant that cannot name the prompt that produced it is not reproducible.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from app.domain import (
    ContentDimension,
    GenerationEnvelope,
)
from app.engines.errors import UnknownReferenceError
from app.kb.loader import JsonObject, KnowledgeBase

PROMPTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "prompts"

#: Phrasing that would hand a settled decision back to the model. Checked
#: against every rendered prompt by ``test_prompt_builder``. The list is
#: lowercase; matching is case-insensitive.
FORBIDDEN_PHRASES: Final[tuple[str, ...]] = (
    "if the budget allows",
    "if budget allows",
    "consider whether",
    "you may want to",
    "feel free to",
    "if you think",
    "decide whether",
    "at your discretion",
    "as appropriate",
    "if possible",
    "try to",
    "ideally",
    "preferably",
    "suggest a rating",
    "recommend a budget",
    "you could",
)


@lru_cache(maxsize=8)
def _template(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def prompt_version() -> str:
    """The version stamped onto every generation made with these templates."""
    return (PROMPTS_DIR / "VERSION").read_text(encoding="utf-8").strip()


def build(
    envelope: GenerationEnvelope,
    archetype_id: str,
    kb: KnowledgeBase,
) -> tuple[str, str]:
    """Return the ``(system, user)`` prompt pair for one variant.

    Raises :class:`~app.engines.errors.UnknownReferenceError` if the archetype
    or genre is not in the knowledge base.
    """
    try:
        archetype = kb.archetype(archetype_id)
    except KeyError as exc:
        raise UnknownReferenceError("archetype", archetype_id) from exc
    try:
        genre = kb.genre(envelope.genre.primary)
    except KeyError as exc:
        raise UnknownReferenceError("genre", envelope.genre.primary) from exc

    secondary: JsonObject | None = None
    if envelope.genre.secondary is not None:
        try:
            secondary = kb.genre(envelope.genre.secondary)
        except KeyError as exc:
            raise UnknownReferenceError("genre", envelope.genre.secondary) from exc

    user = _template("user_v1.md").format(
        archetype_label=archetype["label"],
        archetype_premise=archetype["premise"],
        beat_blueprint=_blueprint(archetype),
        genre_label=genre["label"],
        secondary_genre_line=(
            "" if secondary is None else f"Secondary modifier: {secondary['label']}"
        ),
        genre_conventions=_conventions(genre, secondary),
        numbered_constraints=_constraints(envelope),
        threshold_table=_thresholds(envelope),
        guidance_block=_guidance(envelope),
        output_contract=_contract(archetype),
    )
    return _template("system_v1.md"), user


def _blueprint(archetype: JsonObject) -> str:
    return "\n".join(
        f"{index}. {beat['function']} — {beat['description']}"
        for index, beat in enumerate(archetype["structural_blueprint"], start=1)
    )


def _conventions(genre: JsonObject, secondary: JsonObject | None) -> str:
    lines = [f"- {convention}" for convention in genre["conventions"]]
    if secondary is not None:
        lines.extend(
            f"- {convention} (from {secondary['label']})" for convention in secondary["conventions"]
        )
    return "\n".join(lines)


def _constraints(envelope: GenerationEnvelope) -> str:
    """Scope bounds as an enumerated list of hard limits.

    Numbered because the verifier checks against these same values, and an
    unnumbered paragraph is something a model weighs rather than obeys.
    """
    scope = envelope.scope
    items = [
        _bound_line("distinct shooting locations", scope.max_locations),
        _bound_line("named speaking characters", scope.max_named_characters),
        f"Visual effects may not exceed: {scope.vfx_complexity.value}.",
        f"Period setting is restricted to: {scope.period_setting.value}.",
        f"Staged action may not exceed: {scope.action_complexity.value}.",
        f"Narrative economy required: {scope.narrative_economy.value}. "
        "Every scene must earn its place at this level.",
    ]
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _bound_line(noun: str, limit: int | None) -> str:
    if limit is None:
        return (
            f"There is no budget ceiling on {noun}; stay within what the genre conventionally uses."
        )
    return f"Use at most {limit} {noun}. This is a hard maximum."


def _thresholds(envelope: GenerationEnvelope) -> str:
    """Ceilings with the authority that set each one.

    Naming the board matters: a model told "violence: 1" with no reason has
    less to work with than one told the limit comes from a specific regulator.
    """
    by_dimension = {source.dimension: source for source in envelope.provenance}
    lines = []
    for dimension in ContentDimension:
        level = int(envelope.thresholds.level(dimension))
        source = by_dimension.get(dimension)
        authority = f" (set by {source.authority})" if source is not None else ""
        lines.append(f"- {dimension.value}: maximum level {level}{authority}")
    return "\n".join(lines)


def _guidance(envelope: GenerationEnvelope) -> str:
    if not envelope.guidance:
        return "None."
    return "\n".join(f"- {text}" for text in envelope.guidance)


def variant_schema(archetype: JsonObject) -> dict[str, Any]:
    """The JSON schema the model is constrained to.

    ``min_beats`` comes from the archetype rather than a constant, because the
    structures genuinely differ: Transformation Arc needs six beats where the
    others need five, and a shared floor would under-specify it.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "logline", "beats", "satisfaction", "relaxations"],
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "logline": {"type": "string", "minLength": 1},
            "beats": {
                "type": "array",
                "minItems": int(archetype["min_beats"]),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["function", "summary"],
                    "properties": {
                        "function": {"type": "string", "minLength": 1},
                        "summary": {"type": "string", "minLength": 1},
                    },
                },
            },
            "satisfaction": {
                "type": "object",
                "additionalProperties": False,
                "required": [dimension.value for dimension in ContentDimension],
                "properties": {
                    dimension.value: {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["level", "statement"],
                        "properties": {
                            "level": {"type": "integer", "minimum": 0, "maximum": 4},
                            "statement": {"type": "string", "minLength": 1},
                        },
                    }
                    for dimension in ContentDimension
                },
            },
            "relaxations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "locations": {"type": "array", "items": {"type": "string"}},
            "named_characters": {"type": "array", "items": {"type": "string"}},
        },
    }


def _contract(archetype: JsonObject) -> str:
    """The output contract, rendered from the schema so the two cannot diverge."""
    minimum = int(archetype["min_beats"])
    dimensions = ", ".join(dimension.value for dimension in ContentDimension)
    return (
        f"{json.dumps(variant_schema(archetype), indent=2)}\n\n"
        f"`beats` must contain at least {minimum} entries, one per blueprint "
        f"function, in the order given.\n"
        f"`satisfaction` must state, for each of {dimensions}, the level the "
        f"concept actually reaches and one sentence naming what keeps it there.\n"
        "`relaxations` lists any genre convention you set aside to stay inside a "
        "ceiling; use an empty array if none.\n"
        "`locations` and `named_characters` must enumerate every distinct "
        "location and every named speaking role the concept requires, so the "
        "counts can be checked against the limits above."
    )
