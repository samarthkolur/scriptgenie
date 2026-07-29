"""Exporting a project as a self-contained, defensible document.

An export that listed only loglines would be a set of pitches nobody could
defend. What makes these concepts worth anything is the chain behind them: the
constraints the writer stated, the tensions detected between them, what they
chose, the bounds that produced, and the versions of the knowledge base, the
prompt and the model that turned those bounds into pages. All of it travels
with the export.

The Markdown is rendered here rather than in the browser so that the exported
document and the JSON cannot disagree, and so an export is reproducible from
the API alone.

The wording is bounded by research risk 2: this system says a variant was
**checked against a stated envelope**, never that it was cleared by a ratings
board. ``FORBIDDEN_CLAIMS`` in ``app.engines.verifier`` lists the phrasings
that would overclaim, and the tests assert this renderer uses none of them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.v1 import schemas
from app.domain import Conflict, ConstraintBundle, GenerationEnvelope, ResolutionChoice
from app.engines.verifier import VERIFIED_LANGUAGE


def render_markdown(
    *,
    project: schemas.Project,
    kb_version: str,
    prompt_version: str,
    bundle: ConstraintBundle | None,
    conflicts: tuple[Conflict, ...],
    choices: tuple[ResolutionChoice, ...],
    envelope: GenerationEnvelope | None,
    variants: tuple[schemas.Variant, ...],
) -> str:
    """The project as one Markdown document."""
    lines: list[str] = [f"# {project.title}", ""]
    if project.description:
        lines += [project.description, ""]

    lines += _provenance_section(project, kb_version, prompt_version, variants)
    lines += _constraints_section(bundle)
    lines += _conflicts_section(conflicts, choices)
    lines += _envelope_section(envelope)
    lines += _variants_section(variants)
    lines += [
        "---",
        "",
        "ScriptGenie checks each variant against the production and content "
        "envelope recorded above. It is a pre-development ideation tool: it "
        "produces beat-level concepts, not screenplays, and it does not "
        "classify films. Classification is the business of CARA, BBFC, CBFC "
        "and FSK.",
        "",
    ]
    return "\n".join(lines)


def _provenance_section(
    project: schemas.Project,
    kb_version: str,
    prompt_version: str,
    variants: tuple[schemas.Variant, ...],
) -> list[str]:
    # The model is read from the variants rather than from configuration: an
    # export must name the model that produced *these* concepts, not whichever
    # model the service is set to today.
    models = sorted({variant.provenance.model for variant in variants if variant.provenance.model})
    return [
        "## Provenance",
        "",
        f"- Exported: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- Project created: {project.created_at.isoformat(timespec='seconds')}",
        f"- Knowledge base version: `{kb_version}`",
        f"- Prompt version: `{prompt_version}`",
        f"- Model: {', '.join(f'`{model}`' for model in models) if models else 'none recorded'}",
        "",
    ]


def _constraints_section(bundle: ConstraintBundle | None) -> list[str]:
    if bundle is None:
        return ["## Constraints", "", "No constraint bundle has been submitted yet.", ""]

    genre = bundle.genre.primary
    if bundle.genre.secondary is not None:
        genre += f" / {bundle.genre.secondary}"

    return [
        "## Constraints",
        "",
        "| Constraint | Value |",
        "| --- | --- |",
        f"| Genre | {genre} |",
        f"| Audience | {bundle.audience.min_age} to {bundle.audience.max_age} |",
        f"| Rating target | {bundle.rating.qualified} |",
        f"| Budget tier | {bundle.budget_tier_id} |",
        f"| Territories | {', '.join(bundle.territories.ids)} |",
        "",
    ]


def _conflicts_section(
    conflicts: tuple[Conflict, ...], choices: tuple[ResolutionChoice, ...]
) -> list[str]:
    if not conflicts:
        return [
            "## Detected conflicts",
            "",
            "None. Every constraint in this bundle is compatible with the others.",
            "",
        ]

    chosen = {choice.rule_id: choice.resolution_id for choice in choices}
    lines = ["## Detected conflicts", ""]
    for conflict in conflicts:
        lines += [
            f"### {conflict.title} — {conflict.severity.value}",
            "",
            conflict.explanation,
            "",
        ]
        if conflict.hard_rationale:
            lines += [f"> {conflict.hard_rationale}", ""]
        decision = chosen.get(conflict.rule_id)
        lines += [
            f"- Rule: `{conflict.rule_id}`",
            f"- Resolution chosen: {f'`{decision}`' if decision else 'none recorded'}",
            "",
        ]
    return lines


def _envelope_section(envelope: GenerationEnvelope | None) -> list[str]:
    if envelope is None:
        return []

    scope = envelope.scope
    lines = [
        "## Generation envelope",
        "",
        "The bounds every variant below was generated inside and checked against.",
        "",
        "| Parameter | Bound |",
        "| --- | --- |",
        f"| Locations | {_bound(scope.max_locations)} |",
        f"| Named characters | {_bound(scope.max_named_characters)} |",
        f"| VFX complexity | {scope.vfx_complexity.value} |",
        f"| Period setting | {scope.period_setting.value} |",
        f"| Action complexity | {scope.action_complexity.value} |",
        f"| Narrative economy | {scope.narrative_economy.value} |",
        "",
        "### Content ceilings",
        "",
        "| Dimension | Ceiling | Authority |",
        "| --- | --- | --- |",
    ]

    # Provenance is not decoration: a ceiling nobody can trace is a number the
    # writer has to take on faith.
    authorities = {source.dimension.value: source for source in envelope.provenance}
    for dimension, level in envelope.thresholds.model_dump().items():
        source = authorities.get(dimension)
        authority = source.authority if source is not None else "budget tier"
        lines.append(f"| {dimension.replace('_', ' ')} | {level} | {authority} |")
    lines.append("")

    if envelope.guidance:
        lines += ["### Guidance carried from resolutions", ""]
        lines += [f"- {item}" for item in envelope.guidance]
        lines.append("")
    return lines


def _variants_section(variants: tuple[schemas.Variant, ...]) -> list[str]:
    if not variants:
        return ["## Variants", "", "No variants have been generated yet.", ""]

    lines = ["## Variants", ""]
    for variant in variants:
        lines += [
            f"### {variant.title}",
            "",
            f"*{variant.logline}*",
            "",
            f"- Archetype: `{variant.archetype_id}`",
            f"- Verification: {_verification_label(variant)}",
            f"- Locations ({len(variant.locations)}): "
            f"{', '.join(variant.locations) or 'none enumerated'}",
            f"- Named characters ({len(variant.named_characters)}): "
            f"{', '.join(variant.named_characters) or 'none enumerated'}",
            "",
            "#### Beats",
            "",
        ]
        for beat in variant.beats:
            lines.append(f"{beat.index + 1}. **{beat.function}** — {beat.summary}")
        lines.append("")

        failed = [axis for axis, verdict in sorted(variant.verdicts.items()) if verdict != "PASS"]
        if failed:
            lines += ["#### Axes not cleared", ""]
            for axis in failed:
                lines.append(f"- `{axis}`: {variant.verdicts[axis]}")
            lines.append("")
        if variant.relaxations:
            lines += ["#### Relaxations the generator reported", ""]
            lines += [f"- {item}" for item in variant.relaxations]
            lines.append("")
    return lines


def _verification_label(variant: schemas.Variant) -> str:
    """What this system is permitted to say about its own output.

    Only a variant that passed every axis gets the verified phrasing. Anything
    with a FLAGGED or NEEDS_REVIEW axis is described as unresolved, because an
    axis nobody could check has not been checked.
    """
    if variant.surfaceable:
        return VERIFIED_LANGUAGE
    flagged = sum(1 for verdict in variant.verdicts.values() if verdict == "FLAGGED")
    unchecked = sum(1 for verdict in variant.verdicts.values() if verdict == "NEEDS_REVIEW")
    parts = []
    if flagged:
        parts.append(f"{flagged} axis/axes flagged")
    if unchecked:
        parts.append(f"{unchecked} axis/axes not checked")
    return "; ".join(parts) if parts else "not verified"


def _bound(value: int | None) -> str:
    """An absent ceiling reads as "no budget-imposed limit", never as a number.

    The studio tier genuinely has none, and inventing a large one would look
    like knowledge the knowledge base does not have.
    """
    return str(value) if value is not None else "no budget-imposed limit"
