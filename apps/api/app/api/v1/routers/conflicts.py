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
from app.core.errors import ConflictStateError, ValidationFailedError
from app.core.security import REQUIRE_USER
from app.domain import ConflictReport, ConstraintBundle, ResolutionChoice, ResolvedBundle
from app.engines import resolution
from app.engines.conflict_detector import detect
from app.engines.errors import (
    EngineError,
    UnknownReferenceError,
    UnknownResolutionError,
    UnresolvedHardConflictError,
)
from app.engines.scope_parameterizer import parameterize
from app.kb.loader import KnowledgeBase

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


def run_detection(bundle: ConstraintBundle, kb: KnowledgeBase) -> ConflictReport:
    """Detect, translating an unresolvable reference into a 422.

    A bundle naming a genre or tier the knowledge base has never heard of is
    well-formed JSON describing something that does not exist. That is the
    caller's mistake and is worth naming precisely, rather than becoming a 500
    that says a rule engine failed.
    """
    try:
        return detect(bundle, kb)
    except UnknownReferenceError as exc:
        raise ValidationFailedError(str(exc), kb_version=kb.version) from exc


def apply_choices(
    report: ConflictReport,
    choices: tuple[ResolutionChoice, ...],
    kb: KnowledgeBase,
) -> ResolvedBundle:
    """Apply the writer's resolutions, or explain why the bundle is still blocked.

    Two distinct failures, and conflating them would leave the client unable to
    act on either:

    * a choice naming a conflict or option that is not in this report is a 422
      — the client sent something incoherent;
    * a HARD conflict surviving is a 409 carrying the surviving conflicts, so
      the UI can show exactly what still has to be decided.
    """
    try:
        return resolution.apply_resolutions(report, choices, kb)
    except UnknownResolutionError as exc:
        raise ValidationFailedError(str(exc)) from exc
    except UnresolvedHardConflictError as exc:
        blocking = tuple(
            conflict for conflict in report.conflicts if conflict.rule_id in set(exc.rule_ids)
        )
        raise ConflictStateError(
            "generation is blocked while a HARD conflict is unresolved",
            conflicts=[conflict.model_dump(mode="json") for conflict in blocking],
            kb_version=kb.version,
        ) from exc
    except EngineError as exc:
        raise ValidationFailedError(str(exc)) from exc
