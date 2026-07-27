# ScriptGenie (CASIE) — Production Build Plan

**Project:** NVIDIA PS241 — Constraint-Aware Script Ideation Engine
**Owner:** Samarth D Kolur · `samarthkolur` · samarthdkolur1@gmail.com
**Requirements source:** [PS241_Research_Gap_Analysis_v2.txt](PS241_Research_Gap_Analysis_v2.txt)
**Agent operating manual:** [CLAUDE.md](CLAUDE.md) — read it first
**Plan version:** 1.0.0 · 2026-07-27

---

## How to use this document

- The plan is **10 phases**, each split into **stages**. A stage is the unit of work: one branch, one PR, one squashed Conventional Commit.
- **Never work two stages in one PR.** Never skip a stage. If a stage turns out to be wrong, amend the plan in its own `docs:` commit first.
- Every stage lists **Deliverables**, **Acceptance criteria**, and the **Commit** message to use. A stage is done when every acceptance box is objectively true — not when the code "looks finished".
- Tick the stage checkbox here and update `## CURRENT STATUS` in [CLAUDE.md](CLAUDE.md) at the end of every session.

**Definition of Done (applies to every stage):**

1. **Real, working functionality — no mock data, no placeholders, no stubs, no dead controls.** See [CLAUDE.md §4](CLAUDE.md#-no-mock-data-no-placeholders-no-dummy-implementations). A stage that "renders" using hardcoded data is not done; it is reverted.
2. Code implemented and modular per [CLAUDE.md §4](CLAUDE.md#4-code-rules-hard).
3. Tests written and passing; coverage thresholds met.
4. `pnpm verify` green (format, lint, typecheck, no-placeholders, tests, secret scan).
5. Docs/env examples updated.
6. Conventional Commit, correct authorship, no AI-agent references anywhere.
7. CI green on the PR.
8. `CURRENT STATUS` in CLAUDE.md updated.

---

## Delivery map

| Phase | Title                            | Outcome                                                        |
| ----- | -------------------------------- | -------------------------------------------------------------- |
| 0     | Foundation & Governance          | Secure, linted, CI-gated monorepo skeleton                     |
| 1     | Constraint Knowledge Base        | Versioned, schema-validated domain data                        |
| 2     | Deterministic Constraint Engines | Layer 1 + Layer 2 — the actual research contribution           |
| 3     | Generation & Verification Layer  | Layer 3 — archetype-forced Groq generation + post-check        |
| 4     | Backend Platform                 | Supabase schema, auth, API surface, rate limits                |
| 5     | Frontend Foundation              | Next.js + shadcn + Google auth shell                           |
| 6     | Product Surfaces                 | Wizard, conflict resolution, variant cards, comparison, export |
| 7     | Hardening                        | Security, observability, performance, accessibility            |
| 8     | Deployment & Launch              | Production environments, CD, runbook                           |
| 9     | Evaluation & Research Output     | Diversity/compliance metrics, open schema publication          |

---

# Phase 0 — Foundation & Governance

_Outcome: nothing can be committed that is unformatted, untyped, insecure, or badly named._

### [ ] Stage 0.1 — Secret hygiene & repository baseline

**Deliverables**

- Rotate the API key currently present in `prompt.txt` at the provider; delete the key line from the file (or delete the file).
- `.gitignore` covering `.env*`, build artifacts, virtualenvs, editor dirs, `prompt.txt`.
- `gitleaks` installed locally; full-history scan run and recorded clean.
- `README.md` skeleton: what the product is, stack, local setup placeholders.
- `LICENSE` (MIT, © Samarth D Kolur) and `docs/adr/0001-record-architecture-decisions.md`.

**Acceptance criteria**

- [ ] `gitleaks detect --source . --redact` exits 0 on working tree **and** `--log-opts=--all` on history.
- [ ] `git ls-files | grep -E '^\.env'` returns nothing except `*.example` files.
- [ ] Provider dashboard confirms the old key is revoked.

**Commit:** `chore(security): scrub leaked credential and add secret-safe gitignore`

---

### [ ] Stage 0.2 — Monorepo scaffold

**Deliverables**

- pnpm workspace: `pnpm-workspace.yaml`, root `package.json` with `verify`, `lint`, `format`, `typecheck`, `test` scripts fanning out to workspaces.
- `apps/web` — Next.js App Router + TypeScript strict + Tailwind, created via `create-next-app`.
- `apps/api` — FastAPI project managed by `uv`, `pyproject.toml`, `app/main.py` with a `/health` route returning `{status, version, kb_version}`.
- `packages/constraint-kb` — empty structure + `VERSION` file containing `0.0.0`.
- `docker-compose.yml` for local api + supabase CLI convenience (optional local path).

**Acceptance criteria**

- [ ] `pnpm dev` starts the web app on `:3000`; `uv run fastapi dev` starts the api on `:8000`.
- [ ] `GET :8000/health` returns 200 with a JSON body.
- [ ] `tsconfig.json` has `"strict": true`, `"noUncheckedIndexedAccess": true`.

**Commit:** `build: scaffold pnpm monorepo with next.js web and fastapi api`

---

### [ ] Stage 0.3 — Code quality toolchain

**Deliverables**

- **Web:** ESLint (next/core-web-vitals + `@typescript-eslint` strict) + Prettier + `prettier-plugin-tailwindcss`, `.editorconfig`.
- **API:** `ruff` (lint + format), `mypy --strict` on `app/`, `pytest` + `pytest-cov` configured in `pyproject.toml`.
- **Hooks (husky + lint-staged at repo root):**
  - `pre-commit` → `lint-staged` (prettier + eslint --fix on staged TS/TSX/MD/JSON; ruff format + ruff check --fix on staged .py) **and** `gitleaks protect --staged`.
  - `commit-msg` → `commitlint --edit` with `@commitlint/config-conventional`.
  - `pre-push` → `pnpm -w verify`.
- **`scripts/no-placeholders.sh`** — fails on `TODO`, `FIXME`, `NotImplementedError`, `MOCK_`, `DUMMY_`, `lorem ipsum` or `Coming soon` found anywhere outside `tests/`, `**/tests/**` and `CLAUDE.md`. Wired into `pre-push` and into the `verify` script.
- Root `verify` script chains: format check → lint → typecheck → **no-placeholders** → tests → gitleaks.

**Acceptance criteria**

- [ ] A commit with message `bad message` is rejected by the `commit-msg` hook.
- [ ] A commit containing a fake `sk-live-...` string is rejected by `gitleaks protect`.
- [ ] An unformatted file is auto-formatted on `git commit` and the formatted version is what lands.
- [ ] A file containing `// TODO: implement` in `apps/` fails `no-placeholders.sh`; the same string inside `tests/` passes.
- [ ] `pnpm -w verify` passes on a clean tree.

**Commit:** `build(ci): add prettier, eslint, ruff, mypy, husky hooks and commitlint`

---

### [ ] Stage 0.4 — GitHub Actions: CI

**Deliverables** — `.github/workflows/ci.yml`, triggered on PR + push to `main`, with concurrency cancellation and dependency caching:

- `commitlint` job — validates all commits in the PR range and the PR title.
- `no-placeholders` job — runs `scripts/no-placeholders.sh`; fails the PR on any stub, TODO or mock outside test directories.
- `web` job — `pnpm install --frozen-lockfile`, prettier check, eslint, `tsc --noEmit`, vitest with coverage, `next build`.
- `api` job — `uv sync --frozen`, `ruff check`, `ruff format --check`, `mypy app`, `pytest --cov` with `--cov-fail-under=85`.
- Coverage artifacts uploaded on both jobs.

**Acceptance criteria**

- [ ] A PR with a lint error fails CI and blocks merge.
- [ ] `main` branch protection requires `commitlint`, `web`, `api`, and the security jobs from 0.5.

**Commit:** `ci: add lint, typecheck, test and build pipeline`

---

### [ ] Stage 0.5 — GitHub Actions: security & vulnerability gates

**Deliverables** — `.github/workflows/security.yml` (PR + push + weekly cron):

- `gitleaks` full-history secret scan.
- **Env-file guard:** a step that fails if any tracked path matches `.env`, `.env.local`, `*.pem`, `*.key`, or `id_rsa`, and fails if any `.env.example` file contains a value that looks like a real key.
- `pip-audit` on the resolved Python lockfile.
- `pnpm audit --audit-level=high` on the web app.
- `trivy fs` filesystem + config scan (CRITICAL/HIGH fail).
- `.github/workflows/codeql.yml` — CodeQL for `javascript-typescript` and `python`.
- `.github/dependabot.yml` — weekly updates for npm, pip, and github-actions.
- `.github/PULL_REQUEST_TEMPLATE.md` embedding the checklist below.
- `SECURITY.md` with a disclosure contact.

**Acceptance criteria**

- [ ] A PR adding a dummy `.env` file fails the env-file guard.
- [ ] All five security jobs appear as required status checks on `main`.

**Commit:** `ci(security): add secret, dependency, env-file and codeql scanning`

---

# Phase 1 — Constraint Knowledge Base

_Outcome: all domain knowledge lives in versioned, human-curated, schema-validated JSON. No domain constants hardcoded in Python or TypeScript, ever._

### [ ] Stage 1.1 — KB schemas & loader

**Deliverables**

- JSON Schema files in `packages/constraint-kb/schema/`: `budget_tier`, `rating_system`, `genre`, `territory`, `conflict_rule`, `archetype`.
- `apps/api/app/kb/loader.py` — loads, validates against schema, caches in memory, exposes `kb.version`.
- Startup fails loudly if any KB file violates its schema.
- `SemVer` policy documented: patch = wording, minor = new rows, major = schema change.

**Acceptance criteria**

- [ ] Loader raises a typed `KnowledgeBaseError` naming the offending file and JSON pointer on invalid data.
- [ ] `/health` reports the KB version.

**Commit:** `feat(kb): add knowledge base schemas, loader and version policy`

---

### [ ] Stage 1.2 — Budget tiers → narrative scope parameters

**Deliverables** — `data/budget_tiers.json`, four tiers with six scope parameters each, per the research doc §5 Layer 2:

| Tier        | Range    | Max locations | Max speaking cast | VFX             | Period                     | Action                     |
| ----------- | -------- | ------------- | ----------------- | --------------- | -------------------------- | -------------------------- |
| `micro`     | ≤ $50K   | 3             | 5                 | none            | contemporary only          | dialogue-driven, no stunts |
| `low_indie` | $50K–$1M | 7             | 10                | practical only  | contemporary / ≤30yrs back | limited practical          |
| `mid_indie` | $1M–$10M | 15            | 20                | limited digital | any period w/ allocation   | 1–2 set pieces             |
| `studio`    | > $10M   | genre default | genre default     | unrestricted    | any                        | unrestricted               |

Each row carries `narrative_economy`, `source_citation`, and `notes` fields.

**Acceptance criteria**

- [ ] Every tier validates against `budget_tier` schema.
- [ ] Every numeric bound cites its industry source (SAG-AFTRA tier / Saturation.io / Tools for Film).

**Commit:** `feat(kb): encode budget tier to narrative scope parameter mappings`

---

### [ ] Stage 1.3 — Rating systems → content thresholds

**Deliverables** — `data/rating_systems.json` covering **MPA** (G, PG, PG-13, R, NC-17), **BBFC** (U, PG, 12A, 15, 18), **CBFC** (U, U/A, A), **FSK** (0, 6, 12, 16, 18).
Each classification scores six content dimensions on an ordinal 0–4 scale: `violence`, `sexual_content`, `language`, `thematic_darkness`, `drug_use`, `horror_intensity`, each with a documented prose threshold and citation.
Plus a cross-system equivalence table (e.g. MPA PG-13 ≈ BBFC 12A ≈ CBFC U/A ≈ FSK 12) with an explicit `equivalence_confidence` field — because these are approximations, and the product must say so.

**Acceptance criteria**

- [ ] All 18 classifications encoded with all six dimensions.
- [ ] Equivalence mappings are non-symmetric-safe (CBFC U/A is stricter on violence than MPA PG-13 — this must be representable).

**Commit:** `feat(kb): encode MPA, BBFC, CBFC and FSK content threshold matrices`

---

### [ ] Stage 1.4 — Genres, territories and archetypes

**Deliverables**

- `data/genres.json` — 10 genres (Horror, Thriller, Drama, Comedy, Action, Sci-Fi, Romance, Mystery, Documentary-style, Family) with `conventions[]` (narrative elements that define the genre) and `content_demands` on the same six dimensions, so genre demand can be compared numerically against rating ceilings.
- `data/territories.json` — US, UK, India, Germany, Australia: regulator, default rating system, and `additional_restrictions[]` beyond the rating (e.g. CBFC restrictions on depictions of violence against women, drug use glamorisation).
- `data/archetypes.json` — the five archetypes from the research doc, each with `structural_blueprint` (ordered beat functions), `budget_affinity[]`, `genre_affinity[]`, and `min_beats: 5`.

**Acceptance criteria**

- [ ] Genre `content_demands` and rating thresholds share the same six-dimension vocabulary (this is what makes conflict detection arithmetic rather than vibes).
- [ ] Every archetype blueprint has ≥5 ordered beat functions.

**Commit:** `feat(kb): add genre conventions, territory restrictions and plot archetypes`

---

### [ ] Stage 1.5 — Conflict rule set

**Deliverables** — `data/conflict_rules.json`. Rule shape:

```json
{
  "id": "genre_rating_violence_gap",
  "severity": "SOFT",
  "predicate": {
    "type": "dimension_exceeds",
    "left": "genre.content_demands.violence",
    "right": "rating.thresholds.violence"
  },
  "explanation_template": "{genre} convention typically requires violence at level {left}, but {rating_system} {rating} permits at most level {right}.",
  "resolutions": [
    {
      "id": "shift_to_psychological",
      "label": "Shift toward psychological dread",
      "effect": "genre.content_demands.violence -> rating.thresholds.violence"
    },
    { "id": "raise_rating", "label": "Raise the target rating" },
    {
      "id": "accept_relaxation",
      "label": "Proceed with a documented relaxation"
    }
  ]
}
```

Rule families to encode: genre↔rating dimension gaps, genre↔budget scope demands (e.g. Action at `micro`), territory↔rating stricter-market conflicts, budget↔period setting, multi-territory mutual incompatibility, and audience-age↔rating mismatches.

**Severity semantics (from research doc Risk 5):**

- `HARD` — logically irresolvable; **generation is blocked** until the bundle changes.
- `SOFT` — resolvable with a documented creative strategy; generation proceeds after explicit user acknowledgement.
- `ADVISORY` — informational only.

**Acceptance criteria**

- [ ] ≥25 rules encoded, each with ≥2 resolution options.
- [ ] `HARD` is used only where no narrative can satisfy both constraints; documented rationale per HARD rule.
- [ ] The research doc's worked example (Horror-Comedy / PG-13 / micro / US+India) is encodable and produces the three conflicts described there.

**Commit:** `feat(kb): add pairwise and multi-constraint conflict rule set`

---

# Phase 2 — Deterministic Constraint Engines

_This is the research contribution. No LLM may be called from anything in this phase._

### [ ] Stage 2.1 — Domain models

**Deliverables** — Pydantic v2 models in `app/domain/`: `ConstraintBundle`, `GenreSelection`, `AudienceSelection`, `RatingTarget`, `BudgetTier`, `TerritorySet`, `Conflict`, `ConflictReport`, `ResolutionChoice`, `ResolvedBundle`, `ScopeEnvelope`, `ContentThresholds`, `ArchetypeAssignment`, `PlotVariant`, `PlotBeat`, `ConstraintSatisfactionReport`, `VerificationResult`.
Mirrored TS types generated from the OpenAPI schema — never hand-written.

**Acceptance criteria**

- [ ] Invalid enum values rejected at model construction with field-level errors.
- [ ] `mypy --strict` clean.

**Commit:** `feat(api): add constraint, scope and variant domain models`

---

### [ ] Stage 2.2 — Conflict detection engine (Layer 1)

**Deliverables** — `app/engines/conflict_detector.py`:

- `detect(bundle: ConstraintBundle, kb: KnowledgeBase) -> ConflictReport`
- Pure function. No I/O. Evaluates every rule predicate, renders explanation templates with real values, attaches resolution options, sorts by severity.
- Deterministic ordering of conflicts (stable sort by severity then rule id).
- Structured logging of rule-evaluation counts for later research telemetry.

**Acceptance criteria**

- [ ] **100% branch coverage** on this module.
- [ ] Golden test: the worked example from the research doc returns exactly 1 SOFT (genre↔rating violence), 1 HARD (CBFC stricter than PG-13), 1 ADVISORY (micro-budget location economy vs comedy) with the documented resolutions.
- [ ] Property test: 500 randomly generated valid bundles evaluated twice produce byte-identical reports.
- [ ] p95 latency < 100 ms for a 6-constraint bundle against the full rule set (benchmarked in tests).

**Commit:** `feat(engines): add deterministic constraint conflict detection engine`

---

### [ ] Stage 2.3 — Resolution application

**Deliverables** — `app/engines/resolution.py`: applies user-selected `ResolutionChoice[]` to a bundle, producing a `ResolvedBundle` that records, per conflict, which resolution was chosen and any relaxation accepted. Re-runs detection to prove no `HARD` conflict survives.

**Acceptance criteria**

- [ ] Applying a resolution that does not clear a `HARD` conflict raises `UnresolvedHardConflictError`.
- [ ] `ResolvedBundle` retains a complete audit trail (original bundle + choices + resulting deltas).

**Commit:** `feat(engines): apply user conflict resolutions and validate resolved bundles`

---

### [ ] Stage 2.4 — Scope parameterization engine (Layer 2)

**Deliverables** — `app/engines/scope_parameterizer.py`:

- `parameterize(resolved: ResolvedBundle, kb) -> ScopeEnvelope` merging budget scope bounds + rating content thresholds + territory extra restrictions, always taking the **most restrictive** value across all selected territories.
- Emits both machine fields (numbers/enums) and the exact structured prompt fragment used later — no free-form prose.

**Acceptance criteria**

- [ ] 100% branch coverage.
- [ ] Multi-territory test: US+India at PG-13 yields CBFC-level violence ceiling, not MPA-level.
- [ ] `micro` tier always yields `max_locations=3`, `max_named_characters=5`, `vfx=none`, `period=contemporary`.

**Commit:** `feat(engines): translate resolved bundles into hard narrative scope envelopes`

---

### [ ] Stage 2.5 — Archetype selection engine

**Deliverables** — `app/engines/archetype_selector.py`: `select(envelope, n) -> list[ArchetypeAssignment]`, scoring archetypes by `budget_affinity` and `genre_affinity`, guaranteeing **N distinct archetypes**, deterministic given a seed, with a documented tie-break order.

**Acceptance criteria**

- [ ] Never returns duplicate archetypes.
- [ ] At `micro` tier, Crucible and Transformation Arc rank above Ensemble Convergence.
- [ ] Same envelope + same seed ⇒ same assignment.

**Commit:** `feat(engines): add archetype assignment for structural variant diversity`

---

# Phase 3 — Generation & Verification Layer

### [ ] Stage 3.1 — Groq client

**Deliverables** — `app/services/groq_client.py`: async client, model id from `GROQ_MODEL`, JSON-mode/structured output, timeouts, bounded exponential-backoff retries, circuit breaker, token+latency+cost logging per call, and a typed `LLMError` hierarchy. Key read from settings only; never logged.

**Acceptance criteria**

- [ ] Unit tests mock the transport entirely; no network in CI.
- [ ] Retries are capped and jittered; a 5xx storm does not hang a request beyond the configured deadline.
- [ ] No env var value ever appears in logs (asserted by test).

**Commit:** `feat(api): add resilient groq client with retries, timeouts and telemetry`

---

### [ ] Stage 3.2 — Prompt builder

**Deliverables** — `app/engines/prompt_builder.py`: builds the system prompt from **structured fields only** — archetype blueprint, numbered scope constraints, content threshold table, genre conventions, output JSON contract (≥5 beats, per-dimension satisfaction statement, relaxation flags). Prompt templates are versioned files under `app/prompts/` with a `PROMPT_VERSION` recorded on every generation for reproducibility.

**Acceptance criteria**

- [ ] Snapshot tests over rendered prompts for three representative envelopes.
- [ ] The prompt never contains phrasing that asks the model to _decide_ budget/rating/conflict questions (asserted by a lint test on forbidden phrases).
- [ ] Scope bounds appear as explicit numbered hard constraints.

**Commit:** `feat(engines): add structured prompt builder with versioned templates`

---

### [ ] Stage 3.3 — Parallel variant generation

**Deliverables** — `app/services/generation_service.py`: orchestrates N archetype-assigned Groq calls with `asyncio.gather`, per-variant parse into `PlotVariant`, one-shot repair retry on malformed JSON, partial-success handling (return succeeded variants, mark failures), and total-deadline enforcement.

**Acceptance criteria**

- [ ] 5 variants generated concurrently, not sequentially (asserted by timing test with a fake client).
- [ ] One failing variant does not fail the batch.
- [ ] Every variant records `kb_version`, `prompt_version`, `model`, `archetype`, `seed`.

**Commit:** `feat(api): generate plot variants in parallel under archetype assignment`

---

### [ ] Stage 3.4 — Post-generation verification

**Deliverables** — `app/engines/verifier.py`: extracts location count, named-character count, period markers, VFX/action signals and content-dimension signals from each variant (rule/keyword pass **plus** a structured Groq extraction call), compares against the `ScopeEnvelope`, returns `VerificationResult` per dimension: `PASS` / `FLAGGED` / `NEEDS_REVIEW`.
Per research doc Risk 2, output language is **"CASIE-verified for scope"**, never "certified compliant".

**Acceptance criteria**

- [ ] A synthetic variant naming 7 locations under `micro` is `FLAGGED` on `max_locations`.
- [ ] No variant is ever surfaced as verified when any dimension is `FLAGGED`.
- [ ] Verification is skippable-free: a verification failure degrades to `NEEDS_REVIEW`, never to silent pass.

**Commit:** `feat(engines): add post-generation scope and content verification`

---

# Phase 4 — Backend Platform

### [ ] Stage 4.1 — Supabase schema & RLS

**Deliverables** — forward-only SQL migrations in `supabase/migrations/`:
`profiles`, `projects`, `constraint_bundles`, `conflict_reports`, `resolutions`, `scope_envelopes`, `generation_runs`, `plot_variants`, `variant_feedback`, `kb_versions`, `usage_events`.
RLS enabled on **every** table with `auth.uid() = owner_id` policies; `updated_at` triggers; indexes on `owner_id`, `project_id`, `created_at`; `profiles` auto-created by a trigger on `auth.users` insert.

**Acceptance criteria**

- [ ] `select` as user A returns zero rows from user B's projects (integration test against a local Supabase).
- [ ] Every table has `rowsecurity = true` (asserted by a SQL test querying `pg_tables`).
- [ ] Migrations apply cleanly onto an empty database.

**Commit:** `feat(db): add supabase schema with row level security policies`

---

### [ ] Stage 4.2 — Auth: Google OAuth end to end

**Deliverables**

- Supabase Auth configured with Google provider (setup steps in `docs/runbook.md`; secrets in the dashboard, not the repo).
- API: `app/core/security.py` verifies Supabase JWTs (JWKS cached, `aud`/`iss`/`exp` checked), `get_current_user` dependency, `401` on invalid, `403` on ownership mismatch.
- Web: `@supabase/ssr` browser + server clients, `/auth/callback` route handler, middleware protecting `/app/*`, sign-in with Google, sign-out.

**Acceptance criteria**

- [ ] Unauthenticated request to any `/api/v1/*` route except `/health` returns 401.
- [ ] A tampered or expired JWT is rejected.
- [ ] Full browser flow: Sign in with Google → callback → session cookie → protected page renders the user's profile.

**Commit:** `feat(auth): add supabase google oauth with jwt verification`

---

### [ ] Stage 4.3 — API surface v1

**Deliverables** — routers under `app/api/v1/routers/` (thin; all logic in services):

| Method | Path                                  | Purpose                                                    |
| ------ | ------------------------------------- | ---------------------------------------------------------- |
| `GET`  | `/health`                             | liveness + versions                                        |
| `GET`  | `/v1/kb/options`                      | genres, ratings, tiers, territories, archetypes for the UI |
| `POST` | `/v1/conflicts/detect`                | bundle → conflict report                                   |
| `POST` | `/v1/conflicts/resolve`               | bundle + choices → resolved bundle + envelope              |
| `POST` | `/v1/projects` / `GET` `/v1/projects` | project CRUD                                               |
| `POST` | `/v1/projects/{id}/generate`          | run generation (blocked on unresolved HARD)                |
| `GET`  | `/v1/projects/{id}/variants`          | list variants                                              |
| `POST` | `/v1/variants/{id}/feedback`          | rating / notes / false-positive report                     |
| `GET`  | `/v1/projects/{id}/export`            | JSON + Markdown export                                     |

Plus: RFC 9457 problem-details error envelope, request-id middleware, CORS locked to known origins, `openapi.json` committed and TS types generated from it.

**Acceptance criteria**

- [ ] `POST /generate` with an unresolved `HARD` conflict returns `409` with the conflict payload.
- [ ] Contract tests cover every route's happy path and auth failure path.
- [ ] `apps/web/types/api.ts` is generated, not hand-edited (CI check that regeneration produces no diff).

**Commit:** `feat(api): add v1 endpoints for constraints, projects and generation`

---

### [ ] Stage 4.4 — Rate limiting, quotas & abuse controls

**Deliverables** — per-user rate limits on generation (e.g. 10 runs/hour, configurable), global concurrency cap on Groq calls, request size limits, `usage_events` recording tokens and cost per run, `429` with `Retry-After`.

**Acceptance criteria**

- [ ] Exceeding the limit returns `429` with `Retry-After` and does not consume Groq quota.
- [ ] Usage rows written for every generation run.

**Commit:** `feat(api): add per-user rate limiting and usage accounting`

---

# Phase 5 — Frontend Foundation

### [ ] Stage 5.1 — Design system & shell

**Deliverables** — Tailwind theme tokens (light + dark), shadcn primitives installed **unmodified** (`button, card, dialog, form, input, select, radio-group, checkbox, badge, tabs, tooltip, sonner, skeleton, accordion, alert, separator, sheet, dropdown-menu`), app shell (header, user menu, nav), typed API client in `lib/api-client.ts` with auth header injection and problem-details parsing, error boundary + loading skeletons, `next-themes` dark mode.

**Acceptance criteria**

- [ ] `git diff --stat apps/web/components/ui/` is empty on every subsequent PR (CI guard).
- [ ] All customization flows through props/`className`/`cva` wrappers in `components/features/`.
- [ ] Lighthouse accessibility ≥ 95 on the shell.

**Commit:** `feat(web): add design system, shadcn primitives and app shell`

---

### [ ] Stage 5.2 — Auth UI & route protection

**Deliverables** — landing page explaining the product scope ("pre-development ideation, not a script generator" — research doc Risk 3), Sign in with Google, session provider, protected `/app` layout, profile menu, sign-out, auth error states.

**Acceptance criteria**

- [ ] Visiting `/app` signed out redirects to sign-in and returns to the intended page after auth.
- [ ] Session survives refresh; sign-out clears it everywhere.

**Commit:** `feat(web): add google sign-in flow and protected app routes`

---

# Phase 6 — Product Surfaces

### [ ] Stage 6.1 — Constraint input wizard

**Deliverables** — multi-step wizard under `components/features/constraints/`: Genre (primary + optional secondary) → Audience & rating system/classification → Budget tier (with plain-English scope preview per tier) → Distribution territories (multi-select).
`react-hook-form` + `zod` mirroring the API schema, contextual tooltips per research doc Risk 4, sensible defaults (US-only, mid-indie, PG-13), and a **Quick Start mode** asking only genre / audience type / production scale and mapping internally to the full bundle.

**Acceptance criteria**

- [ ] Quick Start produces a valid full bundle without the user knowing SAG-AFTRA tiers.
- [ ] Every field has a tooltip written in production terms.
- [ ] Wizard state survives refresh (draft persisted to the project).

**Commit:** `feat(web): add constraint bundle wizard with quick start mode`

---

### [ ] Stage 6.2 — Conflict detection & resolution UI

**Deliverables** — live conflict panel (debounced call to `/conflicts/detect`), conflicts grouped by severity with distinct visual treatment: `HARD` blocks the Generate button outright, `SOFT` requires an explicit acknowledgement checkbox, `ADVISORY` is dismissible. Each conflict shows which two constraints are in tension, why, and selectable resolution options. Includes a "this conflict is wrong" report action feeding `variant_feedback` (Risk 1 mitigation), and shows the **KB version + date** used for the evaluation.

**Acceptance criteria**

- [ ] Generate is disabled and clearly explained while any `HARD` conflict is unresolved.
- [ ] Selecting a resolution updates the scope preview immediately.
- [ ] Screen-reader users get severity announced, not conveyed by colour alone.

**Commit:** `feat(web): add conflict resolution workflow with severity gating`

---

### [ ] Stage 6.3 — Generation & variant cards

**Deliverables** — generation trigger with progress state for N parallel variants, variant cards showing archetype label + structural blueprint, ≥5 beats, per-dimension constraint satisfaction report, verification badges (`Verified for scope` / `Flagged` / `Needs review`), and relaxation flags with explanations. Skeleton loading, partial-failure messaging, retry-one-variant.

**Acceptance criteria**

- [ ] Every card renders archetype, beats, satisfaction report and verification state.
- [ ] Flagged dimensions are visually distinct and name the exact parameter exceeded.
- [ ] Copy never claims regulatory certification.

**Commit:** `feat(web): add variant generation view with verification badges`

---

### [ ] Stage 6.4 — Comparison, library & export

**Deliverables** — side-by-side comparison view (structure, cast/location counts, satisfaction dimensions, verification state), project library with search/filter by genre/tier/rating, variant favouriting and notes, export to Markdown/JSON/PDF including the constraint bundle, resolutions, KB version and prompt version.

**Acceptance criteria**

- [ ] Comparison handles 2–5 variants without horizontal page scroll on mobile.
- [ ] Exports are reproducible and include full provenance (kb + prompt + model versions).

**Commit:** `feat(web): add variant comparison, project library and export`

---

# Phase 7 — Hardening

### [ ] Stage 7.1 — Security hardening

**Deliverables** — security headers + strict CSP via `next.config`/middleware, CSRF-safe auth callback, input sanitisation on all free-text, SSRF-safe outbound calls, `X-Request-Id` propagation, dependency pinning, secret-rotation runbook, threat model in `docs/security.md` (STRIDE over auth, generation, and data access).

**Acceptance criteria**

- [ ] `securityheaders.com`-equivalent local check: A grade; CSP has no `unsafe-inline` for scripts.
- [ ] Prompt-injection test: a bundle whose free-text field tries to override system instructions does not change scope enforcement (verifier still flags violations).
- [ ] `npm audit` + `pip-audit` report zero HIGH/CRITICAL.

**Commit:** `fix(security): harden headers, csp and untrusted input handling`

---

### [ ] Stage 7.2 — Observability

**Deliverables** — structured JSON logging with request ids on both apps, Sentry (or equivalent) for web + api with release tagging and PII scrubbing, `/metrics`-style counters for generation latency, token spend, conflict-type frequency, verification flag rate; an ops dashboard doc.

**Acceptance criteria**

- [ ] A failed generation produces one correlated trace across web → api → groq.
- [ ] No prompt content or user email appears in error payloads.

**Commit:** `feat(api): add structured logging, error tracking and usage metrics`

---

### [ ] Stage 7.3 — Performance & resilience

**Deliverables** — KB caching, HTTP caching on `/kb/options`, Next.js route-level caching where safe, bundle-size budget in CI, image/font optimisation, graceful degradation when Groq is down (queue + user-facing message), load test (k6) at target concurrency.

**Acceptance criteria**

- [ ] Conflict detection p95 < 150 ms end-to-end.
- [ ] Full 5-variant generation p95 < 15 s.
- [ ] Web LCP < 2.5 s on 4G throttling; JS bundle within budget.

**Commit:** `perf: add caching, bundle budgets and graceful llm degradation`

---

### [ ] Stage 7.4 — Test completeness & accessibility

**Deliverables** — Playwright E2E covering the golden path (sign in → wizard → conflicts → resolve → generate → compare → export) plus the HARD-block path; `axe` accessibility assertions on every page; coverage gates raised (engines 100%, api ≥90%, web ≥80%); CI runs E2E on PRs.

**Acceptance criteria**

- [ ] Golden path E2E green in CI against a seeded test project.
- [ ] Zero serious/critical axe violations.
- [ ] Coverage gates enforced, not advisory.

**Commit:** `test: add end-to-end golden path and accessibility coverage`

---

# Phase 8 — Deployment & Launch

### [ ] Stage 8.1 — Environments & configuration

**Deliverables** — Supabase `dev`/`prod` projects, `.env.example` for both apps documenting every variable (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `GROQ_API_KEY`, `GROQ_MODEL`, `API_BASE_URL`, `ALLOWED_ORIGINS`, `RATE_LIMIT_*`), settings validation that fails startup on a missing/blank required var, and documented secret storage per environment.

**Acceptance criteria**

- [ ] App refuses to start with a missing required env var and names it.
- [ ] `.env.example` contains no real values (enforced by the Stage 0.5 guard).

**Commit:** `build: add environment configuration and startup validation`

---

### [ ] Stage 8.2 — Continuous deployment

**Deliverables** — `.github/workflows/deploy.yml`: web → Vercel (preview per PR, production on `main`), api → Fly.io/Render via a multi-stage non-root Dockerfile with a healthcheck, migrations applied in a gated pre-deploy step, smoke test post-deploy, documented rollback.

**Acceptance criteria**

- [ ] A merge to `main` deploys both apps and the post-deploy smoke test passes.
- [ ] Rollback rehearsed once and documented with timings.
- [ ] Container runs as a non-root user; image scanned by Trivy in CI.

**Commit:** `ci: add continuous deployment for web and api with smoke tests`

---

### [ ] Stage 8.3 — Release, docs & runbook

**Deliverables** — `README.md` complete (screenshots, setup, architecture diagram), `docs/api.md`, `docs/runbook.md` (incident response, key rotation, KB update procedure, Groq outage playbook), `CONTRIBUTING.md` restating commit/authorship rules, `CHANGELOG.md` generated from Conventional Commits, tag `v1.0.0`.

**Acceptance criteria**

- [ ] A fresh machine can go from clone to running locally using only the README.
- [ ] `v1.0.0` tagged with generated changelog; production URL live and authenticated.

**Commit:** `docs: add readme, api reference, runbook and v1.0.0 release notes`

---

# Phase 9 — Evaluation & Research Output

_The research doc (Risk 6) makes evaluation a first-phase deliverable, not an afterthought._

### [ ] Stage 9.1 — Evaluation harness

**Deliverables** — `apps/api/evaluation/`: a hand-labelled test set of constraint bundles with known conflicts; conflict detection **precision/recall** report; structural diversity scoring via pairwise sentence-embedding distance between variants of the same bundle (Sui Generis-style, per Xu et al. 2025); constraint satisfaction rate from expert labels; CLI to regenerate the report.

**Acceptance criteria**

- [ ] Report reproducible from a single command, output committed under `docs/evaluation/`.
- [ ] Baseline comparison included: archetype-forced variants vs naive repeated sampling from the same prompt.

**Commit:** `feat(evaluation): add conflict accuracy and structural diversity harness`

---

### [ ] Stage 9.2 — Open constraint schema publication

**Deliverables** — `packages/constraint-kb` documented and published under an open licence with a schema reference, citation file (`CITATION.cff`), and a versioned changelog — the "first such artifact" contribution described in research doc §8.

**Acceptance criteria**

- [ ] Schema documented field-by-field with sources.
- [ ] Licence and citation metadata present; version tagged.

**Commit:** `docs(kb): publish versioned open constraint schema with citations`

---

# Standing Engineering Standards

## Pull request checklist

Copied into `.github/PULL_REQUEST_TEMPLATE.md`:

- [ ] Title and all commits follow Conventional Commits.
- [ ] Author is **Samarth D Kolur <samarthdkolur1@gmail.com>**; no `Co-Authored-By`; no AI tool/agent named anywhere in the diff or message.
- [ ] Exactly one BUILD_PLAN stage in scope.
- [ ] **Everything in the diff is real and working** — no mock data, placeholder text, stubbed functions, dead buttons or hardcoded sample output outside `tests/`.
- [ ] No files under `apps/web/components/ui/` modified.
- [ ] No secrets, `.env` files, keys or tokens added; `gitleaks` clean.
- [ ] Tests added/updated; coverage gates met.
- [ ] `pnpm -w verify` passes locally.
- [ ] Env vars documented in `.env.example` if any were added.
- [ ] `CURRENT STATUS` in CLAUDE.md updated.
- [ ] Breaking changes documented with a `BREAKING CHANGE:` footer.

## CI gate summary

| Workflow       | Jobs                                                                                           | Trigger          |
| -------------- | ---------------------------------------------------------------------------------------------- | ---------------- |
| `ci.yml`       | commitlint · no-placeholders · web (prettier/eslint/tsc/vitest/build) · api (ruff/mypy/pytest) | PR, push `main`  |
| `security.yml` | gitleaks · env-file guard · pip-audit · pnpm audit · trivy                                     | PR, push, weekly |
| `codeql.yml`   | CodeQL JS/TS + Python                                                                          | PR, weekly       |
| `e2e.yml`      | Playwright golden path + axe                                                                   | PR               |
| `deploy.yml`   | Vercel + container deploy + migrations + smoke                                                 | push `main`      |

All of the above are **required status checks** on `main`.

## Risk register (from the research doc, tracked through the build)

| #   | Risk                                        | Mitigation stage                                                           |
| --- | ------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | KB accuracy drifts as regulations change    | 1.1 versioning · 6.2 version display + user reporting · 8.3 update runbook |
| 2   | LLM constraint adherence is probabilistic   | 3.4 verification · 6.3 flag-don't-certify UI                               |
| 3   | Users expect full scripts                   | 5.2 landing copy · 6.3 scope framing                                       |
| 4   | Constraint schema creates adoption friction | 6.1 Quick Start + tooltips + defaults                                      |
| 5   | Conflict false positives block experts      | 1.5 HARD/SOFT/ADVISORY tiering · 6.2 report action                         |
| 6   | No benchmark exists for this task           | Phase 9 evaluation harness                                                 |

## Non-negotiables (repeated because they are the product)

1. The LLM never reasons about production constraints — deterministic engines do.
2. Budget tier is enforced as numeric hard bounds, before and after generation.
3. Archetypes are assigned by the system before the LLM call.
4. `apps/web/components/ui/` is never edited.
5. No secret ever enters git.
6. **No mock data, no placeholders, no dummy implementations in application code** — test doubles live in `tests/` and nowhere else.
7. Every commit: Conventional Commit, authored by Samarth D Kolur, no AI agent referenced.
8. `CURRENT STATUS` in CLAUDE.md is updated at the end of every session.
