"""Tests for post-generation verification.

The named acceptance criteria first:

* a variant naming seven locations under ``micro`` is FLAGGED on
  ``max_locations``;
* no variant is surfaced as verified while any axis is FLAGGED;
* a verification failure degrades to NEEDS_REVIEW and never to a silent pass.

The third is the one worth being strict about. A system that treats an
unrunnable check as a successful one is not verifying anything, it is
asserting. Several tests below exist only to prove that path cannot be taken.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.domain import (
    ArchetypeAssignment,
    AudienceSelection,
    ConstraintBundle,
    ContentDimension,
    GenerationEnvelope,
    GenreSelection,
    PlotBeat,
    PlotVariant,
    RatingTarget,
    ResolvedBundle,
    TerritorySet,
)
from app.engines.scope_parameterizer import parameterize
from app.engines.verifier import (
    FORBIDDEN_CLAIMS,
    VERIFIED_LANGUAGE,
    Verdict,
    extract_signals,
    is_surfaceable,
    summarise,
    verdicts,
    verify,
)
from app.kb.loader import KnowledgeBase, load_knowledge_base
from app.services.generation_service import GeneratedVariant, VariantProvenance
from app.services.groq_client import GroqClient

FAKE_API_KEY = "not-a-real-credential-for-verifier-tests"

ALL_DIMENSIONS = tuple(dimension.value for dimension in ContentDimension)


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_knowledge_base()


def _envelope(kb: KnowledgeBase, **overrides: Any) -> GenerationEnvelope:
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


def _generated(
    *,
    locations: tuple[str, ...] = ("Ward", "Corridor"),
    characters: tuple[str, ...] = ("Mara", "Osei"),
    summaries: tuple[str, ...] = ("She takes the night shift.", "A door is ajar."),
    title: str = "The Long Corridor",
) -> GeneratedVariant:
    beats = tuple(
        PlotBeat(index=i, function=f"beat_{i}", summary=text) for i, text in enumerate(summaries)
    )
    return GeneratedVariant(
        variant=PlotVariant(
            id="variant_0",
            title=title,
            logline="A night nurse discovers the ward miscounts its patients.",
            archetype=ArchetypeAssignment(
                variant_index=0, archetype_id="crucible", score=6, rationale="Confined."
            ),
            beats=beats,
        ),
        provenance=VariantProvenance(
            kb_version="0.1.1",
            prompt_version="1.0.0",
            model="openai/gpt-oss-120b",
            archetype_id="crucible",
            seed=0,
            attempts=1,
            repaired=False,
        ),
        satisfaction={},
        relaxations=(),
        locations=locations,
        named_characters=characters,
    )


def _clean_extraction(level: int = 0) -> dict[str, int]:
    return dict.fromkeys(ALL_DIMENSIONS, level)


# ------------------------------------------------------------------ acceptance


def test_seven_locations_under_micro_is_flagged(kb: KnowledgeBase) -> None:
    """The named acceptance criterion. Micro permits three."""
    generated = _generated(locations=tuple(f"Location {i}" for i in range(7)))
    report = verify(generated, _envelope(kb), extraction=_clean_extraction())

    location_check = next(c for c in report.scope_checks if c.parameter == "max_locations")
    assert location_check.limit == 3
    assert location_check.observed == 7
    assert location_check.satisfied is False

    assert verdicts(report, extraction_available=True)["max_locations"] is Verdict.FLAGGED
    assert "max_locations" in report.violations()


def test_no_variant_is_surfaced_while_any_axis_is_flagged(kb: KnowledgeBase) -> None:
    """The second acceptance criterion, asserted axis by axis.

    One failure anywhere is disqualifying; a mostly-passing variant is not a
    passing variant.
    """
    envelope = _envelope(kb)
    for locations, characters in (
        (tuple(f"L{i}" for i in range(9)), ("A", "B")),
        (("Ward",), tuple(f"C{i}" for i in range(9))),
    ):
        generated = _generated(locations=locations, characters=characters)
        report = verify(generated, envelope, extraction=_clean_extraction())
        axis_verdicts = verdicts(report, extraction_available=True)
        assert Verdict.FLAGGED in axis_verdicts.values()
        assert is_surfaceable(axis_verdicts) is False
        assert report.satisfied is False


def test_a_failed_extraction_degrades_to_needs_review_never_to_pass(
    kb: KnowledgeBase,
) -> None:
    """The third acceptance criterion, and the one that matters most.

    A check that could not run is not a check that succeeded.
    """
    generated = _generated()
    report = verify(generated, _envelope(kb), extraction=None)
    axis_verdicts = verdicts(report, extraction_available=False)

    for dimension in ALL_DIMENSIONS:
        assert axis_verdicts[dimension] is Verdict.NEEDS_REVIEW
    assert Verdict.PASS not in {axis_verdicts[d] for d in ALL_DIMENSIONS}
    assert is_surfaceable(axis_verdicts) is False


def test_needs_review_blocks_surfacing_just_as_flagged_does(kb: KnowledgeBase) -> None:
    assert is_surfaceable({"a": Verdict.PASS, "b": Verdict.NEEDS_REVIEW}) is False
    assert is_surfaceable({"a": Verdict.PASS, "b": Verdict.FLAGGED}) is False
    assert is_surfaceable({"a": Verdict.PASS, "b": Verdict.PASS}) is True


def test_a_clean_variant_with_extraction_passes(kb: KnowledgeBase) -> None:
    """The positive case, so the checks are not merely always-failing."""
    generated = _generated()
    report = verify(generated, _envelope(kb), extraction=_clean_extraction())
    axis_verdicts = verdicts(report, extraction_available=True)
    assert is_surfaceable(axis_verdicts) is True
    assert report.satisfied is True
    assert report.violations() == ()


# ------------------------------------------------------------------ scope


def test_counts_come_from_the_enumerations_not_the_prose(kb: KnowledgeBase) -> None:
    generated = _generated(locations=("A", "B", "C"), characters=("X",))
    report = verify(generated, _envelope(kb), extraction=_clean_extraction())
    by_parameter = {c.parameter: c for c in report.scope_checks}
    assert by_parameter["max_locations"].observed == 3
    assert by_parameter["max_named_characters"].observed == 1


def test_exactly_at_the_limit_passes(kb: KnowledgeBase) -> None:
    """Micro permits three locations, so three is inside the envelope."""
    generated = _generated(locations=("A", "B", "C"), characters=("A", "B", "C", "D", "E"))
    report = verify(generated, _envelope(kb), extraction=_clean_extraction())
    assert all(check.satisfied for check in report.scope_checks)


def test_an_unbounded_tier_cannot_be_exceeded(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb, budget_tier_id="studio", genre=GenreSelection(primary="action"))
    generated = _generated(locations=tuple(f"L{i}" for i in range(40)))
    report = verify(generated, envelope, extraction=_clean_extraction())
    location_check = next(c for c in report.scope_checks if c.parameter == "max_locations")
    assert location_check.limit is None
    assert location_check.satisfied is True


# ------------------------------------------------------------------ signals


def test_content_signals_are_read_from_the_prose(kb: KnowledgeBase) -> None:
    """A concept full of explicit violence must not slip past a level-1 ceiling."""
    generated = _generated(
        summaries=(
            "He is stabbed and left to bleed; the blood pools by the corpse.",
            "A second murder follows, with torture and mutilated remains.",
        )
    )
    report = verify(generated, _envelope(kb), extraction=_clean_extraction())
    violence = next(c for c in report.dimension_checks if c.dimension is ContentDimension.VIOLENCE)
    assert int(violence.observed) >= 3
    assert violence.satisfied is False


def test_a_restrained_concept_reads_as_low_intensity(kb: KnowledgeBase) -> None:
    generated = _generated(
        summaries=("She counts the beds twice.", "The register disagrees with her memory.")
    )
    report = verify(generated, _envelope(kb), extraction=_clean_extraction())
    violence = next(c for c in report.dimension_checks if c.dimension is ContentDimension.VIOLENCE)
    assert int(violence.observed) == 0


def test_the_higher_of_extraction_and_signal_is_taken(kb: KnowledgeBase) -> None:
    """A verifier that resolved disagreements downward would under-flag."""
    generated = _generated(
        summaries=("A murder, with blood, a corpse and visible wounds and gore.",)
    )
    # The model claims the concept is clean; the prose says otherwise.
    report = verify(generated, _envelope(kb), extraction=_clean_extraction(0))
    violence = next(c for c in report.dimension_checks if c.dimension is ContentDimension.VIOLENCE)
    assert int(violence.observed) >= 3


def test_extraction_can_raise_a_level_the_keywords_missed(kb: KnowledgeBase) -> None:
    """Implication carries no keywords, which is exactly the heuristic's weakness."""
    generated = _generated(summaries=("What she finds in the ward is never described.",))
    extraction = _clean_extraction()
    extraction["violence"] = 4
    report = verify(generated, _envelope(kb), extraction=extraction)
    violence = next(c for c in report.dimension_checks if c.dimension is ContentDimension.VIOLENCE)
    assert int(violence.observed) == 4
    assert violence.satisfied is False


def test_out_of_range_extraction_values_are_clamped(kb: KnowledgeBase) -> None:
    extraction = _clean_extraction()
    extraction["violence"] = 99
    report = verify(_generated(), _envelope(kb), extraction=extraction)
    violence = next(c for c in report.dimension_checks if c.dimension is ContentDimension.VIOLENCE)
    assert int(violence.observed) == 4


def test_a_missing_dimension_in_the_extraction_falls_back_to_signal(
    kb: KnowledgeBase,
) -> None:
    extraction = _clean_extraction()
    del extraction["violence"]
    report = verify(_generated(), _envelope(kb), extraction=extraction)
    assert len(report.dimension_checks) == len(ALL_DIMENSIONS)


def test_every_dimension_is_reported_whether_it_passes_or_not(kb: KnowledgeBase) -> None:
    """A report listing only failures makes 'checked' and 'clean' indistinguishable."""
    report = verify(_generated(), _envelope(kb), extraction=_clean_extraction())
    assert {c.dimension for c in report.dimension_checks} == set(ContentDimension)


# ------------------------------------------------------------------ extraction


async def _client(handler: Any) -> GroqClient:
    settings = Settings(
        groq_api_key=FAKE_API_KEY,
        groq_model="openai/gpt-oss-120b",
        groq_max_retries=0,
        groq_deadline_seconds=5.0,
        groq_breaker_threshold=100,
    )
    return GroqClient(settings=settings, transport=httpx.MockTransport(handler))


def _extraction_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 40},
        },
    )


async def test_extraction_returns_levels(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _extraction_response(dict.fromkeys(ALL_DIMENSIONS, 2))

    result = await extract_signals(_generated(), await _client(handler))
    assert result == dict.fromkeys(ALL_DIMENSIONS, 2)


async def test_extraction_failure_returns_none_not_zeroes(kb: KnowledgeBase) -> None:
    """Zeroes would read as 'clean'. Absence reads as 'not checked'."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    assert await extract_signals(_generated(), await _client(handler)) is None


async def test_malformed_extraction_returns_none(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _extraction_response({"violence": "high"})

    assert await extract_signals(_generated(), await _client(handler)) is None


async def test_extraction_missing_a_dimension_returns_none(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = dict.fromkeys(ALL_DIMENSIONS, 1)
        del payload["drug_use"]
        return _extraction_response(payload)

    assert await extract_signals(_generated(), await _client(handler)) is None


async def test_boolean_is_not_accepted_as_a_level(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload: dict[str, Any] = dict.fromkeys(ALL_DIMENSIONS, 1)
        payload["violence"] = True
        return _extraction_response(payload)

    assert await extract_signals(_generated(), await _client(handler)) is None


async def test_extraction_values_are_clamped(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload: dict[str, Any] = dict.fromkeys(ALL_DIMENSIONS, 0)
        payload["violence"] = 17
        payload["drug_use"] = -3
        return _extraction_response(payload)

    result = await extract_signals(_generated(), await _client(handler))
    assert result is not None
    assert result["violence"] == 4
    assert result["drug_use"] == 0


async def test_a_failed_extraction_ends_in_needs_review(kb: KnowledgeBase) -> None:
    """End to end: the failure path reaches the verdict it should."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    generated = _generated()
    extraction = await extract_signals(generated, await _client(handler))
    report = verify(generated, _envelope(kb), extraction=extraction)
    axis_verdicts = verdicts(report, extraction_available=extraction is not None)
    assert all(axis_verdicts[d] is Verdict.NEEDS_REVIEW for d in ALL_DIMENSIONS)
    assert is_surfaceable(axis_verdicts) is False


# ------------------------------------------------------------------ language


def test_the_permitted_claim_is_verified_for_scope() -> None:
    """Risk 2 in the research analysis: never 'certified compliant'."""
    assert VERIFIED_LANGUAGE == "CASIE-verified for scope"
    lowered = VERIFIED_LANGUAGE.lower()
    for claim in FORBIDDEN_CLAIMS:
        assert claim not in lowered


def test_no_module_claims_compliance_or_certification() -> None:
    """A guard over the whole application, not just one string.

    ``verifier.py`` is excluded because it is the definition site: it holds
    ``FORBIDDEN_CLAIMS`` and the docstring explaining the rule, so it has to
    name the phrases it forbids. Everything else is checked, including the
    prompt templates — a prompt telling the model its output is "certified"
    would put the claim in front of a user just as surely as UI copy would.
    """
    from pathlib import Path

    root = Path(__file__).parent.parent / "app"
    sources = [
        path
        for path in list(root.rglob("*.py")) + list(root.rglob("*.md"))
        if path.name != "verifier.py"
    ]
    assert sources, "the guard found nothing to check"

    for source in sources:
        text = source.read_text(encoding="utf-8").lower()
        for claim in ("certified compliant", "cleared for release", "rating assured"):
            assert claim not in text, f"{source.name} overclaims: {claim!r}"


def test_the_overclaim_guard_would_catch_a_real_violation() -> None:
    """Verifies the guard rather than trusting it."""
    offending = "This concept is certified compliant with MPA guidelines.".lower()
    assert any(claim in offending for claim in FORBIDDEN_CLAIMS)


# ------------------------------------------------------------------ summary


def test_summarise_bundles_reports(kb: KnowledgeBase) -> None:
    envelope = _envelope(kb)
    clean = verify(_generated(), envelope, extraction=_clean_extraction())
    dirty = verify(
        _generated(locations=tuple(f"L{i}" for i in range(9))),
        envelope,
        extraction=_clean_extraction(),
    )
    result = summarise((clean, dirty), kb.version)
    assert result.kb_version == kb.version
    assert result.verified is False
    assert result.failed_variants() == ("variant_0",)


def test_summarise_of_clean_reports_is_verified(kb: KnowledgeBase) -> None:
    clean = verify(_generated(), _envelope(kb), extraction=_clean_extraction())
    result = summarise((clean,), kb.version)
    assert result.verified is True
    assert result.failed_variants() == ()


def test_a_content_dimension_over_its_ceiling_is_flagged(kb: KnowledgeBase) -> None:
    """Content axes reach FLAGGED too, not only the arithmetic scope axes."""
    extraction = _clean_extraction()
    extraction["violence"] = 4
    report = verify(_generated(), _envelope(kb), extraction=extraction)
    axis_verdicts = verdicts(report, extraction_available=True)
    assert axis_verdicts["violence"] is Verdict.FLAGGED
    assert axis_verdicts["drug_use"] is Verdict.PASS
    assert is_surfaceable(axis_verdicts) is False


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("Nothing happens at all.", 0),
        ("There is blood.", 1),
        ("There is blood and a corpse.", 2),
        # Three distinct matches is still the top of the moderate band.
        ("Blood, a corpse and a stabbing.", 2),
        # "stab wound" contributes two distinct signals, not one.
        ("Blood, a corpse and a stab wound.", 3),
        ("Blood, corpse, stab, wound and gore.", 3),
        ("Blood, corpse, stab, wound, gore, murder and torture.", 4),
    ],
)
def test_signal_bands_scale_with_distinct_matches(
    kb: KnowledgeBase, summary: str, expected: int
) -> None:
    """Distinct matches, not repetitions: one image repeated is still one signal."""
    report = verify(_generated(summaries=(summary,)), _envelope(kb))
    violence = next(c for c in report.dimension_checks if c.dimension is ContentDimension.VIOLENCE)
    assert int(violence.observed) == expected


def test_repetition_does_not_inflate_a_signal(kb: KnowledgeBase) -> None:
    once = verify(_generated(summaries=("There is blood.",)), _envelope(kb))
    many = verify(_generated(summaries=("Blood, blood, blood everywhere; blood.",)), _envelope(kb))
    assert [c.observed for c in once.dimension_checks] == [
        c.observed for c in many.dimension_checks
    ]
