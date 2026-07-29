"""Running the whole pipeline for one project, and persisting what it produced.

The pipeline itself was built in phases 2 and 3 and is not repeated here:
``detect`` → ``apply_resolutions`` → ``parameterize`` → ``select`` →
``generate_variants`` → ``verify``. What this module adds is everything that
makes a run an artefact rather than an answer — the ordering, the persistence,
and the guarantee that a crash leaves evidence.

Three decisions are worth stating.

*The report is re-derived, never trusted.* The client sends a bundle and its
resolutions; this recomputes the conflict report from them. A report is a pure
function of a bundle and a knowledge base version, so re-deriving costs
microseconds and removes the class of bug where a stored report and the
submitted bundle have drifted apart — which is exactly the drift that would let
a HARD conflict through the gate.

*The run row is opened before the model is called.* A run written only on
success makes every failure invisible, including the ones that spent tokens.

*Partial success is a success.* One variant returning unusable JSON is a normal
outcome of a remote model. Four good concepts are not thrown away for it, and
the failure is returned with its reason attached so the caller can say what it
lost.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from app.api.v1 import presenters, schemas
from app.core.errors import UpstreamError
from app.core.security import AuthenticatedUser
from app.db import repositories
from app.db.supabase import SupabaseClient
from app.domain import ConstraintSatisfactionReport, GenerationEnvelope
from app.engines import prompt_builder, verifier
from app.engines.archetype_selector import InsufficientArchetypesError
from app.engines.scope_parameterizer import parameterize
from app.kb.loader import KnowledgeBase
from app.services.errors import LLMConfigurationError, LLMError
from app.services.generation_service import GeneratedVariant, generate_variants
from app.services.groq_client import GroqClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedRun:
    """A resolved bundle, its envelope, and the rows recording both."""

    envelope: GenerationEnvelope
    bundle_id: UUID
    report_id: UUID
    envelope_id: UUID


async def prepare(
    db: SupabaseClient,
    user: AuthenticatedUser,
    kb: KnowledgeBase,
    project_id: UUID,
    request: schemas.GenerateRequest,
) -> PreparedRun:
    """Detect, resolve, parameterise and persist — before any model is called.

    Everything here is deterministic and free. Doing it first means a bundle
    that cannot legally be generated is refused without spending a token, and
    that the envelope a variant is later judged against is already on disk.
    """
    from app.api.v1.routers.conflicts import apply_choices, run_detection

    report = run_detection(request.bundle, kb)
    resolved = apply_choices(report, request.choices, kb)
    envelope = parameterize(resolved, kb)

    bundle_row = await repositories.save_bundle(db, user, project_id, resolved.bundle)
    report_row = await repositories.save_conflict_report(
        db, user, project_id, UUID(str(bundle_row["id"])), report
    )
    await repositories.save_resolutions(
        db, user, project_id, UUID(str(report_row["id"])), resolved.choices, resolved.deltas
    )
    envelope_row = await repositories.save_envelope(
        db, user, project_id, UUID(str(report_row["id"])), kb.version, envelope
    )

    return PreparedRun(
        envelope=envelope,
        bundle_id=UUID(str(bundle_row["id"])),
        report_id=UUID(str(report_row["id"])),
        envelope_id=UUID(str(envelope_row["id"])),
    )


async def run_generation(
    db: SupabaseClient,
    user: AuthenticatedUser,
    kb: KnowledgeBase,
    groq: GroqClient,
    project_id: UUID,
    request: schemas.GenerateRequest,
    prepared: PreparedRun,
) -> schemas.GenerationResponse:
    """Generate, verify and store the batch."""
    run_row = await repositories.open_run(
        db,
        user,
        project_id=project_id,
        envelope_id=prepared.envelope_id,
        requested=request.variant_count,
        seed=request.seed,
        model=groq.settings.groq_model,
        prompt_version=prompt_builder.prompt_version(),
        kb_version=kb.version,
    )
    run_id = UUID(str(run_row["id"]))

    try:
        batch = await generate_variants(
            prepared.envelope, request.variant_count, kb, groq, seed=request.seed
        )
    except (LLMError, InsufficientArchetypesError) as exc:
        # The run row already exists, so the failure is recorded rather than
        # vanishing with the request that caused it.
        await repositories.close_run(
            db,
            user,
            run_id,
            status="failed",
            generated=0,
            failed=request.variant_count,
            elapsed_ms=0.0,
            failures=[{"reason": str(exc), "error_type": type(exc).__name__}],
        )
        await repositories.set_project_status(db, user, project_id, "draft")
        if isinstance(exc, LLMConfigurationError):
            raise
        raise UpstreamError(f"generation could not be completed: {exc}") from exc

    verified = await _verify_all(batch.generated, prepared.envelope, groq)

    stored = await repositories.save_variants(
        db, user, project_id=project_id, run_id=run_id, records=verified
    )

    status = "complete" if batch.complete else ("partial" if batch.generated else "failed")
    closed = await repositories.close_run(
        db,
        user,
        run_id,
        status=status,
        generated=len(batch.generated),
        failed=len(batch.failed),
        elapsed_ms=batch.elapsed_ms,
        failures=[
            {
                "archetype_id": failure.archetype_id,
                "variant_index": failure.variant_index,
                "reason": failure.reason,
                "error_type": failure.error_type,
            }
            for failure in batch.failed
        ],
    )
    await repositories.set_project_status(
        db, user, project_id, "complete" if batch.generated else "draft"
    )

    logger.info(
        "generation run finished",
        extra={
            "run_id": str(run_id),
            "project_id": str(project_id),
            "run_status": status,
            "generated": len(batch.generated),
            "failed": len(batch.failed),
            "surfaceable": sum(1 for record in verified if record[3]),
        },
    )

    return schemas.GenerationResponse(
        run=presenters.generation_run(closed if closed is not None else run_row),
        envelope=prepared.envelope,
        variants=tuple(presenters.variant(row) for row in stored),
        failures=tuple(
            schemas.FailedVariantOut(
                archetype_id=failure.archetype_id,
                variant_index=failure.variant_index,
                reason=failure.reason,
                error_type=failure.error_type,
            )
            for failure in batch.failed
        ),
    )


async def _verify_all(
    generated: tuple[GeneratedVariant, ...],
    envelope: GenerationEnvelope,
    groq: GroqClient,
) -> list[tuple[GeneratedVariant, ConstraintSatisfactionReport, dict[str, str], bool]]:
    """Verify every variant, extracting content signals concurrently.

    The extraction is a second model call per variant, so they run together
    rather than in series. Each returns ``None`` on failure, and a ``None``
    degrades that variant's content axes to ``NEEDS_REVIEW`` — never to
    ``PASS``. A check that did not run is not a check that succeeded, and
    treating it as one is precisely how "verified" becomes a word with no
    content.
    """
    extractions = await asyncio.gather(
        *(verifier.extract_signals(variant, groq) for variant in generated),
        return_exceptions=True,
    )

    records = []
    for variant, extraction in zip(generated, extractions, strict=True):
        signals = extraction if isinstance(extraction, dict) else None
        report = verifier.verify(variant, envelope, extraction=signals)
        verdicts = {
            axis: verdict.value
            for axis, verdict in verifier.verdicts(
                report, extraction_available=signals is not None
            ).items()
        }
        surfaceable = verifier.is_surfaceable(
            verifier.verdicts(report, extraction_available=signals is not None)
        )
        records.append((variant, report, verdicts, surfaceable))
    return records
