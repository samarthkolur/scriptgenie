"""Detect and resolve, translating engine failures into HTTP-facing errors.

Shared by the ``/conflicts`` router, which calls these against a submitted
bundle with nothing stored yet, and by ``project_service.prepare``, which calls
the same two functions before persisting a generation run. Both call sites
need the identical translation from an engine exception to a problem-details
error, so it lives once here rather than in either caller.
"""

from __future__ import annotations

from app.core.errors import ConflictStateError, ValidationFailedError
from app.domain import ConflictReport, ConstraintBundle, ResolutionChoice, ResolvedBundle
from app.engines import resolution
from app.engines.conflict_detector import detect
from app.engines.errors import (
    EngineError,
    UnknownReferenceError,
    UnknownResolutionError,
    UnresolvedHardConflictError,
)
from app.kb.loader import KnowledgeBase


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
