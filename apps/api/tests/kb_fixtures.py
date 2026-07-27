"""Builders for synthetic knowledge bases used by loader tests.

These are test doubles and live here deliberately: application code never
imports them. They generate the smallest knowledge base that satisfies every
schema, so that a test can mutate exactly one thing and assert that the loader
rejects it for that reason and no other.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.kb.loader import default_kb_root

JsonObject = dict[str, Any]

DIMENSIONS = (
    "violence",
    "sexual_content",
    "language",
    "thematic_darkness",
    "drug_use",
    "horror_intensity",
)

BUDGET_IDS = ("micro", "low_indie", "mid_indie", "studio")
GENRE_IDS = (
    "horror",
    "thriller",
    "drama",
    "comedy",
    "action",
    "sci_fi",
    "romance",
    "mystery",
    "documentary_style",
    "family",
)
ARCHETYPE_IDS = (
    "crucible",
    "ensemble_convergence",
    "non_linear_revelation",
    "pursuit",
    "transformation_arc",
)
TERRITORY_IDS = ("us", "uk", "india", "germany", "australia")


def _dimensions(level: int) -> JsonObject:
    return dict.fromkeys(DIMENSIONS, level)


def _envelope(schema: str, items: list[JsonObject], **extra: Any) -> JsonObject:
    return {
        "schema": schema,
        "version": "0.1.0",
        "updated": "2026-07-27",
        "items": items,
        **extra,
    }


def budget_tiers() -> JsonObject:
    items = [
        {
            "id": tier_id,
            "label": tier_id.replace("_", " ").title(),
            "order": index,
            "range_usd": {"min": index * 1000, "max": (index + 1) * 1000},
            "guild_context": "synthetic tier used by tests",
            "scope": {
                "max_locations": 3 + index,
                "max_named_characters": 5 + index,
                "vfx_complexity": "none",
                "period_setting": "contemporary_only",
                "action_complexity": "dialogue_driven",
                "narrative_economy": "high",
            },
            "citations": ["synthetic fixture, not a real source"],
        }
        for index, tier_id in enumerate(BUDGET_IDS)
    ]
    return _envelope("budget_tier", items)


def rating_systems() -> JsonObject:
    items = [
        {
            "id": f"system_{index}",
            "label": f"System {index}",
            "authority": "synthetic",
            "territory": territory,
            "classifications": [
                {
                    "id": f"class_{level}",
                    "label": f"Class {level}",
                    "order": level,
                    "min_audience_age": level * 4,
                    "thresholds": _dimensions(level),
                    "criteria": dict.fromkeys(DIMENSIONS, "synthetic criterion"),
                }
                for level in range(3)
            ],
            "citations": ["synthetic fixture, not a real source"],
        }
        for index, territory in enumerate(TERRITORY_IDS[:4])
    ]
    equivalences = [
        {
            "classifications": ["system_0.class_1", "system_1.class_1"],
            "confidence": "medium",
        }
    ]
    return _envelope("rating_system", items, equivalences=equivalences)


def genres() -> JsonObject:
    items = [
        {
            "id": genre_id,
            "label": genre_id.replace("_", " ").title(),
            "conventions": ["convention one", "convention two", "convention three"],
            "content_demands": _dimensions(1),
            "scope_demands": {
                "typical_locations": 4,
                "typical_named_characters": 6,
                "action_complexity": "dialogue_driven",
            },
            "citations": ["synthetic fixture, not a real source"],
        }
        for genre_id in GENRE_IDS
    ]
    return _envelope("genre", items)


def territories() -> JsonObject:
    items = [
        {
            "id": territory_id,
            "label": territory_id.title(),
            "regulator": "synthetic regulator",
            "rating_system": f"system_{min(index, 3)}",
            "citations": ["synthetic fixture, not a real source"],
        }
        for index, territory_id in enumerate(TERRITORY_IDS)
    ]
    return _envelope("territory", items)


def archetypes() -> JsonObject:
    items = [
        {
            "id": archetype_id,
            "label": archetype_id.replace("_", " ").title(),
            "premise": "synthetic premise",
            "structural_blueprint": [
                {"function": f"beat_{beat}", "description": "synthetic beat"} for beat in range(5)
            ],
            "min_beats": 5,
            "budget_affinity": dict.fromkeys(BUDGET_IDS, 2),
            "genre_affinity": dict.fromkeys(GENRE_IDS, 2),
            "citations": ["synthetic fixture, not a real source"],
        }
        for archetype_id in ARCHETYPE_IDS
    ]
    return _envelope("archetype", items)


def conflict_rules() -> JsonObject:
    items = [
        {
            "id": "synthetic_violence_gap",
            "severity": "SOFT",
            "title": "Synthetic violence gap",
            "predicate": {
                "type": "dimension_exceeds",
                "left": {"path": "genre.content_demands.violence"},
                "right": {"path": "rating.thresholds.violence"},
            },
            "explanation_template": "{genre} needs {left}, rating permits {right}.",
            "resolutions": [
                {"id": "soften", "label": "Soften", "description": "Reduce the demand."},
                {"id": "raise_rating", "label": "Raise rating", "description": "Change target."},
            ],
        }
    ]
    return _envelope("conflict_rule", items)


def write_knowledge_base(root: Path, version: str = "0.1.0") -> Path:
    """Write a complete, schema-valid synthetic knowledge base under ``root``."""
    schema_dir = root / "schema"
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Schemas are the real ones: the point of these fixtures is to exercise the
    # loader against the schemas that ship, not against relaxed copies.
    shutil.copytree(default_kb_root() / "schema", schema_dir, dirs_exist_ok=True)

    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")

    payloads = {
        "budget_tiers": budget_tiers(),
        "rating_systems": rating_systems(),
        "genres": genres(),
        "territories": territories(),
        "archetypes": archetypes(),
        "conflict_rules": conflict_rules(),
    }
    for name, payload in payloads.items():
        (data_dir / f"{name}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    return root


def rewrite(root: Path, name: str, payload: JsonObject) -> None:
    """Replace one data file in an already-written fixture knowledge base."""
    (root / "data" / f"{name}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
