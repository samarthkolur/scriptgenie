"""Conflict detection and resolution, without storing anything.

Both endpoints are pure functions of a bundle and the loaded knowledge base.
That is deliberate and it is what lets the wizard call ``/detect`` on every
edit: there is no row to create, no project to have chosen yet, and no state to
get out of step with the next call.

It also means these endpoints and the generation endpoint cannot disagree.
Generation re-derives the report from the bundle it is given rather than
trusting one the client stored, so the verdict a writer saw here is the verdict
that gates the run — computed the same way, from the same inputs, by the same
code.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Kb
from app.api.v1 import presenters, schemas
from app.core.security import REQUIRE_USER
from app.engines.conflict_detector import detect
from app.engines.scope_parameterizer import parameterize
from app.services.conflict_service import apply_choices, run_detection

router = APIRouter(prefix="/conflicts", tags=["conflicts"], dependencies=[REQUIRE_USER])


@router.post(
    "/detect",
    response_model=schemas.ConflictReportResponse,
    summary="Find the tensions between a bundle's constraints",
)
def detect_conflicts(request: schemas.DetectRequest, kb: Kb) -> schemas.ConflictReportResponse:
    return presenters.conflict_report(run_detection(request.bundle, kb))


@router.post(
    "/resolve",
    response_model=schemas.ResolveResponse,
    summary="Apply resolutions and return the resulting generation envelope",
)
def resolve_conflicts(request: schemas.ResolveRequest, kb: Kb) -> schemas.ResolveResponse:
    report = run_detection(request.bundle, kb)
    resolved = apply_choices(report, request.choices, kb)

    envelope = parameterize(resolved, kb)
    remaining = detect(resolved.bundle, kb).conflicts

    return schemas.ResolveResponse(
        kb_version=kb.version,
        original=resolved.original,
        bundle=resolved.bundle,
        choices=resolved.choices,
        deltas=resolved.deltas,
        envelope=envelope,
        # What the writer still has outstanding. HARD conflicts cannot appear
        # here — `apply_choices` refuses the request if any survived — so this
        # is the SOFT and ADVISORY tail they chose to proceed past.
        remaining_conflicts=remaining,
    )
