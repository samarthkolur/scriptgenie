# CLAUDE.md — ScriptGenie (CASIE)

Operating manual for any AI agent or developer working in this repository.
**Read this file top to bottom before touching code. Update `## CURRENT STATUS

<!-- ============================================================
     UPDATE THIS ENTIRE SECTION AT THE END OF EVERY SESSION.
     Keep it factual and short. It is the handoff contract.
     ============================================================ -->

**Last updated:** 2026-07-27
**Updated by:** Samarth D Kolur

| Field                | Value                                                                   |
| -------------------- | ----------------------------------------------------------------------- |
| Current phase        | **Phase 2 — Deterministic Constraint Engines**                          |
| Current stage        | **Stage 2.1 — Domain models** (not started)                             |
| Last completed stage | Stage 1.5 — Conflict rule set                                           |
| Last commit on main  | `3e17e7d feat(kb): add pairwise and multi-constraint conflict rule set` |
| KB version           | `0.1.0`                                                                 |
| Build health         | 🟢 84 API tests, 3 web tests, all gates green                           |

### Done: Phase 0 — Foundation & Governance

- **0.1** Credential removed from `prompt.txt`; gitleaks clean on working tree and full history. README, MIT licence, ADR 0001 (ADR process) and ADR 0002 (deterministic constraint layer).
- **0.2** pnpm workspace. `apps/web` on Next.js 16 App Router, React 19, Tailwind 4, TypeScript strict plus `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`; starter page replaced with a real landing page under test. `apps/api` on FastAPI with uv, laid out as routers / services / engines / kb / db / domain.
- **0.3** Prettier, ESLint, ruff, mypy strict, commitlint with type and scope enums. Husky `pre-commit` (lint-staged + staged secret scan), `commit-msg`, `pre-push`. `scripts/no-placeholders.sh` enforces the no-mock rule mechanically. `.gitleaks.toml` adds rules the defaults lack: the `sk-` shape found in this repo, Groq `gsk_`, Supabase `sbp_` and service-role JWTs.
- **0.4** `ci.yml` — commitlint, no-placeholders, authorship check, web job, api job with an 85% coverage floor.
- **0.5** `security.yml` — gitleaks, env-file guard, pip-audit, pnpm audit, Trivy. Plus CodeQL, Dependabot, PR template, SECURITY.md.

All gates were verified against real failing inputs, not assumed: bad commit message, bad scope, staged secret, stub in app code (and the same string permitted in `tests/`), tracked `.env`, real value in a `.env.example`, Co-Authored-By trailer, agent set as git author.

### Done: Phase 1 — Constraint Knowledge Base

`packages/constraint-kb` is complete and loads end to end.

- **1.1** Six JSON Schemas plus `common.schema.json`. Loader validates each file, reports file and JSON pointer on the first violation, then checks cross-file references JSON Schema cannot express. No partial-success path. 25 tests.
- **1.2** Four budget tiers with six scope parameters each, SAG-AFTRA aligned, each with rationale and citations. Studio tier stores `null` bounds rather than invented ceilings.
- **1.3** Five rating systems, 23 classifications, six dimensions each with prose criteria. Equivalences carry confidence, not identity; the PG-13 / CBFC U/A asymmetry is asserted in tests.
- **1.4** Ten genres, five territories with restrictions that bind beyond the rating, five archetypes with beat blueprints and affinity scores.
- **1.5** 27 conflict rules across all six content dimensions, all five scope parameters, territory overrides, audience contradictions and hybrid pressure. HARD is held under a third of the set by test.

`/health` reports `kb_version`, so a running service identifies the data driving its verdicts.

### Next: Phase 2 — Deterministic Constraint Engines

This is the research contribution. **No LLM call may appear anywhere in Phase 2.**

Start at **Stage 2.1 — Domain models**: Pydantic v2 models in `app/domain/` for `ConstraintBundle` through `VerificationResult`.

Then 2.2 conflict detector (100% branch coverage, golden test against the worked example in the research analysis), 2.3 resolution application, 2.4 scope parameterizer, 2.5 archetype selector.

### Useful facts for the next session

- Run everything: `pnpm verify` (web + scripts) and `cd apps/api && uv run pytest`.
- `gitleaks` is installed at `~/.local/bin/gitleaks`; hooks warn rather than fail if it is missing from `PATH`.
- The KB loads via `app.kb.loader.load_knowledge_base()`; `load_data_file(stem)` validates one file without cross-file checks.
- Conflict rule predicates are declarative: `dimension_exceeds`, `scope_exceeds`, `ordinal_exceeds`, `equals`, `not_equals`, `includes`, `count_gte`, plus `all_of` / `any_of` / `none_of`. Stage 2.2 has to implement exactly this vocabulary and no more.
- Ordinal enums (`vfx_complexity`, `period_setting`, `action_complexity`) compare by position in the list declared in `common.schema.json`.

### Open blockers / decisions needed

1. **🔴 Still open — rotate the leaked key.** The credential was removed from `prompt.txt` and never entered git history, but it stays valid until revoked at the provider.
2. Confirm the Groq model id for `GROQ_MODEL` against current Groq documentation at Stage 3.1.
3. Confirm the API hosting target (Fly.io or Render) before Stage 8.2.
4. CI has never run: there is no GitHub remote yet. The workflows are written but unproven against the real runner.
