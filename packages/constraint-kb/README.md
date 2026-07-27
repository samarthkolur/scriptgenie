# Constraint Knowledge Base

The single source of domain truth for ScriptGenie: budget bands, rating thresholds, genre demands, territory restrictions, narrative archetypes and the conflict rule set.

Nothing in the application may hardcode these values. Adding a territory, a rating system or a conflict rule is a data change here, not a code change.

## Why this exists as data

Constraint reasoning in this system is deterministic — the same bundle always produces the same conflict report — and that property only holds if the rules are inspectable data rather than scattered conditionals. Keeping the knowledge base separate also means it can be audited by someone who does not read Python, and published on its own.

## Layout

```
schema/     JSON Schema (draft 2020-12) — one per data type, plus common.schema.json
data/       the curated data, one file per type
VERSION     semantic version of the data as a whole
```

| Data file             | Schema          | Contents                                                                                          |
| --------------------- | --------------- | ------------------------------------------------------------------------------------------------- |
| `budget_tiers.json`   | `budget_tier`   | Four tiers, each with six narrative scope parameters                                              |
| `rating_systems.json` | `rating_system` | MPA, BBFC, CBFC, FSK classifications and their content thresholds, plus cross-system equivalences |
| `genres.json`         | `genre`         | Genre conventions, content demands and scope demands                                              |
| `territories.json`    | `territory`     | Regulators and restrictions that apply on top of a rating                                         |
| `archetypes.json`     | `archetype`     | Narrative structures with beat blueprints and affinity scores                                     |
| `conflict_rules.json` | `conflict_rule` | Predicates, explanations and resolution options                                                   |

## The shared six-dimension scale

Genre demand and rating permission are both expressed on the same six axes — `violence`, `sexual_content`, `language`, `thematic_darkness`, `drug_use`, `horror_intensity` — using an ordinal 0–4 scale (0 none, 1 mild, 2 moderate, 3 strong, 4 explicit).

This is what makes conflict detection arithmetic. "Horror wants violence at 3, PG-13 permits 2" is a comparison; "horror is a bit intense for PG-13" is an opinion. Only the first can be tested, explained precisely, or reproduced.

Levels are comparable **within** a system. Across systems they are comparable only through the `equivalences` table, which carries a confidence value, because rating boards apply genuinely different criteria and pretending otherwise is how a project passes MPA review and fails CBFC.

## Every value carries a citation

The `citations` field is required by schema on budget tiers, rating systems, genres, territories and archetypes. A number without a source is not admissible, because this knowledge base is used to tell a writer their concept is not producible — a claim that has to be defensible.

## Versioning

`VERSION` is the semantic version of the data as a whole. Every generated variant records the KB version that produced it, so any output can be traced to the exact data behind it.

| Change                                                                                  | Bump      |
| --------------------------------------------------------------------------------------- | --------- |
| Wording, citations, clarified prose, corrected typo                                     | **patch** |
| New row: another territory, genre, archetype, or conflict rule                          | **minor** |
| New threshold value or changed numeric bound on an existing row                         | **minor** |
| Schema change: added or removed required field, renamed id, changed the dimension scale | **major** |

Renaming or reusing an existing `id` for a different concept is always a major change. Identifiers are referenced from stored generation runs and must remain stable.

## Maintenance

Rating frameworks change. Boards revise criteria, and classification practice shifts with political and cultural conditions, so this data is not written once. It needs scheduled review by someone with current regulatory knowledge, and the version and date are shown to users precisely so that stale data is visible rather than silent.

Conflicts detected from this data are reported as tensions with resolution options, never as certification. Classification decisions belong to CARA, BBFC, CBFC and FSK.

## Validation

The loader validates every file against its schema at startup and refuses to run on a violation. Cross-file references — a territory naming a rating system, an archetype scoring a genre — are checked separately, since JSON Schema cannot express them.

```bash
cd apps/api && uv run pytest tests/test_kb_loader.py
```
