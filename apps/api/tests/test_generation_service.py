"""Tests for parallel variant generation.

Three claims are under test, and each is measured rather than reasoned about:

*Concurrency.* Five variants against a client that sleeps must finish in about
one call's time, not five. Asserted by timing a deliberately slow fake
transport, which is the only way to tell concurrent from sequential.

*Partial success.* One variant failing must not cost the other four. The
counter-case matters as much as the happy path.

*Provenance.* Every variant records the knowledge base version, prompt version,
model, archetype and seed. A concept that cannot name its inputs is not
reproducible, and reproducibility is the difference between this and asking a
model five times.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.domain import (
    AudienceSelection,
    ConstraintBundle,
    GenerationEnvelope,
    GenreSelection,
    RatingTarget,
    ResolvedBundle,
    TerritorySet,
)
from app.engines.prompt_builder import prompt_version
from app.engines.scope_parameterizer import parameterize
from app.kb.loader import KnowledgeBase, load_knowledge_base
from app.services.generation_service import generate_variants
from app.services.groq_client import GroqClient

FAKE_API_KEY = "not-a-real-credential-for-generation-tests"


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


def _variant_json(beat_count: int = 6, **overrides: Any) -> str:
    payload: dict[str, Any] = {
        "title": "The Long Corridor",
        "logline": "A night nurse discovers the ward is counting its patients wrong.",
        "beats": [
            {"function": f"beat_{i}", "summary": f"Something happens, {i}."}
            for i in range(beat_count)
        ],
        "satisfaction": {
            dimension: {"level": 1, "statement": "Held at implication."}
            for dimension in (
                "violence",
                "sexual_content",
                "language",
                "thematic_darkness",
                "drug_use",
                "horror_intensity",
            )
        },
        "relaxations": ["Depicted harm reduced to aftermath."],
        "locations": ["Ward", "Corridor"],
        "named_characters": ["Mara", "Dr Osei"],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _client(handler: Any, **overrides: Any) -> GroqClient:
    values: dict[str, Any] = {
        "groq_api_key": FAKE_API_KEY,
        "groq_model": "openai/gpt-oss-120b",
        "groq_timeout_seconds": 5.0,
        "groq_max_retries": 0,
        "groq_deadline_seconds": 10.0,
        "groq_breaker_threshold": 100,
    }
    values.update(overrides)
    return GroqClient(settings=Settings(**values), transport=httpx.MockTransport(handler))


def _ok(content: str | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": content or _variant_json()}}],
            "usage": {"prompt_tokens": 800, "completion_tokens": 400},
        },
    )


# ------------------------------------------------------------------ happy path


async def test_generates_the_requested_number_of_variants(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 5, kb, _client(handler))
    assert len(batch.generated) == 5
    assert batch.failed == ()
    assert batch.complete is True
    assert batch.requested == 5


async def test_each_variant_uses_a_distinct_archetype(kb: KnowledgeBase) -> None:
    """Structural diversity is the point; duplicates would defeat it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 5, kb, _client(handler))
    archetypes = [g.provenance.archetype_id for g in batch.generated]
    assert len(set(archetypes)) == 5


async def test_variant_ids_and_beats_are_well_formed(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 2, kb, _client(handler))
    for generated in batch.generated:
        variant = generated.variant
        assert variant.id.startswith("variant_")
        assert [beat.index for beat in variant.beats] == list(range(len(variant.beats)))
        assert variant.title and variant.logline


# ------------------------------------------------------------------ concurrency


async def test_variants_are_generated_concurrently_not_sequentially(
    kb: KnowledgeBase,
) -> None:
    """The acceptance criterion, timed against a deliberately slow transport."""
    call_delay = 0.20

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(call_delay)
        return _ok()

    started = time.monotonic()
    batch = await generate_variants(_envelope(kb), 5, kb, _client(slow_handler))
    elapsed = time.monotonic() - started

    assert len(batch.generated) == 5
    # Sequential would be 5 * 0.20 = 1.0s. Concurrent is one call plus overhead.
    assert elapsed < call_delay * 2.5, f"took {elapsed:.2f}s; looks sequential"


async def test_batch_deadline_bounds_the_whole_request(kb: KnowledgeBase) -> None:
    async def very_slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5.0)
        return _ok()

    started = time.monotonic()
    batch = await generate_variants(_envelope(kb), 3, kb, _client(very_slow), deadline_seconds=0.3)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"batch ran {elapsed:.2f}s past a 0.3s deadline"
    assert len(batch.failed) == 3
    assert all("deadline" in failure.reason.lower() for failure in batch.failed)


# ------------------------------------------------------------------ partial


async def test_one_failing_variant_does_not_fail_the_batch(kb: KnowledgeBase) -> None:
    """The acceptance criterion. Four good concepts must not be lost to one bad."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(500, json={"error": "unavailable"})
        return _ok()

    batch = await generate_variants(_envelope(kb), 5, kb, _client(handler))
    assert len(batch.generated) == 4
    assert len(batch.failed) == 1
    assert batch.complete is False
    assert batch.requested == 5


async def test_failure_names_the_archetype_that_was_lost(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    batch = await generate_variants(_envelope(kb), 3, kb, _client(handler))
    assert len(batch.failed) == 3
    for failure in batch.failed:
        assert failure.archetype_id
        assert failure.error_type == "LLMServerError"
        assert failure.reason


async def test_a_wholly_failed_batch_still_returns(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    batch = await generate_variants(_envelope(kb), 2, kb, _client(handler))
    assert batch.generated == ()
    assert len(batch.failed) == 2


# ------------------------------------------------------------------ repair


async def test_malformed_json_is_repaired_once(kb: KnowledgeBase) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return _ok(content="{ this is not json")
        return _ok()

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert len(batch.generated) == 1
    assert batch.generated[0].provenance.repaired is True
    assert calls["n"] == 2


async def test_the_repair_prompt_states_the_failure(kb: KnowledgeBase) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload["messages"][1]["content"])
        if len(seen) == 1:
            return _ok(content="not json at all")
        return _ok()

    await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert "Correction required" in seen[1]
    assert "## Hard constraints" in seen[1], "constraints must survive the repair"


async def test_repair_is_one_shot(kb: KnowledgeBase) -> None:
    """A model that returns unusable JSON twice will not be argued into correctness."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok(content="{ still not json")

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert len(batch.failed) == 1
    assert calls["n"] == 2


async def test_a_successful_variant_is_not_marked_repaired(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert batch.generated[0].provenance.repaired is False


# ------------------------------------------------------------------ contract


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"beats": []}, "no beats"),
        ({"beats": "not a list"}, "no beats"),
        ({"beats": [{"function": "f"}] * 6}, "missing function or summary"),
        ({"beats": ["not an object"] * 6}, "not an object"),
        ({"title": ""}, "missing a title"),
        ({"logline": ""}, "missing a title"),
    ],
)
async def test_output_violating_the_contract_is_rejected(
    kb: KnowledgeBase, payload: dict[str, Any], fragment: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok(content=_variant_json(**payload))

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert len(batch.failed) == 1
    assert fragment in batch.failed[0].reason


async def test_too_few_beats_for_the_archetype_is_rejected(kb: KnowledgeBase) -> None:
    """Transformation Arc needs six; five is a real shortfall, not a rounding issue."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok(content=_variant_json(beat_count=3))

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert len(batch.failed) == 1
    assert "requires" in batch.failed[0].reason


# ------------------------------------------------------------------ provenance


async def test_every_variant_records_its_provenance(kb: KnowledgeBase) -> None:
    """The acceptance criterion, field by field."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 3, kb, _client(handler), seed=42)
    for generated in batch.generated:
        provenance = generated.provenance
        assert provenance.kb_version == kb.version
        assert provenance.prompt_version == prompt_version()
        assert provenance.model == "openai/gpt-oss-120b"
        assert provenance.archetype_id
        assert provenance.seed == 42
        assert provenance.attempts >= 1


async def test_the_seed_reaches_archetype_assignment(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    first = await generate_variants(_envelope(kb), 2, kb, _client(handler), seed=1)
    again = await generate_variants(_envelope(kb), 2, kb, _client(handler), seed=1)
    assert [g.provenance.archetype_id for g in first.generated] == [
        g.provenance.archetype_id for g in again.generated
    ]


async def test_model_reported_output_is_captured(kb: KnowledgeBase) -> None:
    """Satisfaction statements and relaxation flags are the model's own claims.

    They are retained but not trusted; Stage 3.4 checks them independently.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    generated = batch.generated[0]
    assert set(generated.satisfaction) == {
        "violence",
        "sexual_content",
        "language",
        "thematic_darkness",
        "drug_use",
        "horror_intensity",
    }
    assert generated.relaxations
    assert generated.locations == ("Ward", "Corridor")
    assert generated.named_characters == ("Mara", "Dr Osei")


async def test_missing_optional_fields_default_to_empty(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(_variant_json())
        for key in ("relaxations", "locations", "named_characters", "satisfaction"):
            content.pop(key)
        return _ok(content=json.dumps(content))

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    generated = batch.generated[0]
    assert generated.relaxations == ()
    assert generated.locations == ()
    assert generated.satisfaction == {}


async def test_batch_records_elapsed_time(kb: KnowledgeBase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok()

    batch = await generate_variants(_envelope(kb), 1, kb, _client(handler))
    assert batch.elapsed_ms >= 0
