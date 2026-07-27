# CLAUDE.md — ScriptGenie (CASIE)

Operating manual for any AI agent or developer working in this repository.
**Read this file top to bottom before touching code. Update `## CURRENT STATUS` at the end of every working session.**

---

## 1. Project Identity

| Field                            | Value                                                                                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product name                     | **ScriptGenie**                                                                                                                                                     |
| System name                      | **CASIE** — Constraint-Aware Script Ideation Engine                                                                                                                 |
| Problem statement                | NVIDIA PS241 — Media & Entertainment: _"Build a script ideation assistant that generates plot variants under genre, audience, budget, and censorship constraints."_ |
| Source of truth for requirements | [PS241_Research_Gap_Analysis_v2.txt](PS241_Research_Gap_Analysis_v2.txt)                                                                                            |
| Build plan                       | [BUILD_PLAN.md](BUILD_PLAN.md)                                                                                                                                      |
| Author / owner                   | **Samarth D Kolur** — GitHub `samarthkolur` — `samarthdkolur1@gmail.com`                                                                                            |

### What the product does

A writer or producer enters a **constraint bundle** (genre, target audience + content rating, production budget tier, distribution territories). The system:

1. **Detects constraint conflicts deterministically** _before_ any LLM call, classifies them `HARD` / `SOFT` / `ADVISORY`, and routes the user through an explicit resolution workflow.
2. **Translates the resolved bundle into hard narrative scope parameters** (max locations, max speaking characters, VFX ceiling, period setting, action complexity, content thresholds per rating dimension).
3. **Generates 3–5 plot variants**, each forced into a _different_ narratological archetype (Crucible, Ensemble Convergence, Non-Linear Revelation, Pursuit, Transformation Arc) before generation, so diversity is architectural, not stochastic.
4. **Verifies each variant** post-generation against the scope parameters and flags — never silently passes — anything that exceeds them.

### The three architectural rules that define this product

These come straight from the research gap. Violating any of them makes the product just another ChatGPT wrapper.

> **R1 — The LLM never reasons about production constraints.** Conflict detection and scope parameterization are deterministic Python over a curated knowledge base. The LLM only generates narrative _inside_ an already-validated envelope.
>
> **R2 — Budget tier is a narrative shaper, not a label.** Scope parameters are numeric hard bounds injected as structured fields into the prompt, and re-checked after generation.
>
> **R3 — Archetype is assigned programmatically before the LLM call.** Never ask the model to "make the variants different." One archetype per variant, chosen by the system.

---

## 2. Locked Technology Stack

**Non-negotiable.** Do not introduce alternatives, do not swap libraries, do not add a second state manager or a second ORM.

| Layer         | Technology                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------- |
| Frontend      | **Next.js (App Router, TypeScript, strict mode)**                                             |
| UI components | **shadcn/ui** + Tailwind CSS + `lucide-react` icons                                           |
| Backend       | **FastAPI** (Python 3.12, Pydantic v2, `uv` for dependency management)                        |
| LLM access    | **Groq API** (`groq` SDK) — model id from `GROQ_MODEL` env var                                |
| Database      | **Supabase Postgres** (SQL migrations, Row Level Security on every table)                     |
| Auth          | **Supabase Auth with Google OAuth** (`@supabase/ssr` on the web, JWT verification on the API) |
| Testing       | Vitest + Testing Library + Playwright (web) · pytest + pytest-asyncio (api)                   |
| CI            | GitHub Actions                                                                                |
| Hosting       | Vercel (web) · Fly.io or Render (api) · Supabase Cloud (db/auth)                              |

Anything not on this list requires an explicit decision recorded in `docs/adr/`.

---

## 3. Repository Layout

```
scriptgenie/
├── CLAUDE.md                    # this file — agent operating manual
├── BUILD_PLAN.md                # phased build plan, the execution contract
├── README.md                    # human-facing setup + product overview
├── PS241_Research_Gap_Analysis_v2.txt
│
├── apps/
│   ├── web/                     # Next.js frontend
│   │   ├── app/                 # App Router routes only — thin, no business logic
│   │   ├── components/
│   │   │   ├── ui/              # shadcn/ui primitives — DO NOT EDIT (see §4)
│   │   │   └── features/        # our composed components, grouped by domain
│   │   │       ├── constraints/
│   │   │       ├── conflicts/
│   │   │       ├── variants/
│   │   │       └── projects/
│   │   ├── lib/                 # api client, supabase clients, formatters, cn()
│   │   ├── hooks/               # reusable React hooks
│   │   ├── types/               # generated API types + shared TS types
│   │   └── tests/
│   │
│   └── api/                     # FastAPI backend
│       ├── app/
│       │   ├── main.py          # app factory + middleware wiring only
│       │   ├── core/            # settings, logging, security, exceptions
│       │   ├── api/v1/routers/  # HTTP layer only — no business logic
│       │   ├── domain/          # Pydantic models: bundle, conflict, scope, variant
│       │   ├── kb/              # knowledge base loader, schema validation, versioning
│       │   ├── engines/         # ← the deterministic core (see §5)
│       │   │   ├── conflict_detector.py
│       │   │   ├── scope_parameterizer.py
│       │   │   ├── archetype_selector.py
│       │   │   ├── prompt_builder.py
│       │   │   └── verifier.py
│       │   ├── services/        # groq client, generation orchestration, persistence
│       │   └── db/              # supabase client + repositories
│       └── tests/
│
├── packages/
│   └── constraint-kb/           # versioned JSON knowledge base — SINGLE SOURCE OF TRUTH
│       ├── schema/              # JSON Schema definitions
│       ├── data/                # budgets, ratings, genres, territories, conflict rules
│       └── VERSION              # semver; bump on any data change
│
├── supabase/migrations/         # numbered, forward-only SQL migrations
├── .github/workflows/           # ci, security, codeql
└── docs/
    ├── adr/                     # architecture decision records
    ├── api.md
    └── runbook.md
```

**Layering rule (enforced in review):** `routers → services → engines → kb`. Never call an engine from a router without a service, never let an engine import a router, never let the frontend contain constraint logic that belongs in the backend. Client-side conflict hints are allowed only as a UX preview; the API verdict is authoritative.

---

## 4. Code Rules (hard)

### shadcn/ui

- **Never edit anything inside `apps/web/components/ui/`.** Those files are vendored primitives.
- Customise **only** through props, `className` (merged with `cn()`), Tailwind theme tokens in `globals.css`, and `cva` variants defined in _your own_ wrapper components under `components/features/`.
- Need a variant shadcn doesn't ship? Create `components/features/<domain>/<Name>.tsx` that wraps the primitive. Do not fork the primitive.
- Add primitives with the shadcn CLI, commit them untouched: `feat(ui): add dialog and sonner primitives`.

### Modularity

- One responsibility per file. If a file passes ~250 lines, split it.
- React components: presentational by default; data fetching lives in hooks or server components.
- Python: pure functions in `engines/` — **no I/O, no network, no Supabase, no Groq inside `engines/`.** They take data in and return data out, which is what makes them unit-testable and deterministic.
- No business logic in `app/` route files or in `api/v1/routers/`.
- Shared types come from generated OpenAPI types (`apps/web/types/api.ts`); never hand-maintain a duplicate interface.

### Typing & validation

- TypeScript `strict: true`. `any` is banned; use `unknown` + a narrowing guard.
- Every API request and response body is a Pydantic v2 model. No bare `dict` in a signature.
- Every LLM response is parsed into a Pydantic model. Never trust raw model output.

### Testing

- Every `engines/` module ships with unit tests in the same commit. Conflict detector and scope parameterizer target **100% branch coverage** — they are the product's differentiator.
- LLM calls are faked **inside the test suite only** (see the mock rule below). Live-model checks live in a separate, manually triggered suite.

### 🚫 No mock data, no placeholders, no dummy implementations

**Every stage ships working, real, end-to-end functionality. Nothing is faked to make a screen look finished.**

Banned in application code — `apps/web/`, `apps/api/app/`, `packages/constraint-kb/`:

| Banned                                                                 | What to do instead                                     |
| ---------------------------------------------------------------------- | ------------------------------------------------------ |
| Hardcoded sample variants, fake conflicts, canned plot text            | Call the real engine / real Groq API                   |
| `const MOCK_PROJECTS = [...]`, fixture arrays imported by components   | Fetch from the real API endpoint                       |
| `// TODO: implement`, `raise NotImplementedError`, `return null` stubs | Build the real thing in this stage, or move the stage  |
| Lorem ipsum, "Coming soon", dead buttons, non-functional links         | Ship the working control or don't ship the control     |
| Placeholder KB rows (`"genre": "TBD"`, invented thresholds)            | Curate the real row with a source citation, or omit it |
| Fake auth / a bypass flag that skips JWT verification                  | Real Supabase Google OAuth from Stage 4.2 onward       |
| Random or hardcoded numbers standing in for computed scope bounds      | Compute from the knowledge base                        |
| Swallowed errors that return fabricated success                        | Propagate a typed error and render a real error state  |

Allowed, and required:

- **Test doubles inside `tests/` directories** — mocked Groq transport, fixture bundles, seeded factories. Tests must never hit the live LLM in CI. This is the _only_ place fakes may exist, and they never get imported by application code.
- **Loading skeletons and empty states** — these are real UI for real states, not placeholders for missing functionality.
- **Config defaults** in `.env.example` with empty values.

**Enforcement:** a CI lint step fails the build on `TODO`, `FIXME`, `NotImplementedError`, `MOCK_`, `DUMMY_`, `lorem ipsum`, or `Coming soon` appearing anywhere outside `tests/` and this file. A stage whose acceptance criteria pass only because data was hardcoded is **not** complete — it is reverted, not patched.

Corollary for planning: if a stage cannot be built for real yet because its dependency is not done, **do not stub it** — go build the dependency stage first. The BUILD_PLAN order already guarantees the deterministic engines exist before any UI needs their output.

---

## 5. The Deterministic Core (do not compromise)

```
ConstraintBundle
   │
   ▼
[conflict_detector]  ── deterministic rules over packages/constraint-kb
   │                    → ConflictReport(HARD | SOFT | ADVISORY, explanation, resolution options)
   │                    → generation BLOCKED while any HARD conflict is unresolved
   ▼
ResolvedBundle
   │
   ▼
[scope_parameterizer] ── budget tier → numeric scope bounds
   │                     rating × system → content thresholds
   ▼
ScopeEnvelope
   │
   ▼
[archetype_selector]  ── picks N distinct archetypes suited to the envelope
   │
   ▼
[prompt_builder] → Groq (N parallel calls, one archetype each) → structured JSON
   │
   ▼
[verifier]  ── extract locations/cast/content markers, compare to ScopeEnvelope
               → PASS | FLAGGED(reason) — never silently PASS a violation
```

Determinism guarantee: **the same bundle + the same KB version always produces the same conflict report.** Any change that breaks this is a bug, not a feature.

---

## 6. Git & Commit Rules

### Authorship — mandatory

Every commit is authored by the owner and **only** the owner:

```
Author: Samarth D Kolur <samarthdkolur1@gmail.com>
```

- **Never** add `Co-Authored-By` trailers.
- **Never** name or reference Anthropic, Claude, DeepSeek, Copilot, GPT, or any AI agent/tool in commit messages, PR titles, PR bodies, code comments, or documentation authorship lines.
- Verify once per machine:
  ```bash
  git config user.name  "Samarth D Kolur"
  git config user.email "samarthdkolur1@gmail.com"
  ```

### Conventional Commits — mandatory

```
<type>(<scope>): <imperative subject, lower case, no trailing period>

[body: what changed and why, wrapped at 72 chars]

[BREAKING CHANGE: ...]
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
Common scopes: `web`, `api`, `kb`, `db`, `auth`, `engines`, `ui`, `ci`, `security`, `docs`.

Examples:

```
feat(engines): add pairwise constraint conflict detector
fix(api): reject generation when a HARD conflict is unresolved
feat(kb): encode CBFC territory restrictions for v0.3.0
ci(security): add gitleaks secret scan to pull request workflow
```

`commitlint` enforces this in CI and in the `commit-msg` hook. A commit that fails the hook is rewritten, never bypassed with `--no-verify`.

### Branching & PRs

- `main` is protected: no direct pushes, linear history, all checks green.
- Branch names: `feat/<phase>-<stage>-<slug>`, e.g. `feat/p2-s2.1-conflict-detector`.
- One stage from BUILD_PLAN.md = one PR. PR title follows Conventional Commits. Squash-merge.
- Every PR must satisfy the checklist in [BUILD_PLAN.md](BUILD_PLAN.md#pull-request-checklist).

---

## 7. Security Rules (hard)

1. **No secret ever enters git.** Keys live in `.env.local` (web) / `.env` (api) and in the hosting provider's secret store. Only `.env.example` — with empty values — is committed.
2. `gitleaks` runs as a pre-commit hook and in CI on every PR and push. A hit fails the build.
3. **Service-role Supabase keys are backend-only.** The browser gets the anon key and nothing else. Anything prefixed `NEXT_PUBLIC_` is public — treat it as printed on a billboard.
4. **The Groq key never reaches the browser.** All LLM calls go through FastAPI.
5. **RLS is enabled on every table** with owner-scoped policies. A user can read only their own projects, bundles, and variants.
6. Every API route except `/health` requires a verified Supabase JWT. Generation endpoints are rate limited per user.
7. Dependency scanning (`pip-audit`, `npm audit`, Dependabot) and `CodeQL` run on schedule and on PRs.
8. If a secret is ever committed: **rotate the key first**, then purge history, then report it in the PR.

---

## 8. Everyday Commands

```bash
# Web
cd apps/web && pnpm dev            # dev server
pnpm lint && pnpm typecheck && pnpm test
pnpm format                        # prettier write

# API
cd apps/api && uv run fastapi dev app/main.py
uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run pytest --cov=app --cov-report=term-missing

# Database
supabase db diff -f <name>         # author a migration
supabase db push                   # apply

# Whole-repo gates (run before every commit)
pnpm -w verify                     # lint + typecheck + test + gitleaks, both apps
```

---

## 9. Session Protocol for Agents

Follow this every single time you work in this repo:

1. **Read `## CURRENT STATUS` below** — it tells you exactly where the build is. Do not audit the codebase to figure this out; that is what this section exists to prevent.
2. Open [BUILD_PLAN.md](BUILD_PLAN.md), find the next `[ ]` stage, and work **only** that stage. Do not skip ahead, do not bundle stages.
3. Implement → write tests → run the local gates in §8 → commit with a Conventional Commit message and correct authorship.
4. **Before ending the session, update `## CURRENT STATUS`** and tick the stage checkbox in BUILD_PLAN.md. Include the status update in the same commit as the work, or in an immediately following `docs: update build status` commit.
5. If you were blocked, record the blocker in the status block in plain language, including what you tried.

> ### ⚠️ Status maintenance is mandatory
>
> `## CURRENT STATUS` **must be rewritten at the end of every run**, even a run that changed nothing.
> The whole point is that a brand-new chat with zero prior context can read this one section and resume work immediately — **without auditing the repository, reading git log, or re-deriving what has been built.**
> A session that ships code but leaves the status stale is an **incomplete session**.

---

## CURRENT STATUS

<!-- ============================================================
     UPDATE THIS ENTIRE SECTION AT THE END OF EVERY SESSION.
     Keep it factual and short. It is the handoff contract.
     ============================================================ -->

**Last updated:** 2026-07-27
**Updated by:** Samarth D Kolur

| Field                 | Value                                                                       |
| --------------------- | --------------------------------------------------------------------------- |
| Current phase         | **Phase 0 — Foundation & Governance**                                       |
| Current stage         | **Stage 0.1 — Secret hygiene & repository baseline** (not started)          |
| Last completed stage  | _none_                                                                      |
| Last commit on `main` | `f84c5d7 docs: add agent operating manual and phased production build plan` |
| KB version            | _not yet created_                                                           |
| Build health          | 🟡 Planning complete, implementation not started                            |

### What exists right now

- `PS241_Research_Gap_Analysis_v2.txt` — requirements source of truth.
- `CLAUDE.md` — this operating manual.
- `BUILD_PLAN.md` — full phased build plan.
- `.gitignore` — secret- and artifact-safe baseline.
- No application code, no dependencies, no CI, no database yet.

### What is NOT done yet

Everything in Phases 0–9 of BUILD_PLAN.md.

### Open blockers / decisions needed

1. **🔴 SECURITY — action required:** `prompt.txt` in the repo root contains a live-looking API key on line 1. It is currently untracked (not in git history), but it must be **rotated at the provider and removed from the file** before any `git add -A`. `.gitignore` now excludes `prompt.txt` as a stopgap.
2. Confirm Groq model id for `GROQ_MODEL` against current Groq docs at Stage 3.1 (plan assumes a large instruct model with JSON-mode support).
3. Confirm API hosting target (Fly.io vs Render) before Stage 8.2.

### Next action for whoever picks this up

Start **Stage 0.1** in [BUILD_PLAN.md](BUILD_PLAN.md): rotate the leaked key, scrub `prompt.txt`, scaffold the monorepo, and land the tooling baseline.
