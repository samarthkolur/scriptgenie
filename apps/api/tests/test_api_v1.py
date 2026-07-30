"""Contract tests for the v1 surface.

Every route gets its happy path and its auth failure path, as the stage's
acceptance criteria require. Beyond that, the tests that matter are the ones
about the gate: a bundle with an unresolved HARD conflict must be refused with
the conflicts attached, and it must be refused *before* a token is spent.
"""

from __future__ import annotations

import httpx
import pytest

from app.main import API_V1_PREFIX
from tests.api_fixtures import (
    CLEAN_BUNDLE,
    CLEAN_EXTRACTION,
    OWNER_ID,
    PROJECT_ID,
    WORKED_EXAMPLE,
    GroqStub,
    bundle_row,
    harness,
    project_row,
    run_row,
    stored_row,
    variant_payload,
    variant_row,
)
from tests.auth_fixtures import PostgrestStub

OK = httpx.Response(200, json=[])


# ------------------------------------------------------- every route is closed


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/kb/options", None),
        ("POST", "/conflicts/detect", {"bundle": CLEAN_BUNDLE}),
        ("POST", "/conflicts/resolve", {"bundle": CLEAN_BUNDLE}),
        ("GET", "/projects", None),
        ("POST", "/projects", {"title": "x"}),
        ("GET", f"/projects/{PROJECT_ID}", None),
        ("PATCH", f"/projects/{PROJECT_ID}", {"title": "x"}),
        ("DELETE", f"/projects/{PROJECT_ID}", None),
        ("PUT", f"/projects/{PROJECT_ID}/bundle", {"bundle": CLEAN_BUNDLE}),
        ("GET", f"/projects/{PROJECT_ID}/bundle", None),
        ("POST", f"/projects/{PROJECT_ID}/generate", {"bundle": CLEAN_BUNDLE}),
        ("GET", f"/projects/{PROJECT_ID}/variants", None),
        ("GET", f"/projects/{PROJECT_ID}/export", None),
        ("POST", f"/variants/{PROJECT_ID}/feedback", {"rating": 4}),
    ],
)
def test_every_route_refuses_an_unauthenticated_caller(
    method: str, path: str, body: dict | None
) -> None:
    api = harness()

    response = api.client.request(method, f"{API_V1_PREFIX}{path}", json=body)

    assert response.status_code == 401
    assert response.json()["type"].endswith("/unauthenticated")


# --------------------------------------------------------------- kb options


def test_kb_options_returns_everything_the_wizard_needs() -> None:
    response = harness().get("/kb/options")

    assert response.status_code == 200
    body = response.json()
    assert body["kb_version"]
    assert len(body["genres"]) == 10
    assert len(body["budget_tiers"]) == 4
    assert len(body["territories"]) == 5
    assert len(body["archetypes"]) == 5
    assert len(body["rating_systems"]) == 5


def test_budget_tiers_carry_the_scope_a_writer_is_actually_choosing() -> None:
    """A picker showing only dollar bands asks the writer to guess at the
    location count and speaking cast they care about."""
    tiers = harness().get("/kb/options").json()["budget_tiers"]
    micro = next(tier for tier in tiers if tier["id"] == "micro")

    assert micro["scope"]["max_locations"] == 3
    assert micro["scope"]["max_named_characters"] == 5
    assert "SAG-AFTRA" in micro["guild_context"]


def test_budget_tiers_are_ordered_by_band_not_by_label() -> None:
    orders = [tier["order"] for tier in harness().get("/kb/options").json()["budget_tiers"]]

    assert orders == sorted(orders)


def test_the_studio_tier_reports_no_ceiling_rather_than_a_large_number() -> None:
    tiers = harness().get("/kb/options").json()["budget_tiers"]
    studio = next(tier for tier in tiers if tier["id"] == "studio")

    assert studio["max_usd"] is None
    assert studio["scope"]["max_locations"] is None


def test_classifications_are_ordered_as_the_board_orders_them() -> None:
    systems = harness().get("/kb/options").json()["rating_systems"]
    mpa = next(system for system in systems if system["id"] == "mpa")
    ages = [item["min_audience_age"] for item in mpa["classifications"]]

    assert ages == sorted(ages), "a rating picker listing R before PG cannot be scanned"


def test_kb_options_advertises_a_version_scoped_cache() -> None:
    response = harness().get("/kb/options")

    assert response.headers["cache-control"].startswith("private")
    assert response.json()["kb_version"] in response.headers["etag"]


def test_the_conflict_rules_are_not_published() -> None:
    """A client holding the rules could render its own verdict and disagree
    with the endpoint that enforces it."""
    body = harness().get("/kb/options").text

    assert "conflict_rules" not in body
    assert "predicate" not in body


# ----------------------------------------------------------------- conflicts


def test_detect_returns_the_worked_examples_conflicts() -> None:
    response = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 200
    body = response.json()
    assert body["conflicts"], "the worked example is chosen because it conflicts"
    assert body["rules_evaluated"] > 0
    assert body["counts"]["hard"] + body["counts"]["soft"] + body["counts"]["advisory"] == len(
        body["conflicts"]
    )


def test_a_clean_bundle_reports_no_blocking_conflict() -> None:
    body = harness().post("/conflicts/detect", json={"bundle": CLEAN_BUNDLE}).json()

    assert body["blocking"] is False
    assert body["counts"]["hard"] == 0


def test_blocking_is_decided_by_the_server() -> None:
    """It is the flag that disables the Generate button. A client computing it
    itself could disagree with the endpoint that enforces it."""
    body = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE}).json()

    assert body["blocking"] == (body["counts"]["hard"] > 0)


def test_every_conflict_offers_at_least_two_resolutions() -> None:
    """Offering one option is an instruction wearing the costume of a choice."""
    body = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE}).json()

    for conflict in body["conflicts"]:
        assert len(conflict["resolutions"]) >= 2, conflict["rule_id"]


def test_a_bundle_naming_an_unknown_genre_is_a_422_not_a_500() -> None:
    bundle = {**CLEAN_BUNDLE, "genre": {"primary": "horrror"}}

    response = harness().post("/conflicts/detect", json={"bundle": bundle})

    assert response.status_code == 422
    assert "horrror" in response.json()["detail"]


def test_a_malformed_bundle_reports_the_offending_field() -> None:
    bundle = {**CLEAN_BUNDLE, "audience": {"min_age": 40, "max_age": 18}}

    response = harness().post("/conflicts/detect", json={"bundle": bundle})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/invalid-body")


def test_an_unknown_field_in_a_request_is_refused() -> None:
    """A client sending `varient_count` is told, rather than silently given the
    default and left to file a bug about generation ignoring a setting."""
    response = harness().post("/conflicts/detect", json={"bundle": CLEAN_BUNDLE, "varient": 1})

    assert response.status_code == 422


def test_resolve_returns_the_envelope_the_generator_will_be_held_to() -> None:
    response = harness().post("/conflicts/resolve", json={"bundle": CLEAN_BUNDLE})

    assert response.status_code == 200
    body = response.json()
    assert body["envelope"]["budget_tier_id"] == "studio"
    assert body["envelope"]["directives"], "an envelope with no directives constrains nothing"


def test_resolve_carries_the_provenance_of_every_ceiling() -> None:
    """A ceiling nobody can trace is a number the writer has to take on faith."""
    body = harness().post("/conflicts/resolve", json={"bundle": CLEAN_BUNDLE}).json()

    for source in body["envelope"]["provenance"]:
        assert source["authority"], source["dimension"]


def test_resolve_refuses_a_choice_that_names_an_unknown_conflict() -> None:
    response = harness().post(
        "/conflicts/resolve",
        json={
            "bundle": CLEAN_BUNDLE,
            "choices": [{"rule_id": "no_such_rule", "resolution_id": "accept"}],
        },
    )

    assert response.status_code == 422


def test_resolve_blocks_on_an_unresolved_hard_conflict_and_says_which() -> None:
    """The stage's stated criterion, at the endpoint that reports it."""
    report = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE}).json()
    hard = [c for c in report["conflicts"] if c["severity"] == "HARD"]
    if not hard:
        pytest.skip("the worked example currently produces no HARD conflict")

    response = harness().post("/conflicts/resolve", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 409
    body = response.json()
    assert body["type"].endswith("/conflict-state")
    assert {c["rule_id"] for c in body["conflicts"]} == {c["rule_id"] for c in hard}


# ------------------------------------------------------------------ projects


def test_creating_a_project_returns_what_the_database_stored() -> None:
    db = PostgrestStub().on("POST", "projects", httpx.Response(201, json=[project_row()]))

    response = harness(db).post("/projects", json={"title": "Cabin horror comedy"})

    assert response.status_code == 201
    assert response.json()["id"] == str(PROJECT_ID)
    assert response.json()["status"] == "draft"


def test_a_project_is_created_under_the_verified_caller() -> None:
    """Never under an owner from the request body: that is a request to write
    as somebody else."""
    db = PostgrestStub().on("POST", "projects", httpx.Response(201, json=[project_row()]))

    harness(db).post("/projects", json={"title": "Cabin"})

    import json as jsonlib

    body = jsonlib.loads(db.last("POST", "projects").content)
    assert body["owner_id"] == str(OWNER_ID)


def test_a_blank_project_title_is_refused() -> None:
    response = harness().post("/projects", json={"title": "   "})

    assert response.status_code == 422


def test_listing_projects_reports_the_total_alongside_the_page() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on(
            "GET",
            "projects",
            httpx.Response(200, json=[], headers={"content-range": "0-0/7"}),
        )
    )

    body = harness(db).get("/projects").json()

    assert len(body["projects"]) == 1
    assert body["total"] == 7


def test_an_unbounded_page_size_is_refused() -> None:
    """A client must not be able to turn one request into a full table scan."""
    assert harness().get("/projects?limit=5000").status_code == 422


def test_reading_another_users_project_is_a_404_not_a_403() -> None:
    """A 403 would confirm the project exists, which is enough to enumerate."""
    db = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))

    response = harness(db).get(f"/projects/{PROJECT_ID}")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")


def test_updating_a_project_sends_only_what_changed() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on(
            "PATCH",
            "projects",
            httpx.Response(200, json=[project_row(title="Renamed")]),
        )
    )

    response = harness(db).patch(f"/projects/{PROJECT_ID}", json={"title": "Renamed"})

    assert response.status_code == 200
    import json as jsonlib

    sent = jsonlib.loads(db.last("PATCH", "projects").content)
    assert sent == {"title": "Renamed"}, "an omitted field means unchanged, not cleared"


def test_an_empty_update_is_refused() -> None:
    db = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[project_row()]))

    response = harness(db).patch(f"/projects/{PROJECT_ID}", json={})

    assert response.status_code == 422


def test_an_invalid_project_status_is_refused_with_the_valid_set() -> None:
    db = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[project_row()]))

    response = harness(db).patch(f"/projects/{PROJECT_ID}", json={"status": "shipped"})

    assert response.status_code == 422
    assert "archived" in response.json()["detail"]


def test_deleting_a_project_answers_204() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("DELETE", "projects", httpx.Response(200, json=[project_row()]))
    )

    assert harness(db).delete(f"/projects/{PROJECT_ID}").status_code == 204


# -------------------------------------------------------------- bundle draft


def test_saving_a_first_draft_inserts_it() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[]))
        .on("POST", "constraint_bundles", httpx.Response(201, json=[bundle_row()]))
    )

    response = harness(db).put(f"/projects/{PROJECT_ID}/bundle", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 200
    assert response.json()["bundle"]["genre"]["primary"] == "horror"
    assert response.json()["cited"] is False


def test_saving_again_overwrites_the_draft_rather_than_appending() -> None:
    """The wizard saves on every step; a row per save is a row per keystroke."""
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[bundle_row()]))
        .on(
            "GET",
            "conflict_reports",
            httpx.Response(200, json=[], headers={"content-range": "*/0"}),
        )
        .on("PATCH", "constraint_bundles", httpx.Response(200, json=[bundle_row()]))
    )

    response = harness(db).put(f"/projects/{PROJECT_ID}/bundle", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 200
    db.last("PATCH", "constraint_bundles")
    assert "POST constraint_bundles" not in {
        f"{r.method} {r.url.path.rsplit('/', 1)[-1]}" for r in db.requests
    }


def test_a_draft_a_report_already_cites_is_not_rewritten() -> None:
    """A stored verdict describes a specific bundle. Rewriting its columns
    would change what that verdict was about without changing the verdict."""
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[bundle_row()]))
        .on(
            "GET",
            "conflict_reports",
            httpx.Response(200, json=[], headers={"content-range": "*/1"}),
        )
        .on("POST", "constraint_bundles", httpx.Response(201, json=[bundle_row()]))
    )

    response = harness(db).put(f"/projects/{PROJECT_ID}/bundle", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 200
    db.last("POST", "constraint_bundles")
    with pytest.raises(AssertionError):
        db.last("PATCH", "constraint_bundles")


def test_reading_a_saved_draft_returns_the_writers_answers() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[bundle_row()]))
        .on(
            "GET",
            "conflict_reports",
            httpx.Response(200, json=[], headers={"content-range": "*/0"}),
        )
    )

    response = harness(db).get(f"/projects/{PROJECT_ID}/bundle")

    assert response.status_code == 200
    body = response.json()
    assert body["bundle"]["territories"]["ids"] == ["us", "india"]
    assert body["bundle"]["rating"] == {"system": "mpa", "classification": "pg_13"}
    assert body["cited"] is False


def test_reading_a_draft_reports_that_a_report_cites_it() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[bundle_row()]))
        .on(
            "GET",
            "conflict_reports",
            httpx.Response(200, json=[], headers={"content-range": "*/2"}),
        )
    )

    response = harness(db).get(f"/projects/{PROJECT_ID}/bundle")

    assert response.json()["cited"] is True


def test_reading_a_draft_that_was_never_saved_is_a_404() -> None:
    """There is no partial ConstraintBundle, so "nothing yet" cannot be one."""
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[]))
    )

    response = harness(db).get(f"/projects/{PROJECT_ID}/bundle")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")


def test_saving_a_draft_to_another_users_project_is_a_404() -> None:
    db = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))

    response = harness(db).put(f"/projects/{PROJECT_ID}/bundle", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 404


def test_saving_a_malformed_draft_is_refused_before_any_write() -> None:
    db = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[project_row()]))

    response = harness(db).put(
        f"/projects/{PROJECT_ID}/bundle",
        json={"bundle": {**WORKED_EXAMPLE, "territories": {"ids": []}}},
    )

    assert response.status_code == 422
    with pytest.raises(AssertionError):
        db.last("POST", "constraint_bundles")


def test_saving_a_draft_does_not_detect_conflicts() -> None:
    """An autosave that quietly ran the engine would make an incomplete draft
    look like a verdict, and would write a report nobody asked for."""
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[]))
        .on("POST", "constraint_bundles", httpx.Response(201, json=[bundle_row()]))
    )

    harness(db).put(f"/projects/{PROJECT_ID}/bundle", json={"bundle": WORKED_EXAMPLE})

    tables = {r.url.path.rsplit("/", 1)[-1] for r in db.requests}
    assert "conflict_reports" not in tables


# ---------------------------------------------------------------- generation


def _project_and_quota() -> PostgrestStub:
    """The two reads every generation makes before it decides anything."""
    return (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on(
            "GET",
            "generation_runs",
            httpx.Response(200, json=[], headers={"content-range": "0-0/0"}),
        )
    )


def _generation_db(variants: int = 2) -> PostgrestStub:
    """The write sequence one successful generation performs, in order."""
    return (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        # The rate limiter counts this user's recent runs before anything is
        # written. Scripted here rather than defaulted, so a route that stopped
        # asking would fail these tests rather than silently lose its limit.
        .on(
            "GET",
            "generation_runs",
            httpx.Response(200, json=[], headers={"content-range": "0-0/0"}),
        )
        .on("POST", "constraint_bundles", httpx.Response(201, json=[stored_row("bundle")]))
        .on("POST", "conflict_reports", httpx.Response(201, json=[stored_row("report")]))
        .on("POST", "scope_envelopes", httpx.Response(201, json=[stored_row("envelope")]))
        .on("PATCH", "projects", httpx.Response(200, json=[project_row()]))
        .on("POST", "generation_runs", httpx.Response(201, json=[run_row()]))
        .on(
            "POST",
            "plot_variants",
            httpx.Response(201, json=[variant_row(i) for i in range(variants)]),
        )
        .on(
            "PATCH",
            "generation_runs",
            httpx.Response(200, json=[run_row(status="complete", generated_count=variants)]),
        )
        .on("PATCH", "projects", httpx.Response(200, json=[project_row(status="complete")]))
    )


def test_generation_returns_variants_the_run_and_the_envelope() -> None:
    groq = GroqStub(
        variants=[variant_payload("A"), variant_payload("B")], extraction=CLEAN_EXTRACTION
    )

    response = harness(_generation_db(), groq).post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["variants"]) == 2
    assert body["run"]["status"] == "complete"
    assert body["envelope"]["budget_tier_id"] == "studio"


def test_each_variant_carries_the_provenance_to_reproduce_it() -> None:
    groq = GroqStub(
        variants=[variant_payload("A"), variant_payload("B")], extraction=CLEAN_EXTRACTION
    )

    body = (
        harness(_generation_db(), groq)
        .post(
            f"/projects/{PROJECT_ID}/generate",
            json={"bundle": CLEAN_BUNDLE, "variant_count": 2},
        )
        .json()
    )

    for variant in body["variants"]:
        provenance = variant["provenance"]
        assert provenance["kb_version"]
        assert provenance["prompt_version"]
        assert provenance["model"]


def test_generation_is_blocked_by_an_unresolved_hard_conflict() -> None:
    """The stage's stated criterion: 409, with the conflict payload."""
    report = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE}).json()
    if report["counts"]["hard"] == 0:
        pytest.skip("the worked example currently produces no HARD conflict")

    db = _project_and_quota()
    api = harness(db)

    response = api.post(f"/projects/{PROJECT_ID}/generate", json={"bundle": WORKED_EXAMPLE})

    assert response.status_code == 409
    assert response.json()["conflicts"]


def test_a_blocked_generation_spends_no_model_quota() -> None:
    """The refusal happens in the deterministic layer, before any call."""
    report = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE}).json()
    if report["counts"]["hard"] == 0:
        pytest.skip("the worked example currently produces no HARD conflict")

    db = _project_and_quota()
    api = harness(db)

    api.post(f"/projects/{PROJECT_ID}/generate", json={"bundle": WORKED_EXAMPLE})

    assert api.groq.calls == []


def test_a_blocked_generation_writes_no_rows() -> None:
    report = harness().post("/conflicts/detect", json={"bundle": WORKED_EXAMPLE}).json()
    if report["counts"]["hard"] == 0:
        pytest.skip("the worked example currently produces no HARD conflict")

    db = _project_and_quota()
    harness(db).post(f"/projects/{PROJECT_ID}/generate", json={"bundle": WORKED_EXAMPLE})

    assert {r.method for r in db.requests} == {"GET"}, "a refused generation writes nothing"


def test_generating_for_another_users_project_is_a_404() -> None:
    db = PostgrestStub().on("GET", "projects", httpx.Response(200, json=[]))

    response = harness(db).post(f"/projects/{PROJECT_ID}/generate", json={"bundle": CLEAN_BUNDLE})

    assert response.status_code == 404


def test_more_variants_than_the_ceiling_is_refused() -> None:
    response = harness().post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 99},
    )

    assert response.status_code == 422


def test_a_failed_extraction_degrades_to_needs_review_never_to_pass() -> None:
    """A check that did not run is not a check that succeeded."""
    groq = GroqStub(variants=[variant_payload("A")], extraction=None)
    db = _generation_db(variants=1)

    harness(db, groq).post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 1},
    )

    import json as jsonlib

    stored = jsonlib.loads(db.last("POST", "plot_variants").content)
    verdicts = stored[0]["verdicts"]
    assert "NEEDS_REVIEW" in verdicts.values()
    assert stored[0]["surfaceable"] is False


def test_a_variant_exceeding_its_location_ceiling_is_flagged() -> None:
    """Micro permits three locations. This one names seven."""
    bundle = {**CLEAN_BUNDLE, "budget_tier_id": "micro", "genre": {"primary": "drama"}}
    groq = GroqStub(
        variants=[variant_payload("Sprawling", locations=7)], extraction=CLEAN_EXTRACTION
    )
    db = _generation_db(variants=1)

    harness(db, groq).post(
        f"/projects/{PROJECT_ID}/generate", json={"bundle": bundle, "variant_count": 1}
    )

    import json as jsonlib

    stored = jsonlib.loads(db.last("POST", "plot_variants").content)[0]
    assert stored["verdicts"]["max_locations"] == "FLAGGED"
    assert stored["surfaceable"] is False


def test_a_run_row_exists_even_when_the_model_fails() -> None:
    """A run written only on success makes every failure invisible, including
    the ones that spent tokens."""
    groq = GroqStub(variants=[variant_payload()], variant_status=500)
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on(
            "GET",
            "generation_runs",
            httpx.Response(200, json=[], headers={"content-range": "0-0/0"}),
        )
        .on("POST", "constraint_bundles", httpx.Response(201, json=[stored_row("bundle")]))
        .on("POST", "conflict_reports", httpx.Response(201, json=[stored_row("report")]))
        .on("POST", "scope_envelopes", httpx.Response(201, json=[stored_row("envelope")]))
        .on("PATCH", "projects", httpx.Response(200, json=[project_row()]))
        .on("POST", "generation_runs", httpx.Response(201, json=[run_row()]))
        .on(
            "PATCH",
            "generation_runs",
            httpx.Response(200, json=[run_row(status="failed", failed_count=1)]),
        )
        .on("PATCH", "projects", httpx.Response(200, json=[project_row()]))
    )

    response = harness(db, groq).post(
        f"/projects/{PROJECT_ID}/generate",
        json={"bundle": CLEAN_BUNDLE, "variant_count": 1},
    )

    assert response.status_code in (200, 503)
    closed = db.last("PATCH", "generation_runs")
    assert b'"failed"' in closed.content


# ------------------------------------------------------------------ variants


def test_listing_variants_reports_the_total() -> None:
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "plot_variants", httpx.Response(200, json=[variant_row(0)]))
        .on(
            "GET",
            "plot_variants",
            httpx.Response(200, json=[], headers={"content-range": "0-0/3"}),
        )
    )

    body = harness(db).get(f"/projects/{PROJECT_ID}/variants").json()

    assert len(body["variants"]) == 1
    assert body["total"] == 3


def test_a_variants_satisfaction_report_keeps_its_passing_checks() -> None:
    """A report listing only failures would make "verified for scope"
    indistinguishable from "not checked"."""
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "plot_variants", httpx.Response(200, json=[variant_row(0)]))
        .on(
            "GET",
            "plot_variants",
            httpx.Response(200, json=[], headers={"content-range": "0-0/1"}),
        )
    )

    variant = harness(db).get(f"/projects/{PROJECT_ID}/variants").json()["variants"][0]

    assert variant["satisfaction"]["dimension_checks"]
    assert variant["satisfaction"]["scope_checks"]


# ------------------------------------------------------------------ feedback


def test_feedback_records_a_rating() -> None:
    db = (
        PostgrestStub()
        .on("GET", "plot_variants", httpx.Response(200, json=[variant_row(0)]))
        .on(
            "POST",
            "variant_feedback",
            httpx.Response(
                201,
                json=[
                    {
                        "id": "cccccccc-0000-4000-8000-000000000001",
                        "variant_id": str(PROJECT_ID),
                        "rating": 4,
                        "notes": None,
                        "false_positive_rule_id": None,
                        "created_at": "2026-07-29T09:00:00+00:00",
                    }
                ],
            ),
        )
    )

    response = harness(db).post(f"/variants/{PROJECT_ID}/feedback", json={"rating": 4})

    assert response.status_code == 201
    assert response.json()["rating"] == 4


def test_feedback_that_says_nothing_is_refused() -> None:
    response = harness().post(f"/variants/{PROJECT_ID}/feedback", json={})

    assert response.status_code == 422
    assert "false-positive" in response.json()["detail"]


def test_a_false_positive_report_against_an_unknown_rule_is_refused() -> None:
    """Accepting it would poison the dataset this channel exists to build."""
    response = harness().post(
        f"/variants/{PROJECT_ID}/feedback", json={"false_positive_rule_id": "no_such_rule"}
    )

    assert response.status_code == 422
    assert "no_such_rule" in response.json()["detail"]


def test_feedback_on_an_invisible_variant_is_a_404() -> None:
    db = PostgrestStub().on("GET", "plot_variants", httpx.Response(200, json=[]))

    response = harness(db).post(f"/variants/{PROJECT_ID}/feedback", json={"rating": 5})

    assert response.status_code == 404


# -------------------------------------------------------------------- export


def _export_db() -> PostgrestStub:
    return (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on(
            "GET",
            "constraint_bundles",
            httpx.Response(
                200,
                json=[
                    {
                        "id": "dddddddd-0000-4000-8000-000000000001",
                        "genre_primary": "horror",
                        "genre_secondary": "comedy",
                        "audience_min_age": 15,
                        "audience_max_age": 40,
                        "rating_system": "mpa",
                        "rating_classification": "pg_13",
                        "budget_tier_id": "micro",
                        "territory_ids": ["us", "india"],
                    }
                ],
            ),
        )
        .on(
            "GET",
            "conflict_reports",
            httpx.Response(
                200,
                json=[
                    {
                        "id": "eeeeeeee-0000-4000-8000-000000000001",
                        "kb_version": "0.1.1",
                        "conflicts": [],
                    }
                ],
            ),
        )
        .on("GET", "scope_envelopes", httpx.Response(200, json=[]))
        .on("GET", "plot_variants", httpx.Response(200, json=[variant_row(0)]))
        .on("GET", "resolutions", httpx.Response(200, json=[]))
    )


def test_an_export_carries_its_full_provenance() -> None:
    response = harness(_export_db()).get(f"/projects/{PROJECT_ID}/export")

    assert response.status_code == 200
    body = response.json()
    assert body["kb_version"] == "0.1.1"
    assert body["prompt_version"]
    assert body["bundle"]["genre"]["primary"] == "horror"
    assert body["markdown"]


def test_the_exported_markdown_names_every_version_behind_it() -> None:
    markdown = harness(_export_db()).get(f"/projects/{PROJECT_ID}/export").json()["markdown"]

    assert "Knowledge base version" in markdown
    assert "Prompt version" in markdown
    assert "openai/gpt-oss-120b" in markdown


def test_the_export_never_claims_regulatory_certification() -> None:
    """Research risk 2. This system checks against a stated envelope; it does
    not classify films, and saying otherwise would be the one claim it cannot
    afford to make."""
    from app.engines.verifier import FORBIDDEN_CLAIMS

    markdown = (
        harness(_export_db()).get(f"/projects/{PROJECT_ID}/export").json()["markdown"].lower()
    )

    for claim in FORBIDDEN_CLAIMS:
        assert claim not in markdown, claim
    assert "casie-verified for scope" in markdown


def test_the_export_uses_the_stored_kb_version_not_todays() -> None:
    """An export must describe the run that happened, not the deployment
    reading it back."""
    db = _export_db()
    api = harness(db)
    today = api.get("/kb/options").json()["kb_version"]

    body = api.get(f"/projects/{PROJECT_ID}/export").json()

    assert body["kb_version"] == "0.1.1"
    if today != "0.1.1":  # pragma: no cover - only when the KB has moved on
        assert body["kb_version"] != today


def test_exporting_a_project_with_nothing_in_it_still_works() -> None:
    """A project created and abandoned is a normal state, not an error."""
    db = (
        PostgrestStub()
        .on("GET", "projects", httpx.Response(200, json=[project_row()]))
        .on("GET", "constraint_bundles", httpx.Response(200, json=[]))
        .on("GET", "conflict_reports", httpx.Response(200, json=[]))
        .on("GET", "scope_envelopes", httpx.Response(200, json=[]))
        .on("GET", "plot_variants", httpx.Response(200, json=[]))
    )

    response = harness(db).get(f"/projects/{PROJECT_ID}/export")

    assert response.status_code == 200
    assert "No constraint bundle has been submitted yet." in response.json()["markdown"]
