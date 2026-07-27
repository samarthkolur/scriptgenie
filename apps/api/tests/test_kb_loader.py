"""Tests for knowledge base loading, schema validation and integrity checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.kb.errors import (
    KnowledgeBaseFileError,
    KnowledgeBaseIntegrityError,
    KnowledgeBaseValidationError,
)
from app.kb.loader import load_knowledge_base
from tests import kb_fixtures


@pytest.fixture
def kb_root(tmp_path: Path) -> Path:
    return kb_fixtures.write_knowledge_base(tmp_path / "kb")


class TestHappyPath:
    def test_loads_every_collection(self, kb_root: Path) -> None:
        kb = load_knowledge_base(kb_root)

        assert kb.version == "0.1.0"
        assert len(kb.budget_tiers) == 4
        assert len(kb.genres) == 10
        assert len(kb.territories) == 5
        assert len(kb.archetypes) == 5
        assert len(kb.rating_systems) == 4
        assert len(kb.conflict_rules) == 1
        assert len(kb.rating_equivalences) == 1

    def test_lookup_helpers_return_records(self, kb_root: Path) -> None:
        kb = load_knowledge_base(kb_root)

        assert kb.budget_tier("micro")["order"] == 0
        assert kb.genre("horror")["label"] == "Horror"
        assert kb.territory("india")["regulator"] == "synthetic regulator"
        assert kb.archetype("crucible")["min_beats"] == 5
        assert kb.classification("system_0", "class_2")["min_audience_age"] == 8

    def test_unknown_lookup_raises_key_error_naming_the_kind(self, kb_root: Path) -> None:
        kb = load_knowledge_base(kb_root)

        with pytest.raises(KeyError, match="unknown budget tier"):
            kb.budget_tier("nonexistent")
        with pytest.raises(KeyError, match="unknown classification"):
            kb.classification("system_0", "nonexistent")

    def test_snapshot_is_immutable(self, kb_root: Path) -> None:
        kb = load_knowledge_base(kb_root)

        with pytest.raises(AttributeError):
            kb.version = "9.9.9"  # type: ignore[misc]


class TestFileFailures:
    def test_missing_version_file(self, kb_root: Path) -> None:
        (kb_root / "VERSION").unlink()

        with pytest.raises(KnowledgeBaseFileError, match="is missing"):
            load_knowledge_base(kb_root)

    def test_empty_version_file(self, kb_root: Path) -> None:
        (kb_root / "VERSION").write_text("\n", encoding="utf-8")

        with pytest.raises(KnowledgeBaseFileError, match="is empty"):
            load_knowledge_base(kb_root)

    def test_missing_data_file(self, kb_root: Path) -> None:
        (kb_root / "data" / "genres.json").unlink()

        with pytest.raises(KnowledgeBaseFileError, match=r"genres\.json.*is missing"):
            load_knowledge_base(kb_root)

    def test_malformed_json_reports_position(self, kb_root: Path) -> None:
        (kb_root / "data" / "genres.json").write_text("{ not json", encoding="utf-8")

        with pytest.raises(KnowledgeBaseFileError, match="not valid JSON"):
            load_knowledge_base(kb_root)

    def test_top_level_array_is_rejected(self, kb_root: Path) -> None:
        (kb_root / "data" / "genres.json").write_text("[]", encoding="utf-8")

        with pytest.raises(KnowledgeBaseFileError, match="JSON object at the top level"):
            load_knowledge_base(kb_root)


class TestSchemaValidation:
    def test_violation_names_file_and_json_pointer(self, kb_root: Path) -> None:
        payload = kb_fixtures.budget_tiers()
        payload["items"][0]["scope"]["max_locations"] = "three"
        kb_fixtures.rewrite(kb_root, "budget_tiers", payload)

        with pytest.raises(KnowledgeBaseValidationError) as excinfo:
            load_knowledge_base(kb_root)

        assert excinfo.value.pointer == "/items/0/scope/max_locations"
        assert "budget_tiers.json" in excinfo.value.path

    def test_content_level_above_scale_is_rejected(self, kb_root: Path) -> None:
        payload = kb_fixtures.genres()
        payload["items"][0]["content_demands"]["violence"] = 7
        kb_fixtures.rewrite(kb_root, "genres", payload)

        with pytest.raises(KnowledgeBaseValidationError) as excinfo:
            load_knowledge_base(kb_root)

        assert excinfo.value.pointer == "/items/0/content_demands/violence"

    def test_missing_citation_is_rejected(self, kb_root: Path) -> None:
        payload = kb_fixtures.budget_tiers()
        del payload["items"][2]["citations"]
        kb_fixtures.rewrite(kb_root, "budget_tiers", payload)

        with pytest.raises(KnowledgeBaseValidationError):
            load_knowledge_base(kb_root)

    def test_hard_rule_without_rationale_is_rejected(self, kb_root: Path) -> None:
        payload = kb_fixtures.conflict_rules()
        payload["items"][0]["severity"] = "HARD"
        kb_fixtures.rewrite(kb_root, "conflict_rules", payload)

        with pytest.raises(KnowledgeBaseValidationError) as excinfo:
            load_knowledge_base(kb_root)

        assert "hard_rationale" in excinfo.value.message

    def test_rule_with_a_single_resolution_is_rejected(self, kb_root: Path) -> None:
        payload = kb_fixtures.conflict_rules()
        payload["items"][0]["resolutions"] = payload["items"][0]["resolutions"][:1]
        kb_fixtures.rewrite(kb_root, "conflict_rules", payload)

        with pytest.raises(KnowledgeBaseValidationError) as excinfo:
            load_knowledge_base(kb_root)

        assert excinfo.value.pointer == "/items/0/resolutions"

    def test_archetype_with_four_beats_is_rejected(self, kb_root: Path) -> None:
        payload = kb_fixtures.archetypes()
        payload["items"][0]["structural_blueprint"] = payload["items"][0]["structural_blueprint"][
            :4
        ]
        kb_fixtures.rewrite(kb_root, "archetypes", payload)

        with pytest.raises(KnowledgeBaseValidationError):
            load_knowledge_base(kb_root)

    def test_unexpected_property_is_rejected(self, kb_root: Path) -> None:
        payload = kb_fixtures.genres()
        payload["items"][0]["vibe"] = "spooky"
        kb_fixtures.rewrite(kb_root, "genres", payload)

        with pytest.raises(KnowledgeBaseValidationError):
            load_knowledge_base(kb_root)


class TestIntegrity:
    def test_territory_referencing_unknown_rating_system(self, kb_root: Path) -> None:
        payload = kb_fixtures.territories()
        payload["items"][0]["rating_system"] = "system_missing"
        kb_fixtures.rewrite(kb_root, "territories", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="unknown rating system"):
            load_knowledge_base(kb_root)

    def test_rating_system_referencing_unknown_territory(self, kb_root: Path) -> None:
        payload = kb_fixtures.rating_systems()
        payload["items"][0]["territory"] = "atlantis"
        kb_fixtures.rewrite(kb_root, "rating_systems", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="unknown territory"):
            load_knowledge_base(kb_root)

    def test_equivalence_referencing_unknown_classification(self, kb_root: Path) -> None:
        payload = kb_fixtures.rating_systems()
        payload["equivalences"][0]["classifications"] = ["system_0.class_9", "system_1.class_1"]
        kb_fixtures.rewrite(kb_root, "rating_systems", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="unknown classification"):
            load_knowledge_base(kb_root)

    def test_archetype_scoring_unknown_budget_tier(self, kb_root: Path) -> None:
        payload = kb_fixtures.archetypes()
        payload["items"][0]["budget_affinity"]["blockbuster"] = 3
        kb_fixtures.rewrite(kb_root, "archetypes", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="unknown budget tiers"):
            load_knowledge_base(kb_root)

    def test_archetype_missing_a_budget_tier_score(self, kb_root: Path) -> None:
        payload = kb_fixtures.archetypes()
        del payload["items"][0]["budget_affinity"]["studio"]
        kb_fixtures.rewrite(kb_root, "archetypes", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="missing budget affinity"):
            load_knowledge_base(kb_root)

    def test_archetype_scoring_unknown_genre(self, kb_root: Path) -> None:
        payload = kb_fixtures.archetypes()
        payload["items"][0]["genre_affinity"]["musical"] = 1
        kb_fixtures.rewrite(kb_root, "archetypes", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="unknown genres"):
            load_knowledge_base(kb_root)

    def test_genre_listing_unknown_hybrid_partner(self, kb_root: Path) -> None:
        payload = kb_fixtures.genres()
        payload["items"][0]["hybrid_friendly"] = ["western"]
        kb_fixtures.rewrite(kb_root, "genres", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="unknown hybrid partners"):
            load_knowledge_base(kb_root)

    def test_duplicate_identifier(self, kb_root: Path) -> None:
        payload = kb_fixtures.genres()
        payload["items"][1]["id"] = payload["items"][0]["id"]
        kb_fixtures.rewrite(kb_root, "genres", payload)

        with pytest.raises(KnowledgeBaseIntegrityError, match="duplicate id"):
            load_knowledge_base(kb_root)


class TestDeterminism:
    def test_two_loads_produce_identical_content(self, kb_root: Path) -> None:
        first = load_knowledge_base(kb_root)
        second = load_knowledge_base(kb_root)

        assert json.dumps(first.genres, sort_keys=True) == json.dumps(second.genres, sort_keys=True)
        assert first.version == second.version
