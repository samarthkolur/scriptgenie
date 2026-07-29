"""Turning stored rows and engine output into the published wire shapes.

Kept out of the routers so that "what a project looks like on the wire" is
decided in one place. A router that assembled its own response would drift from
the next router that assembled the same thing, and the OpenAPI document would
record both.

Nothing here reaches the database or the knowledge base. Given a row, it
produces a model; given a model, it produces the row's shape. That makes every
function testable without a transport.
"""

from __future__ import annotations

from uuid import UUID

from app.api.v1 import schemas
from app.db.supabase import JsonObject
from app.domain import ConflictReport


def project(row: JsonObject) -> schemas.Project:
    return schemas.Project(
        id=UUID(str(row["id"])),
        title=str(row["title"]),
        description=row.get("description"),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def conflict_report(report: ConflictReport) -> schemas.ConflictReportResponse:
    return schemas.ConflictReportResponse(
        kb_version=report.kb_version,
        bundle=report.bundle,
        conflicts=report.conflicts,
        counts=schemas.counts_from(report.conflicts),
        rules_evaluated=report.rules_evaluated,
        # Derived server-side. It is the flag that disables the Generate
        # button, and a client computing it itself could disagree with the
        # endpoint that enforces it.
        blocking=report.blocking,
    )


def variant(row: JsonObject) -> schemas.Variant:
    """A stored variant as the UI reads it.

    ``satisfaction`` and ``provenance`` are stored as JSONB and re-validated
    here rather than passed through. A row written by an older version of this
    service would otherwise reach a client as a shape the client's types say is
    impossible.
    """
    stored = row.get("satisfaction") or {}
    provenance = row.get("provenance") or {}

    return schemas.Variant(
        id=UUID(str(row["id"])),
        variant_index=int(row["variant_index"]),
        archetype_id=str(row["archetype_id"]),
        title=str(row["title"]),
        logline=str(row["logline"]),
        beats=tuple(schemas.BeatOut.model_validate(beat) for beat in row["beats"]),
        locations=tuple(row.get("locations") or ()),
        named_characters=tuple(row.get("named_characters") or ()),
        relaxations=tuple(row.get("relaxations") or ()),
        satisfaction=schemas.SatisfactionOut(
            dimension_checks=tuple(
                schemas.DimensionCheckOut.model_validate(check)
                for check in stored.get("dimension_checks", ())
            ),
            scope_checks=tuple(
                schemas.ScopeCheckOut.model_validate(check)
                for check in stored.get("scope_checks", ())
            ),
            satisfied=bool(stored.get("satisfied", False)),
            violations=tuple(stored.get("violations", ())),
        ),
        verdicts={str(k): str(v) for k, v in (row.get("verdicts") or {}).items()},
        surfaceable=bool(row.get("surfaceable", False)),
        favourite=bool(row.get("favourite", False)),
        notes=row.get("notes"),
        provenance=schemas.VariantProvenanceOut(
            kb_version=str(provenance.get("kb_version", "")),
            prompt_version=str(provenance.get("prompt_version", "")),
            model=str(provenance.get("model", "")),
            archetype_id=str(provenance.get("archetype_id", row["archetype_id"])),
            seed=int(provenance.get("seed", 0)),
            attempts=int(provenance.get("attempts", 0)),
            repaired=bool(provenance.get("repaired", False)),
        ),
        created_at=row["created_at"],
    )


def generation_run(row: JsonObject) -> schemas.GenerationRun:
    return schemas.GenerationRun(
        id=UUID(str(row["id"])),
        project_id=UUID(str(row["project_id"])),
        status=str(row["status"]),
        requested_count=int(row["requested_count"]),
        generated_count=int(row["generated_count"]),
        failed_count=int(row["failed_count"]),
        seed=int(row["seed"]),
        model=str(row["model"]),
        prompt_version=str(row["prompt_version"]),
        kb_version=str(row["kb_version"]),
        elapsed_ms=row.get("elapsed_ms"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )


def feedback(row: JsonObject) -> schemas.Feedback:
    return schemas.Feedback(
        id=UUID(str(row["id"])),
        variant_id=UUID(str(row["variant_id"])),
        rating=row.get("rating"),
        notes=row.get("notes"),
        false_positive_rule_id=row.get("false_positive_rule_id"),
        created_at=row["created_at"],
    )
