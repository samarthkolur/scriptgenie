"""Tests for the exported document.

An export is the research artefact this system produces. What matters is not
that it renders, but that it renders the *provenance* — and that its wording
stays inside what the system is entitled to claim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.api.v1 import presenters, schemas
from app.db import repositories
from app.domain import ConstraintBundle, ResolutionChoice
from app.engines.conflict_detector import detect
from app.engines.resolution import apply_resolutions
from app.engines.scope_parameterizer import parameterize
from app.engines.verifier import FORBIDDEN_CLAIMS, VERIFIED_LANGUAGE
from app.kb.loader import load_knowledge_base
from app.services import export_service
from tests.api_fixtures import CLEAN_BUNDLE, PROJECT_ID, WORKED_EXAMPLE, variant_row


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


def _project(**overrides) -> schemas.Project:
    values = {
        "id": PROJECT_ID,
        "title": "Cabin horror comedy",
        "description": "A reunion weekend that nobody leaves.",
        "status": "complete",
        "created_at": datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return schemas.Project(**values)


def _render(kb, bundle_dict, *, variants=(), choices=()) -> str:
    bundle = ConstraintBundle.model_validate(bundle_dict)
    report = detect(bundle, kb)
    envelope = None
    if not report.blocking:
        envelope = parameterize(apply_resolutions(report, choices, kb), kb)
    return export_service.render_markdown(
        project=_project(),
        kb_version=kb.version,
        prompt_version="1.0.0",
        bundle=bundle,
        conflicts=report.conflicts,
        choices=choices,
        envelope=envelope,
        variants=variants,
    )


# ------------------------------------------------------------------ provenance


def test_the_export_names_every_version_that_shaped_it(kb) -> None:
    markdown = _render(kb, CLEAN_BUNDLE)

    assert f"`{kb.version}`" in markdown
    assert "`1.0.0`" in markdown
    assert "Project created: 2026-07-29" in markdown


def test_the_model_is_read_from_the_variants_not_from_configuration(kb) -> None:
    """An export must name the model that produced *these* concepts, not
    whichever model the service happens to be set to today."""
    variants = (presenters.variant(variant_row(0)),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert "openai/gpt-oss-120b" in markdown


def test_an_export_with_no_variants_says_so_rather_than_inventing_a_model(kb) -> None:
    markdown = _render(kb, CLEAN_BUNDLE)

    assert "Model: none recorded" in markdown
    assert "No variants have been generated yet." in markdown


# ----------------------------------------------------------------- constraints


def test_a_hybrid_genre_is_rendered_as_both_halves(kb) -> None:
    markdown = _render(kb, WORKED_EXAMPLE)

    assert "horror / comedy" in markdown


def test_the_rating_is_qualified_by_its_system(kb) -> None:
    """`u_a` means nothing without CBFC, so the two never travel apart."""
    markdown = _render(kb, WORKED_EXAMPLE)

    assert "mpa.pg_13" in markdown


def test_an_export_before_any_bundle_was_submitted_still_renders() -> None:
    markdown = export_service.render_markdown(
        project=_project(status="draft"),
        kb_version="0.1.1",
        prompt_version="1.0.0",
        bundle=None,
        conflicts=(),
        choices=(),
        envelope=None,
        variants=(),
    )

    assert "No constraint bundle has been submitted yet." in markdown


# ------------------------------------------------------------------- conflicts


def test_a_clean_bundle_states_that_nothing_conflicted(kb) -> None:
    """Stated, not left as an empty section. "No conflicts" and "not checked"
    must not look the same in a document someone is defending."""
    markdown = _render(kb, CLEAN_BUNDLE)

    assert "None. Every constraint in this bundle is compatible" in markdown


def test_every_detected_conflict_appears_with_its_severity(kb) -> None:
    bundle = ConstraintBundle.model_validate(WORKED_EXAMPLE)
    report = detect(bundle, kb)

    markdown = _render(kb, WORKED_EXAMPLE)

    for conflict in report.conflicts:
        assert conflict.title in markdown
        assert f"`{conflict.rule_id}`" in markdown
    assert "HARD" in markdown


def test_a_hard_conflict_carries_the_rationale_that_justifies_blocking(kb) -> None:
    """HARD blocks the work, so the burden of justification sits on the rule."""
    markdown = _render(kb, WORKED_EXAMPLE)
    report = detect(ConstraintBundle.model_validate(WORKED_EXAMPLE), kb)

    for conflict in report.conflicts:
        if conflict.hard_rationale:
            assert conflict.hard_rationale in markdown


def test_a_conflict_with_no_recorded_choice_says_so(kb) -> None:
    markdown = _render(kb, WORKED_EXAMPLE)

    assert "Resolution chosen: none recorded" in markdown


def test_a_recorded_choice_is_named_against_its_conflict(kb) -> None:
    bundle = ConstraintBundle.model_validate(WORKED_EXAMPLE)
    report = detect(bundle, kb)
    conflict = report.conflicts[0]
    choice = ResolutionChoice(rule_id=conflict.rule_id, resolution_id=conflict.resolutions[0].id)

    markdown = export_service.render_markdown(
        project=_project(),
        kb_version=kb.version,
        prompt_version="1.0.0",
        bundle=bundle,
        conflicts=report.conflicts,
        choices=(choice,),
        envelope=None,
        variants=(),
    )

    assert f"Resolution chosen: `{choice.resolution_id}`" in markdown


# -------------------------------------------------------------------- envelope


def test_the_envelope_section_names_the_authority_behind_each_ceiling(kb) -> None:
    """Provenance is not decoration: a ceiling nobody can trace is a number the
    writer has to take on faith."""
    bundle = ConstraintBundle.model_validate(CLEAN_BUNDLE)
    report = detect(bundle, kb)
    envelope = parameterize(apply_resolutions(report, (), kb), kb)

    markdown = _render(kb, CLEAN_BUNDLE)

    assert "| Dimension | Ceiling | Authority |" in markdown
    for source in envelope.provenance:
        assert source.authority in markdown


def test_an_unbounded_tier_reads_as_having_no_limit_not_as_a_number(kb) -> None:
    """The studio tier genuinely has no budget-imposed ceiling, and inventing a
    large one would look like knowledge the knowledge base does not have."""
    markdown = _render(kb, CLEAN_BUNDLE)

    assert "no budget-imposed limit" in markdown


def test_a_bounded_tier_reports_its_actual_numbers(kb) -> None:
    micro = {**CLEAN_BUNDLE, "budget_tier_id": "micro"}

    markdown = _render(kb, micro)

    assert "| Locations | 3 |" in markdown
    assert "| Named characters | 5 |" in markdown


# -------------------------------------------------------------------- variants


def test_a_variant_renders_its_beats_in_order(kb) -> None:
    variants = (presenters.variant(variant_row(0)),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert "1. **setup** — They arrive at the cabin." in markdown
    assert "2. **turn** — The road out is gone." in markdown


def test_a_fully_passing_variant_gets_the_verified_phrasing(kb) -> None:
    variants = (presenters.variant(variant_row(0)),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert VERIFIED_LANGUAGE in markdown


def test_a_flagged_variant_names_the_axis_rather_than_claiming_verification(kb) -> None:
    row = variant_row(
        0, surfaceable=False, verdicts={"max_locations": "FLAGGED", "violence": "PASS"}
    )
    variants = (presenters.variant(row),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert VERIFIED_LANGUAGE not in markdown
    assert "axis/axes flagged" in markdown
    assert "`max_locations`: FLAGGED" in markdown


def test_an_unchecked_axis_is_reported_as_unchecked_not_as_passing(kb) -> None:
    """A check that did not run is not a check that succeeded."""
    row = variant_row(
        0, surfaceable=False, verdicts={"violence": "NEEDS_REVIEW", "max_locations": "PASS"}
    )
    variants = (presenters.variant(row),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert "axis/axes not checked" in markdown
    assert "`violence`: NEEDS_REVIEW" in markdown


def test_a_variant_with_no_verdicts_at_all_is_not_called_verified(kb) -> None:
    row = variant_row(0, surfaceable=False, verdicts={})
    variants = (presenters.variant(row),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert "Verification: not verified" in markdown


def test_relaxations_the_generator_reported_are_carried_through(kb) -> None:
    row = variant_row(0, relaxations=["reduced to a single interior to stay inside scope"])
    variants = (presenters.variant(row),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert "Relaxations the generator reported" in markdown
    assert "single interior" in markdown


def test_a_variant_enumerating_nothing_says_so(kb) -> None:
    row = variant_row(0, locations=[], named_characters=[])
    variants = (presenters.variant(row),)

    markdown = _render(kb, CLEAN_BUNDLE, variants=variants)

    assert "Locations (0): none enumerated" in markdown
    assert "Named characters (0): none enumerated" in markdown


# ----------------------------------------------------------------- the wording


def test_the_export_never_overclaims(kb) -> None:
    """Research risk 2. Classification is the business of CARA, BBFC, CBFC and
    FSK; this system checks against a stated envelope and says only that."""
    variants = (presenters.variant(variant_row(0)),)

    markdown = _render(kb, WORKED_EXAMPLE, variants=variants).lower()

    for claim in FORBIDDEN_CLAIMS:
        assert claim not in markdown, claim


def test_the_export_states_what_the_tool_is(kb) -> None:
    markdown = _render(kb, CLEAN_BUNDLE)

    assert "pre-development ideation tool" in markdown
    assert "not screenplays" in markdown
    assert "it does not classify films" in markdown


# ------------------------------------------------------------- rehydration


def test_a_stored_bundle_round_trips(kb) -> None:
    """A row can also have been written by a migration or a support query, so
    it is validated on the way back rather than trusted."""
    row = {
        "genre_primary": "horror",
        "genre_secondary": "comedy",
        "audience_min_age": 15,
        "audience_max_age": 40,
        "rating_system": "mpa",
        "rating_classification": "pg_13",
        "budget_tier_id": "micro",
        "territory_ids": ["us", "india"],
    }

    bundle = repositories.bundle_from_row(row)

    assert bundle == ConstraintBundle.model_validate(WORKED_EXAMPLE)


def test_a_stored_bundle_without_a_secondary_genre_round_trips() -> None:
    row = {
        "genre_primary": "drama",
        "genre_secondary": None,
        "audience_min_age": 18,
        "audience_max_age": 60,
        "rating_system": "mpa",
        "rating_classification": "r",
        "budget_tier_id": "studio",
        "territory_ids": ["us"],
    }

    assert repositories.bundle_from_row(row).genre.secondary is None


def test_a_corrupt_stored_bundle_fails_at_the_boundary() -> None:
    row = {
        "genre_primary": "drama",
        "genre_secondary": None,
        "audience_min_age": 60,
        "audience_max_age": 18,
        "rating_system": "mpa",
        "rating_classification": "r",
        "budget_tier_id": "studio",
        "territory_ids": ["us"],
    }

    with pytest.raises(ValueError, match="below min_age"):
        repositories.bundle_from_row(row)


def test_a_stored_variant_rehydrates_into_the_domain_model() -> None:
    variant = repositories.variant_from_row(variant_row(0))

    assert variant.title == "Variant 0"
    assert [beat.index for beat in variant.beats] == [0, 1]


def test_a_stored_conflict_report_rehydrates_its_conflicts(kb) -> None:
    report = detect(ConstraintBundle.model_validate(WORKED_EXAMPLE), kb)
    row = {"conflicts": [c.model_dump(mode="json") for c in report.conflicts]}

    assert repositories.conflicts_from_row(row) == report.conflicts


def test_a_report_row_with_no_conflicts_rehydrates_to_an_empty_tuple() -> None:
    assert repositories.conflicts_from_row({"conflicts": None}) == ()


def test_a_stored_envelope_rehydrates(kb) -> None:
    bundle = ConstraintBundle.model_validate(CLEAN_BUNDLE)
    envelope = parameterize(apply_resolutions(detect(bundle, kb), (), kb), kb)
    row = {"envelope": envelope.model_dump(mode="json")}

    assert repositories.envelope_from_row(row) == envelope


def test_saving_no_resolutions_writes_nothing() -> None:
    """An empty insert is a request PostgREST rejects, and a bundle with no
    conflicts genuinely has no choices to record."""
    import asyncio

    from app.core.security import AuthenticatedUser

    user = AuthenticatedUser(id=uuid4(), email=None, role="authenticated", access_token="t")

    async def run():
        # A client that would fail if called at all: the assertion is that it
        # is not called.
        return await repositories.save_resolutions(
            None,
            user,
            PROJECT_ID,
            uuid4(),
            (),
            (),  # type: ignore[arg-type]
        )

    assert asyncio.run(run()) == []
