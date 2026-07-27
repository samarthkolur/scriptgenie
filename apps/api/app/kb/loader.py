"""Knowledge base loading and validation.

The knowledge base is the single source of domain truth: budget bands, rating
thresholds, genre demands, territory restrictions, archetypes and the conflict
rule set. Nothing in this repository may hardcode those values.

Loading is strict and eager. Every file is validated against its JSON Schema,
then cross-file references are checked, and any failure raises rather than
degrading. A partially loaded knowledge base would make conflict detection
quietly incomplete, and a conflict report that is missing a conflict is the one
failure mode this system exists to prevent.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.kb.errors import (
    KnowledgeBaseFileError,
    KnowledgeBaseIntegrityError,
    KnowledgeBaseValidationError,
)

#: Data file stem -> schema file stem.
DATA_FILES: Mapping[str, str] = {
    "budget_tiers": "budget_tier",
    "rating_systems": "rating_system",
    "genres": "genre",
    "territories": "territory",
    "archetypes": "archetype",
    "conflict_rules": "conflict_rule",
}

JsonObject = dict[str, Any]

#: What a JSON Schema document may be: an object, or a bare boolean schema.
SchemaResource = bool | Mapping[str, Any]


def default_kb_root() -> Path:
    """Locate ``packages/constraint-kb`` relative to this source file.

    ``loader.py`` sits at ``apps/api/app/kb/``, so the repository root is four
    levels up.
    """
    return Path(__file__).resolve().parents[4] / "packages" / "constraint-kb"


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    """An immutable, validated snapshot of the constraint knowledge base."""

    version: str
    budget_tiers: tuple[JsonObject, ...]
    rating_systems: tuple[JsonObject, ...]
    rating_equivalences: tuple[JsonObject, ...]
    genres: tuple[JsonObject, ...]
    territories: tuple[JsonObject, ...]
    archetypes: tuple[JsonObject, ...]
    conflict_rules: tuple[JsonObject, ...]

    def budget_tier(self, tier_id: str) -> JsonObject:
        return _require(self.budget_tiers, tier_id, "budget tier")

    def genre(self, genre_id: str) -> JsonObject:
        return _require(self.genres, genre_id, "genre")

    def territory(self, territory_id: str) -> JsonObject:
        return _require(self.territories, territory_id, "territory")

    def archetype(self, archetype_id: str) -> JsonObject:
        return _require(self.archetypes, archetype_id, "archetype")

    def rating_system(self, system_id: str) -> JsonObject:
        return _require(self.rating_systems, system_id, "rating system")

    def classification(self, system_id: str, classification_id: str) -> JsonObject:
        system = self.rating_system(system_id)
        for classification in system["classifications"]:
            if classification["id"] == classification_id:
                return dict(classification)
        raise KeyError(f"unknown classification '{system_id}.{classification_id}'")

    def conflict_rule(self, rule_id: str) -> JsonObject:
        return _require(self.conflict_rules, rule_id, "conflict rule")


def _require(items: tuple[JsonObject, ...], item_id: str, kind: str) -> JsonObject:
    for item in items:
        if item["id"] == item_id:
            return item
    raise KeyError(f"unknown {kind} '{item_id}'")


def _read_json(path: Path) -> JsonObject:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise KnowledgeBaseFileError(str(path), f"cannot be read ({exc.strerror})") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseFileError(
            str(path), f"is not valid JSON (line {exc.lineno}, column {exc.colno})"
        ) from exc

    if not isinstance(parsed, dict):
        raise KnowledgeBaseFileError(str(path), "must contain a JSON object at the top level")

    return parsed


def _build_registry(schema_dir: Path) -> Registry[SchemaResource]:
    """Register every schema by filename so ``$ref`` between them resolves."""
    registry: Registry[SchemaResource] = Registry()
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        schema = _read_json(schema_path)
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        registry = registry.with_resource(uri=schema_path.name, resource=resource)
        identifier = schema.get("$id")
        if isinstance(identifier, str):
            registry = registry.with_resource(uri=identifier, resource=resource)
    return registry


def _validate(
    data: JsonObject, schema: JsonObject, registry: Registry[SchemaResource], path: Path
) -> None:
    validator = Draft202012Validator(schema, registry=registry)
    errors: Iterator[JsonSchemaValidationError] = validator.iter_errors(data)
    first = next(iter(sorted(errors, key=lambda err: list(err.absolute_path))), None)
    if first is not None:
        pointer = "/" + "/".join(str(part) for part in first.absolute_path)
        raise KnowledgeBaseValidationError(str(path), pointer, first.message)


def _check_integrity(payloads: Mapping[str, JsonObject]) -> None:
    """Verify references that JSON Schema cannot express.

    Uniqueness is checked first: a duplicate identifier makes every later
    reference check ambiguous, so reporting a dangling reference before
    reporting the duplicate that caused it would send the reader to the wrong
    file.
    """
    _check_unique_ids(payloads)

    budget_ids = {item["id"] for item in payloads["budget_tiers"]["items"]}
    genre_ids = {item["id"] for item in payloads["genres"]["items"]}
    system_ids = {item["id"] for item in payloads["rating_systems"]["items"]}
    territory_ids = {item["id"] for item in payloads["territories"]["items"]}

    qualified_classifications = {
        f"{system['id']}.{classification['id']}"
        for system in payloads["rating_systems"]["items"]
        for classification in system["classifications"]
    }

    for territory in payloads["territories"]["items"]:
        if territory["rating_system"] not in system_ids:
            raise KnowledgeBaseIntegrityError(
                f"territory '{territory['id']}' references unknown rating system "
                f"'{territory['rating_system']}'"
            )

    for system in payloads["rating_systems"]["items"]:
        if system["territory"] not in territory_ids:
            raise KnowledgeBaseIntegrityError(
                f"rating system '{system['id']}' references unknown territory "
                f"'{system['territory']}'"
            )

    for equivalence in payloads["rating_systems"].get("equivalences", []):
        for qualified in equivalence["classifications"]:
            if qualified not in qualified_classifications:
                raise KnowledgeBaseIntegrityError(
                    f"rating equivalence references unknown classification '{qualified}'"
                )

    for archetype in payloads["archetypes"]["items"]:
        unknown_budgets = set(archetype["budget_affinity"]) - budget_ids
        if unknown_budgets:
            raise KnowledgeBaseIntegrityError(
                f"archetype '{archetype['id']}' scores unknown budget tiers: "
                f"{sorted(unknown_budgets)}"
            )
        missing_budgets = budget_ids - set(archetype["budget_affinity"])
        if missing_budgets:
            raise KnowledgeBaseIntegrityError(
                f"archetype '{archetype['id']}' is missing budget affinity for: "
                f"{sorted(missing_budgets)}"
            )
        unknown_genres = set(archetype["genre_affinity"]) - genre_ids
        if unknown_genres:
            raise KnowledgeBaseIntegrityError(
                f"archetype '{archetype['id']}' scores unknown genres: {sorted(unknown_genres)}"
            )

    for genre in payloads["genres"]["items"]:
        unknown_hybrids = set(genre.get("hybrid_friendly", [])) - genre_ids
        if unknown_hybrids:
            raise KnowledgeBaseIntegrityError(
                f"genre '{genre['id']}' lists unknown hybrid partners: {sorted(unknown_hybrids)}"
            )


def _check_unique_ids(payloads: Mapping[str, JsonObject]) -> None:
    for name, payload in payloads.items():
        seen: set[str] = set()
        for item in payload["items"]:
            if item["id"] in seen:
                raise KnowledgeBaseIntegrityError(f"{name}: duplicate id '{item['id']}'")
            seen.add(item["id"])


def load_knowledge_base(root: Path | None = None) -> KnowledgeBase:
    """Load, validate and freeze the knowledge base.

    Raises a :class:`~app.kb.errors.KnowledgeBaseError` subclass on any
    problem; there is no partial-success path.
    """
    kb_root = root or default_kb_root()
    schema_dir = kb_root / "schema"
    data_dir = kb_root / "data"

    version_file = kb_root / "VERSION"
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise KnowledgeBaseFileError(str(version_file), "is missing") from exc
    if not version:
        raise KnowledgeBaseFileError(str(version_file), "is empty")

    registry = _build_registry(schema_dir)

    payloads: dict[str, JsonObject] = {}
    for data_stem, schema_stem in DATA_FILES.items():
        data_path = data_dir / f"{data_stem}.json"
        schema_path = schema_dir / f"{schema_stem}.schema.json"
        if not data_path.exists():
            raise KnowledgeBaseFileError(str(data_path), "is missing")
        if not schema_path.exists():
            raise KnowledgeBaseFileError(str(schema_path), "is missing")

        data = _read_json(data_path)
        schema = _read_json(schema_path)
        _validate(data, schema, registry, data_path)
        payloads[data_stem] = data

    _check_integrity(payloads)

    return KnowledgeBase(
        version=version,
        budget_tiers=tuple(payloads["budget_tiers"]["items"]),
        rating_systems=tuple(payloads["rating_systems"]["items"]),
        rating_equivalences=tuple(payloads["rating_systems"].get("equivalences", [])),
        genres=tuple(payloads["genres"]["items"]),
        territories=tuple(payloads["territories"]["items"]),
        archetypes=tuple(payloads["archetypes"]["items"]),
        conflict_rules=tuple(payloads["conflict_rules"]["items"]),
    )


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    """Return the process-wide knowledge base, loading it on first use."""
    return load_knowledge_base()
