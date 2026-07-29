"""Feedback on a generated variant.

Small endpoint, and the most important one for the research.

Risk 1 in the analysis is that the rule set flags tensions working writers do
not recognise. A tool with no channel for "this conflict is wrong" cannot
distinguish a rule that is genuinely useful from one that users have learned to
click past, and the knowledge base would keep the bad rule indefinitely because
nothing ever contradicted it. ``false_positive_rule_id`` is that channel, and
it names the rule rather than the variant so the evidence points at the thing
that would have to change.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import Db, Kb
from app.api.v1 import presenters, schemas
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.security import CurrentUser
from app.db import repositories

router = APIRouter(prefix="/variants", tags=["variants"])


@router.post(
    "/{variant_id}/feedback",
    response_model=schemas.Feedback,
    status_code=status.HTTP_201_CREATED,
    summary="Rate a variant, annotate it, or report a rule as a false positive",
)
async def submit_feedback(
    variant_id: UUID,
    request: schemas.FeedbackRequest,
    user: CurrentUser,
    db: Db,
    kb: Kb,
) -> schemas.Feedback:
    if request.rating is None and request.notes is None and request.false_positive_rule_id is None:
        # The database enforces this too. Checking here as well means the user
        # gets a sentence explaining what feedback needs, rather than a
        # constraint name from PostgREST.
        raise ValidationFailedError(
            "feedback must carry a rating, a note, or a false-positive report"
        )

    if request.false_positive_rule_id is not None:
        # A report against a rule that does not exist is unusable evidence, and
        # accepting it would quietly poison the very dataset this channel is
        # for. The knowledge base is the authority on what rules there are.
        try:
            kb.conflict_rule(request.false_positive_rule_id)
        except KeyError as exc:
            raise ValidationFailedError(
                f"no conflict rule '{request.false_positive_rule_id}' exists "
                f"in knowledge base {kb.version}"
            ) from exc

    if await repositories.get_variant(db, user, variant_id) is None:
        raise NotFoundError(f"no variant '{variant_id}'")

    row = await repositories.save_feedback(
        db,
        user,
        variant_id,
        rating=request.rating,
        notes=request.notes,
        false_positive_rule_id=request.false_positive_rule_id,
    )
    return presenters.feedback(row)
