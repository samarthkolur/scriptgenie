"""Projects: the container a bundle, its conflicts and its variants belong to.

Thin by design. Each handler resolves the project, delegates, and shapes a
response; the pipeline lives in :mod:`app.services.project_service` and the
queries in :mod:`app.db.repositories`.

Every handler that names a project id goes through :func:`_require_project`.
Not for tidiness — the row level security policies mean a project belonging to
somebody else simply is not there, so the check is a single lookup that turns
absence into a 404. A handler that skipped it would still be safe and would
report the failure as something confusing three calls later.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AppSettings, Db, Groq, Kb
from app.api.v1 import presenters, schemas
from app.core import usage
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.security import AuthenticatedUser, CurrentUser
from app.db import repositories
from app.db.supabase import JsonObject, SupabaseClient
from app.domain import ResolutionChoice
from app.services import export_service, project_service
from app.services.rate_limit import enforce_generation_limit, record_generation_usage

router = APIRouter(prefix="/projects", tags=["projects"])

#: Bounded so a client cannot ask for an unbounded page and turn one request
#: into a full table scan.
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]

VALID_STATUSES = {"draft", "resolving", "generating", "complete", "archived"}


async def _require_project(
    db: SupabaseClient, user: AuthenticatedUser, project_id: UUID
) -> JsonObject:
    """The project, or a 404.

    "No such project" and "not your project" are the same answer on purpose.
    Distinguishing them would let anyone confirm the existence of another
    user's project by watching for a 403.
    """
    row = await repositories.get_project(db, user, project_id)
    if row is None:
        raise NotFoundError(f"no project '{project_id}'")
    return row


# --------------------------------------------------------------------- CRUD


@router.post(
    "",
    response_model=schemas.Project,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
async def create_project(
    request: schemas.ProjectCreate, user: CurrentUser, db: Db
) -> schemas.Project:
    row = await repositories.create_project(
        db, user, title=request.title, description=request.description
    )
    return presenters.project(row)


@router.get("", response_model=schemas.ProjectList, summary="List your projects")
async def list_projects(
    user: CurrentUser,
    db: Db,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> schemas.ProjectList:
    rows = await repositories.list_projects(db, user, limit=limit, offset=offset)
    total = await repositories.count_projects(db, user)
    return schemas.ProjectList(projects=tuple(presenters.project(row) for row in rows), total=total)


@router.get("/{project_id}", response_model=schemas.Project, summary="Read one project")
async def read_project(project_id: UUID, user: CurrentUser, db: Db) -> schemas.Project:
    return presenters.project(await _require_project(db, user, project_id))


@router.patch("/{project_id}", response_model=schemas.Project, summary="Update a project")
async def update_project(
    project_id: UUID, request: schemas.ProjectUpdate, user: CurrentUser, db: Db
) -> schemas.Project:
    await _require_project(db, user, project_id)

    # Only what was sent. `exclude_unset` is what makes an omitted title mean
    # "leave it alone" rather than "clear it".
    values = request.model_dump(exclude_unset=True)
    if not values:
        raise ValidationFailedError("no fields were supplied to update")
    if "status" in values and values["status"] not in VALID_STATUSES:
        raise ValidationFailedError(
            f"'{values['status']}' is not a project status; "
            f"expected one of {sorted(VALID_STATUSES)}"
        )

    row = await repositories.update_project(db, user, project_id, values)
    if row is None:  # pragma: no cover - the project was proved to exist above
        raise NotFoundError(f"no project '{project_id}'")
    return presenters.project(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a project")
async def delete_project(project_id: UUID, user: CurrentUser, db: Db) -> Response:
    await _require_project(db, user, project_id)
    await repositories.delete_project(db, user, project_id)
    # Its bundles, reports, envelopes, runs and variants go with it by cascade.
    # The usage_events rows do not: deleting a project must not erase the record
    # that its generation spent tokens.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------- generation


@router.post(
    "/{project_id}/generate",
    response_model=schemas.GenerationResponse,
    summary="Generate plot variants for a resolved bundle",
)
async def generate(
    project_id: UUID,
    request: schemas.GenerateRequest,
    user: CurrentUser,
    db: Db,
    kb: Kb,
    groq: Groq,
    settings: AppSettings,
) -> schemas.GenerationResponse:
    """Run the pipeline. Blocked while any HARD conflict is unresolved.

    The order is the design. The rate limit is checked first, so an over-quota
    caller is refused for the cost of one counting query — no rows written, no
    tokens spent. The bundle is then detected and resolved, which is
    deterministic and free and is the step that raises 409 with the blocking
    conflicts attached, so a bundle that cannot legally be generated never
    reaches the model either.
    """
    await _require_project(db, user, project_id)
    await enforce_generation_limit(db, user, settings)

    prepared = await project_service.prepare(db, user, kb, project_id, request)

    await repositories.set_project_status(db, user, project_id, "generating")

    # Every model call made inside this block — N variants plus N verification
    # extractions — accumulates into one meter, so the accounting row totals
    # the run rather than whichever call happened to be last.
    with usage.measured() as meter:
        response = await project_service.run_generation(
            db, user, kb, groq, project_id, request, prepared
        )

    await record_generation_usage(
        db,
        user,
        project_id,
        response,
        prompt_tokens=meter.prompt_tokens,
        completion_tokens=meter.completion_tokens,
        cost_usd=meter.cost_usd,
    )
    return response


@router.get(
    "/{project_id}/variants",
    response_model=schemas.VariantList,
    summary="List a project's generated variants",
)
async def list_variants(
    project_id: UUID,
    user: CurrentUser,
    db: Db,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> schemas.VariantList:
    await _require_project(db, user, project_id)
    rows = await repositories.list_variants(db, user, project_id, limit=limit, offset=offset)
    total = await repositories.count_variants(db, user, project_id)
    return schemas.VariantList(variants=tuple(presenters.variant(row) for row in rows), total=total)


# -------------------------------------------------------------------- export


@router.get(
    "/{project_id}/export",
    response_model=schemas.ExportBundle,
    summary="Export a project with its full provenance",
)
async def export_project(
    project_id: UUID, user: CurrentUser, db: Db, kb: Kb
) -> schemas.ExportBundle:
    """The project as JSON and Markdown, with everything behind it.

    Both formats in one response rather than two endpoints, because they are
    two renderings of one document and returning them together is what
    guarantees they cannot disagree.
    """
    from datetime import UTC, datetime

    from app.engines import prompt_builder

    project_row = await _require_project(db, user, project_id)

    bundle_row = await repositories.latest_bundle(db, user, project_id)
    report_row = await repositories.latest_report(db, user, project_id)
    envelope_row = await repositories.latest_envelope(db, user, project_id)
    variant_rows = await repositories.list_variants(db, user, project_id, limit=100, offset=0)

    bundle = repositories.bundle_from_row(bundle_row) if bundle_row is not None else None
    conflicts = repositories.conflicts_from_row(report_row) if report_row is not None else ()
    envelope = repositories.envelope_from_row(envelope_row) if envelope_row is not None else None
    variants = tuple(presenters.variant(row) for row in variant_rows)

    choices: tuple[ResolutionChoice, ...] = ()
    if report_row is not None:
        stored = await repositories.resolutions_for_report(db, user, UUID(str(report_row["id"])))
        choices = tuple(
            ResolutionChoice(rule_id=str(row["rule_id"]), resolution_id=str(row["resolution_id"]))
            for row in stored
        )

    project = presenters.project(project_row)
    # The knowledge base version comes from the stored report, not from the one
    # loaded today. An export must describe the run that happened.
    kb_version = str(report_row["kb_version"]) if report_row is not None else kb.version

    return schemas.ExportBundle(
        exported_at=datetime.now(UTC),
        project=project,
        kb_version=kb_version,
        prompt_version=prompt_builder.prompt_version(),
        bundle=bundle,
        conflicts=conflicts,
        choices=choices,
        envelope=envelope,
        variants=variants,
        markdown=export_service.render_markdown(
            project=project,
            kb_version=kb_version,
            prompt_version=prompt_builder.prompt_version(),
            bundle=bundle,
            conflicts=conflicts,
            choices=choices,
            envelope=envelope,
            variants=variants,
        ),
    )
