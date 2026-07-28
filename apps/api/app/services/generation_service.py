"""Generating N plot variants concurrently, one per assigned archetype.

Concurrency here is not a performance nicety. Five sequential calls at Groq's
latency is a wait a writer will not sit through, and the variants are
independent by construction -- each has its own archetype and its own prompt --
so there is no ordering to preserve.

Partial success is the other half. One variant returning unusable JSON is a
normal outcome of a remote model, and failing the batch for it would throw away
four good concepts. Failures are reported alongside successes with the reason
attached, so the caller can show what it has and say what it lost.

Every variant records the knowledge base version, prompt version, model,
archetype and seed that produced it. A concept that cannot name the inputs
behind it is not reproducible, and reproducibility is what separates this from
asking a model five times.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.domain import (
    ArchetypeAssignment,
    GenerationEnvelope,
    PlotBeat,
    PlotVariant,
)
from app.engines import prompt_builder
from app.engines.archetype_selector import select
from app.kb.loader import KnowledgeBase
from app.services.errors import LLMError, LLMResponseError
from app.services.groq_client import GroqClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VariantProvenance:
    """Everything needed to explain or reproduce one variant."""

    kb_version: str
    prompt_version: str
    model: str
    archetype_id: str
    seed: int
    attempts: int
    repaired: bool


@dataclass(frozen=True, slots=True)
class GeneratedVariant:
    """A successfully generated and parsed variant."""

    variant: PlotVariant
    provenance: VariantProvenance
    satisfaction: dict[str, Any]
    relaxations: tuple[str, ...]
    locations: tuple[str, ...]
    named_characters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FailedVariant:
    """A variant that could not be produced, and why.

    Carries the archetype so the caller can say which structure is missing
    rather than only that something is.
    """

    archetype_id: str
    variant_index: int
    reason: str
    error_type: str


@dataclass(frozen=True, slots=True)
class GenerationBatch:
    """The result of one generation request."""

    generated: tuple[GeneratedVariant, ...]
    failed: tuple[FailedVariant, ...]
    elapsed_ms: float

    @property
    def requested(self) -> int:
        return len(self.generated) + len(self.failed)

    @property
    def complete(self) -> bool:
        return not self.failed


async def generate_variants(
    envelope: GenerationEnvelope,
    n: int,
    kb: KnowledgeBase,
    client: GroqClient,
    *,
    seed: int = 0,
    deadline_seconds: float | None = None,
) -> GenerationBatch:
    """Generate ``n`` variants concurrently, one per distinct archetype.

    Returns whatever succeeded. The batch is never abandoned for a single
    failure, and the total deadline bounds the whole request rather than each
    call individually.
    """
    assignments = select(envelope, n, kb, seed=seed)
    started = time.monotonic()

    budget = deadline_seconds
    if budget is None:
        # One slow variant must not extend the batch indefinitely. The client's
        # own per-request deadline applies to each call; this bounds the group.
        budget = client.settings.groq_deadline_seconds * 2

    tasks = [_generate_one(envelope, assignment, kb, client, seed) for assignment in assignments]

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=budget
        )
    except TimeoutError:
        # gather was cancelled; report every variant as timed out rather than
        # returning an empty batch with no explanation.
        results = [TimeoutError(f"batch deadline of {budget:.1f}s elapsed") for _ in assignments]

    generated: list[GeneratedVariant] = []
    failed: list[FailedVariant] = []
    for assignment, result in zip(assignments, results, strict=True):
        if isinstance(result, GeneratedVariant):
            generated.append(result)
        else:
            failed.append(
                FailedVariant(
                    archetype_id=assignment.archetype_id,
                    variant_index=assignment.variant_index,
                    reason=str(result),
                    error_type=type(result).__name__,
                )
            )

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info(
        "variant batch complete",
        extra={
            "kb_version": kb.version,
            "prompt_version": prompt_builder.prompt_version(),
            "requested": len(assignments),
            "generated": len(generated),
            "failed": len(failed),
            "elapsed_ms": round(elapsed_ms, 2),
            "seed": seed,
        },
    )
    return GenerationBatch(generated=tuple(generated), failed=tuple(failed), elapsed_ms=elapsed_ms)


async def _generate_one(
    envelope: GenerationEnvelope,
    assignment: ArchetypeAssignment,
    kb: KnowledgeBase,
    client: GroqClient,
    seed: int,
) -> GeneratedVariant:
    """One variant, with a single repair retry on unusable output.

    The repair is one-shot on purpose. A model that returns unusable JSON twice
    is not going to be argued into correctness, and each extra attempt spends
    the batch deadline that the other variants also need.
    """
    archetype = kb.archetype(assignment.archetype_id)
    system, user = prompt_builder.build(envelope, assignment.archetype_id, kb)
    schema = prompt_builder.variant_schema(archetype)

    try:
        completion = await client.complete_json(system=system, user=user, schema=schema)
        payload = completion.parse_json()
        variant = _to_variant(payload, assignment, archetype)
        repaired = False
    except LLMResponseError as first:
        completion = await client.complete_json(
            system=system, user=_repair_instruction(user, first), schema=schema
        )
        payload = completion.parse_json()
        variant = _to_variant(payload, assignment, archetype)
        repaired = True

    return GeneratedVariant(
        variant=variant,
        provenance=VariantProvenance(
            kb_version=kb.version,
            prompt_version=prompt_builder.prompt_version(),
            model=completion.model,
            archetype_id=assignment.archetype_id,
            seed=seed,
            attempts=completion.attempts,
            repaired=repaired,
        ),
        satisfaction=dict(payload.get("satisfaction") or {}),
        relaxations=tuple(payload.get("relaxations") or ()),
        locations=tuple(payload.get("locations") or ()),
        named_characters=tuple(payload.get("named_characters") or ()),
    )


def _repair_instruction(user: str, failure: LLMError) -> str:
    """Re-ask with the parse failure stated, and nothing else changed.

    The constraints are unchanged because they were never the problem; only the
    shape of the reply was.
    """
    return (
        f"{user}\n\n## Correction required\n\n"
        f"Your previous reply could not be used: {failure}. "
        "Return a single valid JSON object matching the required shape exactly. "
        "No prose, no markdown fences, no trailing commentary."
    )


def _to_variant(
    payload: dict[str, Any], assignment: ArchetypeAssignment, archetype: dict[str, Any]
) -> PlotVariant:
    """Build the domain model, rejecting output the contract does not allow.

    Raises :class:`~app.services.errors.LLMResponseError` for anything
    unusable, so a malformed reply is handled on the same path as malformed
    JSON and gets the same one-shot repair.
    """
    raw_beats = payload.get("beats")
    if not isinstance(raw_beats, list) or not raw_beats:
        raise LLMResponseError("variant contained no beats")

    minimum = int(archetype["min_beats"])
    if len(raw_beats) < minimum:
        raise LLMResponseError(
            f"variant has {len(raw_beats)} beats; {archetype['id']} requires {minimum}"
        )

    beats = []
    for index, raw in enumerate(raw_beats):
        if not isinstance(raw, dict):
            raise LLMResponseError(f"beat {index} is not an object")
        function = raw.get("function")
        summary = raw.get("summary")
        if not function or not summary:
            raise LLMResponseError(f"beat {index} is missing function or summary")
        beats.append(PlotBeat(index=index, function=str(function), summary=str(summary)))

    title = payload.get("title")
    logline = payload.get("logline")
    if not title or not logline:
        raise LLMResponseError("variant is missing a title or logline")

    return PlotVariant(
        id=f"variant_{assignment.variant_index}",
        title=str(title),
        logline=str(logline),
        archetype=assignment,
        beats=tuple(beats),
    )
