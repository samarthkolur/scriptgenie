"""Layer 3: checking a generated variant against the envelope it was built for.

The model was told the constraints and asserts in its own output that it
honoured them. This module does not take its word for it. A system that
reported the model's self-assessment would be reporting a claim, and the whole
point is to report a check.

Two passes, and the difference between them matters:

*Structural.* Location and character counts come from the enumerations the
output contract requires, compared against the envelope's numbers. This is
arithmetic and it is decisive.

*Signal.* Content intensity is read from the prose by keyword, which is a
heuristic and is treated as one. A keyword pass can miss implication and can
fire on a quoted word, so it never produces a PASS on its own — it can only
raise a concern for a human, which is what ``NEEDS_REVIEW`` means.

An optional structured extraction call can supply the same signals from the
model itself. When it is unavailable or fails, the dimension degrades to
``NEEDS_REVIEW``. It never degrades to ``PASS``: a check that did not run is
not a check that succeeded, and treating it as one is precisely how "verified"
becomes a word with no content.

Per the research analysis (Risk 2), the language is **"CASIE-verified for
scope"** and never "certified compliant". Classification is the business of
CARA, BBFC, CBFC and FSK, not of this software.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Final

from app.domain import (
    ConstraintSatisfactionReport,
    ContentDimension,
    ContentLevel,
    DimensionCheck,
    GenerationEnvelope,
    PlotVariant,
    ScopeCheck,
    VerificationResult,
)
from app.services.errors import LLMError
from app.services.generation_service import GeneratedVariant
from app.services.groq_client import GroqClient

logger = logging.getLogger(__name__)

#: The phrase this system is permitted to use about its own output.
VERIFIED_LANGUAGE: Final[str] = "CASIE-verified for scope"

#: Phrases that would overclaim. Asserted against by the tests, because the
#: distinction between "checked against a stated envelope" and "cleared by a
#: ratings board" is the one this project cannot afford to blur.
FORBIDDEN_CLAIMS: Final[tuple[str, ...]] = (
    "certified compliant",
    "certified",
    "compliant with",
    "approved by",
    "cleared for release",
    "guaranteed",
    "rating assured",
)

#: Keyword signals per content dimension. Deliberately small and deliberately
#: not authoritative: this raises questions, it does not answer them.
SIGNALS: Final[dict[ContentDimension, tuple[str, ...]]] = {
    ContentDimension.VIOLENCE: (
        "kill",
        "kills",
        "killed",
        "murder",
        "stab",
        "stabbed",
        "shoot",
        "shot",
        "blood",
        "bloody",
        "beating",
        "beaten",
        "torture",
        "gore",
        "mutilat",
        "wound",
        "corpse",
    ),
    ContentDimension.SEXUAL_CONTENT: (
        "sex",
        "sexual",
        "nude",
        "nudity",
        "naked",
        "seduc",
        "erotic",
        "intimacy",
        "undress",
        "bedroom scene",
    ),
    ContentDimension.LANGUAGE: (
        "profanity",
        "swears",
        "swearing",
        "curses",
        "expletive",
        "obscenity",
    ),
    ContentDimension.THEMATIC_DARKNESS: (
        "suicide",
        "despair",
        "abuse",
        "grief",
        "trauma",
        "nihilis",
        "hopeless",
        "bleak",
        "cruelty",
    ),
    ContentDimension.DRUG_USE: (
        "heroin",
        "cocaine",
        "meth",
        "overdose",
        "needle",
        "syringe",
        "narcotic",
        "drug",
        "drugs",
        "addict",
    ),
    ContentDimension.HORROR_INTENSITY: (
        "terror",
        "dread",
        "nightmare",
        "monstrous",
        "grotesque",
        "mutilat",
        "possess",
        "haunt",
        "screaming",
    ),
}


class Verdict(StrEnum):
    """The outcome of checking one dimension.

    ``NEEDS_REVIEW`` is not a soft failure. It is the honest answer when a
    check could not be completed, and it is deliberately distinct from
    ``PASS`` so that an unrunnable check can never be mistaken for a
    successful one.
    """

    # Suppression justified: bandit reads the name PASS as a credential
    # constant. It is a verification outcome.
    PASS = "PASS"  # noqa: S105
    FLAGGED = "FLAGGED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


def verify(
    generated: GeneratedVariant,
    envelope: GenerationEnvelope,
    *,
    extraction: dict[str, int] | None = None,
) -> ConstraintSatisfactionReport:
    """Check one variant against its envelope.

    ``extraction`` supplies model-extracted content levels where available.
    Without it the content dimensions rely on the keyword pass alone and
    therefore cannot reach ``PASS``.
    """
    scope_checks = _scope_checks(generated, envelope)
    dimension_checks = _dimension_checks(generated, envelope, extraction)

    return ConstraintSatisfactionReport(
        variant_id=generated.variant.id,
        thresholds=envelope.thresholds,
        envelope=envelope.scope,
        dimension_checks=dimension_checks,
        scope_checks=scope_checks,
    )


def verdicts(
    report: ConstraintSatisfactionReport,
    *,
    extraction_available: bool,
) -> dict[str, Verdict]:
    """Per-axis verdicts for a report.

    Scope axes are arithmetic and so resolve to PASS or FLAGGED. Content axes
    resolve to FLAGGED when a signal exceeds the ceiling, and otherwise to PASS
    only when a structured extraction actually ran.
    """
    result: dict[str, Verdict] = {}
    for scope_check in report.scope_checks:
        result[scope_check.parameter] = Verdict.PASS if scope_check.satisfied else Verdict.FLAGGED
    for dimension_check in report.dimension_checks:
        axis = dimension_check.dimension.value
        if not dimension_check.satisfied:
            result[axis] = Verdict.FLAGGED
        elif extraction_available:
            result[axis] = Verdict.PASS
        else:
            result[axis] = Verdict.NEEDS_REVIEW
    return result


def is_surfaceable(verdicts_by_axis: dict[str, Verdict]) -> bool:
    """Whether a variant may be presented as verified for scope.

    A single FLAGGED axis is disqualifying. ``NEEDS_REVIEW`` is too: the claim
    is that the variant was checked, and an axis nobody could check has not
    been.
    """
    return all(verdict is Verdict.PASS for verdict in verdicts_by_axis.values())


def _scope_checks(
    generated: GeneratedVariant, envelope: GenerationEnvelope
) -> tuple[ScopeCheck, ...]:
    return (
        ScopeCheck(
            parameter="max_locations",
            limit=envelope.scope.max_locations,
            observed=len(generated.locations),
        ),
        ScopeCheck(
            parameter="max_named_characters",
            limit=envelope.scope.max_named_characters,
            observed=len(generated.named_characters),
        ),
    )


def _dimension_checks(
    generated: GeneratedVariant,
    envelope: GenerationEnvelope,
    extraction: dict[str, int] | None,
) -> tuple[DimensionCheck, ...]:
    text = _variant_text(generated.variant)
    checks = []
    for dimension in ContentDimension:
        permitted = envelope.thresholds.level(dimension)
        observed = _observed_level(dimension, text, extraction)
        checks.append(DimensionCheck(dimension=dimension, permitted=permitted, observed=observed))
    return tuple(checks)


def _observed_level(
    dimension: ContentDimension, text: str, extraction: dict[str, int] | None
) -> ContentLevel:
    """The higher of the extracted level and the keyword signal.

    Taking the maximum rather than preferring one source is deliberate: the
    extraction can under-report and the keyword pass can miss implication, and
    a verifier that resolved disagreements downward would systematically
    under-flag.
    """
    signal = _signal_level(dimension, text)
    if extraction is None:
        return signal
    reported = extraction.get(dimension.value)
    if reported is None:
        return signal
    return ContentLevel(max(int(signal), _clamp(reported)))


def _clamp(level: int) -> int:
    return max(0, min(4, level))


def _signal_level(dimension: ContentDimension, text: str) -> ContentLevel:
    """A crude intensity estimate from keyword density.

    Distinct matches, not total occurrences: a scene that says "blood" four
    times is one signal, and counting repetition would let a single image
    dominate the estimate.
    """
    distinct = sum(1 for keyword in SIGNALS[dimension] if keyword in text)
    if distinct == 0:
        return ContentLevel.NONE
    if distinct == 1:
        return ContentLevel.MILD
    if distinct <= 3:
        return ContentLevel.MODERATE
    if distinct <= 5:
        return ContentLevel.STRONG
    return ContentLevel.EXPLICIT


def _variant_text(variant: PlotVariant) -> str:
    parts = [variant.title, variant.logline]
    parts.extend(beat.summary for beat in variant.beats)
    parts.extend(beat.function for beat in variant.beats)
    return " ".join(parts).lower()


async def extract_signals(generated: GeneratedVariant, client: GroqClient) -> dict[str, int] | None:
    """Ask the model to rate its own output on the six dimensions.

    Returns ``None`` on any failure, which the caller turns into
    ``NEEDS_REVIEW``. A failed extraction must never silently become a pass,
    so this reports absence rather than defaulting to zero.
    """
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [dimension.value for dimension in ContentDimension],
        "properties": {
            dimension.value: {"type": "integer", "minimum": 0, "maximum": 4}
            for dimension in ContentDimension
        },
    }
    system = (
        "You are a content classifier. Rate the supplied film concept on each "
        "dimension using the 0-4 scale: 0 none, 1 mild, 2 moderate, 3 strong, "
        "4 explicit. Rate what the text actually contains, not what the genre "
        "usually contains. Return only the JSON object."
    )
    try:
        completion = await client.complete_json(
            system=system,
            user=_variant_text(generated.variant),
            schema=schema,
            temperature=0.0,
        )
        payload = completion.parse_json()
    except LLMError as exc:
        logger.warning(
            "content extraction failed; dimensions degrade to NEEDS_REVIEW",
            extra={"variant_id": generated.variant.id, "error_type": type(exc).__name__},
        )
        return None

    extracted: dict[str, int] = {}
    for dimension in ContentDimension:
        value = payload.get(dimension.value)
        if not isinstance(value, int) or isinstance(value, bool):
            logger.warning(
                "content extraction returned a non-integer level",
                extra={"variant_id": generated.variant.id, "dimension": dimension.value},
            )
            return None
        extracted[dimension.value] = _clamp(value)
    return extracted


def summarise(
    reports: tuple[ConstraintSatisfactionReport, ...], kb_version: str
) -> VerificationResult:
    """Bundle per-variant reports into one result."""
    return VerificationResult(kb_version=kb_version, reports=reports)
