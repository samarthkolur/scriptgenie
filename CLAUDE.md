# CLAUDE.md — ScriptGenie (CASIE)

Operating manual for any AI agent or developer working in this repository.
**Read this file top to bottom before touching code. Update `## CURRENT STATUS

<!-- ============================================================
     UPDATE THIS ENTIRE SECTION AT THE END OF EVERY SESSION.
     Keep it factual and short. It is the handoff contract.
     ============================================================ -->

**Last updated:** 2026-07-31
**Updated by:** Samarth D Kolur

| Field                | Value                                                           |
| -------------------- | --------------------------------------------------------------- |
| Current phase        | **Phase 6 — Product Surfaces**                                  |
| Current stage        | **Stages 6.1 and 6.2 complete** — browser pass done, below      |
| Last completed stage | Phase 5 complete — Stage 5.2 auth UI and route protection       |
| Dependency baseline  | `32ac7f9` — Dependabot queue empty, 0 open PRs                  |
| KB version           | `0.1.1`                                                         |
| Build health         | 🟢 621 API tests, 168 web tests, 60 SQL assertions, gates green |

### In progress: Phase 6 — Product Surfaces

Branch **`feat/phase-6-product-surfaces`**, not yet raised as a PR.

**Stages 6.1 and 6.2 are done, and the browser pass has now been run against
the live Supabase project.** What it proved, end to end, signed in as a real
user with a real ES256 token:

- Quick Start renders on a project with no bundle; the four-step wizard renders
  on one that has a bundle.
- `PUT` then `GET /v1/projects/{id}/bundle` round-trips byte-identically, and
  the workspace shows "Current constraints — Saved" after a reload. **This was
  6.1's one unticked criterion and it is now ticked.**
- The worked example (horror-comedy, PG-13, micro, US + India) produces **13
  conflicts — 2 HARD, 6 SOFT, 5 ADVISORY** — and the panel groups them as "2
  blocking, 6 needs a decision, 5 worth knowing".
- Before settling, the gate reads "Generation is blocked: 2 conflicts have to be
  settled first" and the sidebar shows **"Scope at this tier"**. After choosing
  "Generate to the strictest territory's ceiling" on both, it advances to
  "Acknowledge 6 conflicts to continue" and the sidebar switches to **"Scope for
  generation"** with the API's envelope, ceilings attributed to CBFC and MPA by
  name, and "What your choices changed — Drug use held at mild, down from
  moderate. Violence held at mild, down from moderate." The preview tightens,
  which was the other thing tests could not show.
- `POST /generate` with no choices returns **409** with the blocking conflicts
  and spends nothing.

**Use `pnpm dev:webpack` on this machine** — see the Turbopack note further
down; `pnpm dev` cannot resolve `radix-ui` from a path containing a space.

**The API runs on port 8001 on this machine, not 8000.** Port 8000 is held by
an unrelated project's Docker container (`mybill-api`). Start it with
`cd apps/api && uv run fastapi dev app/main.py --port 8001`, and
`NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` points there. Both are local
and untracked; the committed default is still 8000, so CI and deploys are
unaffected.

**Sign in with the local shortcut rather than Google** — set `DEV_LOGIN_EMAIL`
and `DEV_LOGIN_PASSWORD` in `apps/web/.env.local` against a Supabase user you
create by hand, and `/sign-in` grows a one-click button. It signs in as a real
user with a password, so the token is genuine and RLS still applies; it is a
second credential, not a bypass. `app/auth/dev-login/route.ts` returns 404
unless `NODE_ENV` is exactly `development`, verified against a real production
build. Setup is in `docs/runbook.md`. The user `dev-local@scriptgenie.test`
exists in the live project and `.env.local` already holds its password.

What landed in 6.1:

- `PUT`/`GET /v1/projects/{id}/bundle` — the draft had nowhere to live before
  this. `constraint_bundles` has held the shape since 4.1 and the repository
  could already write it, but no route exposed it. A draft is overwritten in
  place while it is still a draft, and left alone once a conflict report cites
  it, so a stored verdict never silently changes what it was about.
- `lib/constraints/` — `schema.ts` (zod, mirroring `ConstraintBundle`),
  `quick-start.ts` (three plain-English answers to a full bundle, derived from
  the KB rather than hardcoded), `field-help.ts` (tooltip copy as data),
  `scope-preview.ts` (tier scope in a producer's words).
- `components/features/constraints/` — the four-step wizard, Quick Start, the
  field row that carries help to both a pointer and a screen reader, and the
  workspace that owns the answers so 6.2's conflict panel can read them.
- Project creation, which did not exist: `/app` listed projects and linked to a
  route that 404'd.

What landed in 6.2:

- `lib/constraints/severity.ts` — the interruption policy as data, and
  `generationGate`, which is the only place that decides whether generation may
  be attempted. HARD blocks until a resolution that actually settles it is
  chosen, SOFT blocks until its checkbox is ticked, ADVISORY never blocks.
  Dismissing an advisory is a reading preference and is deliberately held in the
  panel's own state, out of reach of the gate.
- `lib/constraints/thresholds.ts` — content ceilings in words, each beside the
  board that imposed it, and the resolution deltas as sentences that do not
  claim an acknowledgement moved a bound.
- `hooks/use-conflict-report.ts` and `hooks/use-generation-envelope.ts` —
  debounced calls to `/conflicts/detect` and `/conflicts/resolve`. Both keep the
  last good answer on screen while a new one is in flight, refuse to send a form
  the schema rejects, and drop out-of-order responses by sequence number.
  Neither stores `pending` or `error`: both are derived from which request has
  an outcome, so a failure clears itself the moment an answer changes.
- `components/features/constraints/conflict-panel.tsx` and `scope-panel.tsx` —
  the grouped panel, and the preview that switches from the tier's ceiling to
  the API's `GenerationEnvelope` the moment one can be computed.
- `resolveConflictsAction`, which treats a 409 as `blocked` rather than as an
  error. A HARD conflict mid-resolution is a state the panel is already
  explaining; a red toast over it would be noise.

Known and deliberate:

- `pnpm lint` emits one **warning** on `wizard.tsx`: the React Compiler skips
  the component because `react-hook-form`'s `watch()` is not compiler-safe. It
  is a warning, the gate passes, and the alternative is hand-rolling the form.
- Ages are plain `z.number()` with `valueAsNumber` at the input, **not**
  `z.coerce.number()`. Coercion makes the schema's input type `unknown` and its
  output `number`; `useForm` is generic over one type, so the resolver stops
  typechecking under `exactOptionalPropertyTypes`. Same reason `genreSecondary`
  has no `.default()`.
- **The "this conflict is wrong" report is captured, not posted.**
  `POST /v1/variants/{id}/feedback` needs a variant id and at 6.2 no variant
  exists. The flagged rule ids sit in the workspace and the UI says plainly that
  they are filed with the next generation — which is the better record anyway,
  since a rule complaint is worth more with the output it produced attached.
  **Stage 6.3 must send them**, passing each flagged id as
  `false_positive_rule_id` once the variants come back.
- **The Generate button is disabled even when the gate is open.** Generation
  lands at 6.3, and a live button with no handler is the placeholder
  `scripts/no-placeholders.sh` exists to prevent. `GenerateGate` takes an
  optional `onGenerate`; supplying it is the only change 6.3 makes there.
- Changing any answer clears the chosen resolutions and acknowledgements. The
  API rejects a choice naming a rule that is not in the report it is judging, so
  carrying them forward would guarantee a 422 — and a decision about a conflict
  that no longer fires was not a decision about anything.
- Stages 6.3 and 6.4 are untouched. `generateVariants`, `listVariants`,
  `submitFeedback` and `exportProject` are already in `lib/api-client.ts`.

### Done: Phase 0 — Foundation & Governance

- **0.1** Credential removed from `prompt.txt`; gitleaks clean on working tree and full history. README, ADR 0001 (ADR process) and ADR 0002 (deterministic constraint layer). No licence file: default copyright applies until the owner chooses one.
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

### Done: Phase 2 — Deterministic Constraint Engines

The research contribution, and it contains **no LLM call anywhere**. 100% branch coverage on every engine and domain module.

- **2.1** 17 domain models in `app/domain/`, split across `enums` / `constraints` / `conflicts` / `variants` but exported flat from `app.domain` — import from there, not from the modules beneath. Frozen and `extra="forbid"` throughout.
- **2.2** `conflict_detector.detect(bundle, kb) -> ConflictReport`. Evaluates all 27 rules, renders templates with real values, sorts by severity then rule id. Golden test on the worked example (horror-comedy, PG-13, micro, US + India), 500-bundle determinism property test, p95 latency far inside 100 ms.
- **2.3** `resolution.apply_resolutions(report, choices, kb) -> ResolvedBundle`, re-running detection so resolution is proved rather than asserted.
- **2.4** `scope_parameterizer.parameterize(resolved, kb) -> GenerationEnvelope`. Strictest applicable value on every axis, with provenance naming the board behind each ceiling.
- **2.5** `archetype_selector.select(envelope, n, kb, seed=0)`. N distinct archetypes, seed permutes only equal scores.

**The pipeline composes:** `detect` → `apply_resolutions` → `parameterize` → `select`. Phase 3 consumes the `GenerationEnvelope` and its `prompt_fragment()`.

### Done: Phase 3 — Generation & Verification Layer

The first LLM calls in the project. 100% branch coverage on all four modules; every test drives `httpx.MockTransport`, so no test touches the network.

- **3.1** `app/services/groq_client.py`. Typed `LLMError` hierarchy, bounded jittered retries, a deadline covering all attempts and sleeps, a circuit breaker counting failed attempts, and token/latency/cost telemetry. The key is a `SecretStr` read once at header construction and never logged.
- **3.2** `app/engines/prompt_builder.py` with versioned templates in `app/prompts/`. Renders from structured fields only; `FORBIDDEN_PHRASES` blocks any wording that hands a settled decision back to the model.
- **3.3** `app/services/generation_service.py`. N concurrent calls, one-shot repair on unusable output, partial success, batch deadline.
- **3.4** `app/engines/verifier.py`. PASS / FLAGGED / NEEDS_REVIEW per axis. A check that could not run never becomes a pass.

**GROQ_MODEL is `openai/gpt-oss-120b`**, confirmed against Groq's documentation: the production model with strict JSON-schema constrained decoding, where Llama offers `json_object` only. Free-tier limits are identical (30 RPM / 8K TPM / 1K RPD).

**No live key has ever been used.** Every stage is verified against a mocked transport, which is what the acceptance criteria ask for. The first real Groq call will happen when someone sets `GROQ_API_KEY`, and the free tier's 8K TPM is low enough that a five-variant batch may hit it — the client's rate-limit handling exists for that.

### Done: Phase 4 — Backend Platform

The service becomes multi-user. Everything below is verified against a real PostgreSQL and mocked HTTP transports; no test touches the network and no live credential has been used.

- **4.1** Eleven tables in `supabase/migrations/`, RLS on every one. Ownership is denormalised onto each user table so every policy is the single comparison `owner_id = (select auth.uid())`, and pinned by **composite foreign keys** — each parent carries `unique (id, owner_id)` and each child references `(parent_id, owner_id)` — so a row cannot name one user's parent while claiming a different owner. `profiles` is created by a trigger on `auth.users`; `kb_versions` and `usage_events` have no client write policy at all. 60 SQL assertions run against a throwaway Postgres via `pnpm test:db`, and in CI against a service container.
- **4.2** `app/core/security.py` verifies Supabase access tokens against the project JWKS, with a cache that survives a brief Supabase outage and a refresh floor so a token carrying a random `kid` cannot turn every request into an outbound fetch. Legacy HS256 projects are supported, but the algorithm family comes from configuration and never from the token header. Web side: `@supabase/ssr` clients, `proxy.ts` refreshing the session and guarding `/app`, and `/auth/callback` exchanging the PKCE code.
- **4.3** Nine v1 routes, RFC 9457 problem details, request-id propagation, and `openapi.json` + `apps/web/types/api.ts` generated and committed with a CI job that fails on drift. `POST /generate` returns 409 with the blocking conflicts and spends nothing.
- **4.4** Per-user generation limits counted in the database over a rolling window, a semaphore capping this process's outbound model calls, ASGI-level request body limits, and usage accounting totalled through a contextvar meter and written under the service role.

**610 API tests at 99% coverage**, 30 web tests, 60 SQL assertions.

### Done: Phase 5 — Frontend Foundation

The app becomes something a person can use. 80 web tests.

- **5.1** Tailwind theme tokens in `app/globals.css`, the seventeen shadcn primitives vendored **unmodified**, and the signed-in shell on top of them: header, nav, user menu, theme toggle, error boundaries, loading skeletons. Customisation flows through props, `className` and wrappers in `components/features/`; `scripts/check-ui-primitives.sh` enforces that against the merge base and runs both in `pnpm verify` and as its own CI job. `lib/api-client.ts` is the typed vocabulary over `lib/api/server.ts`, drawing every shape from the generated `types/api.ts`.
- **5.2** Landing page carrying the scope statement as a callout rather than a footnote, Google sign-in on the design system, `SessionSync` keeping server-rendered markup honest about who is signed in, and a closed set of auth error messages.

### Next: Stage 6.3 — Generation & variant cards

Variant cards (6.3), then comparison and export (6.4). `lib/api-client.ts`
already exposes every route these need.

### Useful facts for the next session

- Run everything: `pnpm verify` (web + scripts), `cd apps/api && uv run pytest`, and `pnpm test:db` (needs docker or a `DATABASE_URL` pointing at an empty database).
- **`pnpm codegen` after any route or schema change.** `apps/api/openapi.json` and `apps/web/types/api.ts` are generated, committed, and checked in CI; neither is ever edited by hand.
- The API talks to Supabase two ways and the difference is a security boundary. Everything a user owns goes through PostgREST **under that user's own access token**, so RLS is enforced by the database on every statement. The service role, which bypasses RLS, is reachable only through `SupabaseClient.as_service()` — insert-only, and used for `usage_events` and nothing else.
- Routes never build a response body. They raise from the `app.core.errors` hierarchy and `app.core.problem_details` renders it; each class fixes its own status and a stable `type` URI, which is what clients branch on.
- Request ids live in a `ContextVar`, so an exception handler or a service three calls deep can reach one without it being threaded through every signature. The same mechanism carries the usage meter: asyncio tasks inherit a copy of the context, so the N concurrent variant tasks share the meter object their request installed and no other request can observe it.
- `RequestSizeLimitMiddleware` is raw ASGI, not `BaseHTTPMiddleware`. The latter gives no access to the receive channel, so the streaming half — the half that catches a chunked body with no `Content-Length` — cannot be written there at all.
- The generation gate re-derives the conflict report from the submitted bundle rather than reading back a stored one. A report is a pure function of a bundle and a KB version, so re-deriving costs microseconds and removes the drift that would let a HARD conflict through.
- Two latent bugs were found by the new tests and fixed: `ALLOWED_ORIGINS` in a `.env` crashed startup (pydantic-settings JSON-decodes list fields before validators run — the field now carries `NoDecode`), and the PostgREST error path passed `"message"` in logging's `extra` dict, which is a reserved `LogRecord` attribute and raises while reporting a failure. All `extra=` dicts are now audited against the reserved set.
- Starlette's `ServerErrorMiddleware` sits **outside** application middleware, so a 500 never passes back through `RequestIdMiddleware`. The request id is stamped where the problem document is built, not on the way out.
- The full pipeline is `detect` → `apply_resolutions` → `parameterize` → `select` → `generate_variants` → `verify`. The first four are deterministic and LLM-free; the last two are the only places a model is called.
- Prompt templates (`apps/api/app/prompts/`) and prompt snapshots are in `.prettierignore` deliberately. The pre-commit formatter was rewriting them, and reflowing a prompt changes what the model receives with no diff anyone reviewed. Regenerate snapshots with `uv run python -m tests.regenerate_prompt_snapshots`, never by hand.
- `gitleaks` is installed at `~/.local/bin/gitleaks`; hooks warn rather than fail if it is missing from `PATH`.
- **`SUPABASE_JWT_SECRET` must be empty on this project, and having it set broke every authenticated route.** It was filled in in `apps/api/.env` and was blanked on 2026-07-31. `app/core/security.py` treats the presence of that value as the whole decision: set it, and tokens are verified with **HS256 against the secret** and the JWKS is never consulted. This project signs asymmetrically — `GET /auth/v1/.well-known/jwks.json` publishes one **ES256** key, and a real access token minted from it carries `{"alg":"ES256","kid":"5bc5ce3b-…"}`. So every genuine token failed verification and every `/v1/*` call returned 401 while `/health` stayed green. The variable is only for legacy projects still on symmetric signing keys; the dashboard shows a "JWT secret" regardless, which is what makes this easy to fill in by mistake. Check the token, not the dashboard: decode the header of a real token and read `alg`.
- **`SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL` are the bare project origin — `https://<ref>.supabase.co` — and nothing else.** `app/core/config.py` appends `/auth/v1` and `/rest/v1` itself, so pasting the REST endpoint from the Supabase dashboard produces `…/rest/v1/auth/v1` and every token verification and PostgREST call fails. This was actually in `apps/api/.env` and was fixed on 2026-07-29. It does **not** announce itself: the web app degrades quietly rather than erroring, so sign-in simply never works.
- **A 500 on every route including `/` and a nonexistent path, while `/favicon.ico` returns 200, means the proxy is throwing — almost always a missing `NEXT_PUBLIC_*`.** `favicon.ico` is the one path excluded from the `proxy.ts` matcher, so it is the tell: everything the matcher covers fails ahead of routing, which is why even a static page and a 404 come back as 500. Reproduced deliberately by removing `NEXT_PUBLIC_SUPABASE_URL` and rebuilding. Remember these are inlined **at build time** — setting them in Vercel without redeploying changes nothing, and a cached build can carry the old values forward.
- **`pnpm build` and `pnpm dev` both fail on this machine and pass in CI, and the cause is the checkout path, not the code.** This working copy lives under `…/SEM 7/open elective/…`, and Turbopack cannot resolve a pnpm symlink whose realpath contains a space: `radix-ui` is the only runtime dependency whose `.pnpm` directory is reached that way, so every shadcn primitive fails with `Module not found: Can't resolve 'radix-ui'`. Verified by copying the tracked tree to a space-free path and building there, where it succeeds. `next build --webpack` also succeeds in place, because webpack resolves through Node.
  - **The dev server hits the same wall**, surfacing as an overlay on first render of `components/ui/tooltip.tsx` via `providers.tsx`. Use **`pnpm dev:webpack`** on this machine — verified serving 200 with no module-not-found. `dev` is left on Turbopack because the fault is this checkout's path, not the repo's.
  - **Do not "fix" this in `next.config.ts`.** Setting `turbopack.root` does not help in either direction: pinned to `apps/web` the build then cannot resolve `next` itself, whose symlink also points outside that root. The only real fixes are moving the checkout or waiting for Turbopack, and neither belongs in committed configuration.
  - `pnpm verify` is unaffected — `tsc` and Vitest use Node's own resolution — so a genuine build break can still hide behind this. Check with `next build --webpack` before concluding the build is fine.
- **Local `.env` files are allowlisted in `.gitleaks.toml`, and that is not a hole — do not "fix" it.** The working-tree pass is `gitleaks detect --no-git`, which walks the filesystem and does not consult `.gitignore`, so without the allowlist `pnpm verify` fails on every machine that has a filled-in `.env`. A gate that always fails is a gate people stop reading. "A `.env` must never be tracked" is instead owned by `scripts/env-guard.sh`, which fails on the file being tracked at all regardless of contents, and which runs in `security.yml` **and** in the pre-push hook — the hook entry is what stops a `git add -f apps/api/.env` from passing every local gate and only being caught after the push. The allowlist enumerates the ignored names rather than using `\.env(\..*)?$`, because that would also cover the committed `.env.example` files; a real value in one of those is caught by both gitleaks and env-guard. All four arms were verified against real inputs, not assumed.
- The KB loads via `app.kb.loader.load_knowledge_base()`; `load_data_file(stem)` validates one file without cross-file checks.
- Conflict rule predicates are declarative: `dimension_exceeds`, `scope_exceeds`, `ordinal_exceeds`, `equals`, `not_equals`, `includes`, `count_gte`, plus `all_of` / `any_of` / `none_of`. The detector implements exactly this vocabulary and no more; adding a type here without adding it to `conflict_rule.schema.json` would let a rule exist that the schema calls invalid. `any_of` and `none_of` are unused by the shipped data and are tested against synthetic rules.
- Ordinal enums (`vfx_complexity`, `period_setting`, `action_complexity`) compare by position in the list declared in `common.schema.json`. `app.domain.OrdinalVocabulary` enforces this: those enums raise `TypeError` on `<`, `<=`, `>`, `>=` and expose `.rank`, because `StrEnum` would otherwise answer alphabetically and be wrong without erroring. `ContentLevel` is numeric and compares normally. `narrative_economy` is deliberately not ordinal — the only rule reading it tests equality.
- Engines live in `app/engines/`: `conflict_detector`, `resolution`, `scope_parameterizer`, `archetype_selector`, plus `territory` (shared classification-equivalence and restriction logic) and `errors`. `territory.py` is shared deliberately: if detection and parameterisation read a territory differently, the parameteriser could hand the generator an envelope the detector had already refused.
- Territory restrictions are gated by `applies_from_classification`, and an unmappable classification applies the restriction. An unnecessary conflict carries an explanation and resolutions; a missed one carries a refused certificate.
- `app/domain/enums.py` restates values the knowledge base schemas own. `tests/test_domain_enums.py` reads those schema files and asserts member-for-member equality, so adding a dimension or severity to the knowledge base without adding it here fails a test instead of producing an engine that ignores the new value.
- Three dependency majors are held in `.github/dependabot.yml` and must not be taken by hand. Each entry carries its reason and the condition for lifting it.
  - **typescript** at 5.x — TS 7.0 typechecks this workspace cleanly, but `typescript-eslint` 8.65 refuses to load against it and `pnpm lint` exits 2. Retry when TS >= 7.1 support lands (typescript-eslint#10940).
  - **eslint** at 9.x — `eslint-config-next` pulls `eslint-plugin-react` 7.37.5, which calls the pre-10 context API and throws `contextOrFilename.getFilename is not a function`. Retry when that config ships eslint 10 compatible plugins.
  - **@types/node** at 22.x — matches `NODE_VERSION` and the `engines` floor. Raise all three together, or the types will describe APIs the runtime does not have.
- The pre-commit hook is the one gate CI never exercises. When `lint-staged`, `husky` or the hook scripts change, check both arms by hand: a badly formatted staged file must be rewritten, and a real lint violation must still abort and revert the commit.
- commitlint ignores commits carrying Dependabot's sign-off trailer, because its bodies embed release notes past 100 characters and cannot be reformatted. The match is on the trailer, not on `chore(deps)`, so human dependency commits are still fully checked.

### Open blockers / decisions needed

1. ✅ **Resolved — the leaked key has been rotated.** It was removed from `prompt.txt` at Stage 0.1 and never entered git history (`gitleaks detect` over the full history is clean), so the exposure was working-directory only and no history rewrite was needed. The old credential is now revoked at the provider; `apps/api/.env` holds the replacement, gitignored and untracked. Nothing further is outstanding here.
2. ✅ **Resolved at Stage 3.1.** `GROQ_MODEL` is `openai/gpt-oss-120b`, confirmed against Groq's documentation.
3. Confirm the API hosting target (Fly.io or Render) before Stage 8.2.
4. ✅ **Resolved.** CI now runs on `github.com/samarthkolur/scriptgenie` and all 12 checks pass on `main`. Two runner-specific problems surfaced and were fixed on first contact (`880f74d`, `5e9e741`), which is exactly why this was worth doing before Phase 2 code landed.
5. ⚠️ **Branch protection is on, but three checks are not required yet.** `main` now enforces linear review with `enforce_admins` on, force pushes and deletions blocked, and **12** required contexts — including all five security jobs, so Stage 0.4 and 0.5 are satisfied. Missing from the required list are the three jobs added after it was configured: **`Database`**, **`API contract`** (Phase 4) and **`UI primitives unmodified`** (Phase 5). They run on every PR and are green, but nothing blocks a merge if they fail. Add them and the count becomes **15**.
6. **No licence.** Default copyright applies; no rights are granted. Stage 9.2 (open schema publication) is blocked until that is decided, and the decision may be constrained by university IP policy and the PS241 terms. Do not default one in.
7. ✅ **Resolved at Stage 2.2 and re-asserted at 4.3.** The detector produces the worked example's conflicts, and `test_api_v1` asserts the API refuses to generate while its HARD conflicts are unresolved.
8. ⚠️ **The Supabase project now exists and the schema is applied; Google sign-in is not yet enabled.** Both migrations were applied to the live project on 2026-07-29 and verified against it: 11 tables, RLS enabled on every one with no exceptions, policy counts matching the design, and the `on_auth_user_created` trigger present. Confirmed live that `kb_versions` reads anonymously while `projects` returns nothing without a user token, which is RLS doing its job.

   **Google sign-in is now enabled and wired correctly.** `GET /auth/v1/settings` reports `"google": true`, and `/auth/v1/authorize?provider=google` redirects to `accounts.google.com` carrying a real `client_id` with `redirect_uri` set to Supabase's own `/auth/v1/callback` — which is the value Google Cloud must hold, not ours. That is the mistake the runbook calls the most common one, and it is not present here.

   Two things remain:
   - ⚠️ **The Redirect URL allow-list is missing its `/auth/callback` entries, and this is now confirmed rather than suspected.** On 2026-07-30 Google sign-in returned to `http://localhost:3000/?code=…`. That is Supabase discarding a `redirect_to` it does not recognise and substituting the Site URL — a new project ships with Site URL `http://localhost:3000` and no redirect entries, and URL Configuration has never been touched. Fix in **Authentication → URL Configuration → Redirect URLs**: add `http://localhost:3000/auth/callback` plus the two deployment entries in `docs/runbook.md` §2.3. **The path is required** — a bare `http://localhost:3000` entry does not match, because Supabase globs the whole URL.

     Nothing in this repository causes it: `git grep localhost:3000` over tracked files finds only the API's CORS default and the runbook, `components/features/auth/sign-in-with-google.tsx` asks for `/auth/callback` correctly, and `proxy.ts` never redirects that route. It cannot be checked from outside either — passing `redirect_to=https://evil.example/…` to `/auth/v1/authorize` still returns a 302 to Google, because Supabase validates the value when the callback returns rather than when authorize is called. Read the list in the dashboard and confirm it holds only our origins, including the wildcard entry for previews. Our own `/auth/callback` is separately protected: the `next` parameter goes through `safeReturnPath`, which is covered by tests.

     **The app no longer fails silently when this is wrong.** `proxy.ts` calls
     `strandedAuthResponse` (`lib/auth/redirects.ts`), which forwards an
     authorisation response delivered to the site root on to `/auth/callback`
     with its query intact, so Google sign-in now completes even with the
     allow-list unfixed. Verified live: `GET /?code=…` answers `307` to
     `/auth/callback?code=…`. This is a safety net, not the fix — it only covers
     the site root of an origin already serving the app, and cannot help a
     preview deployment whose Site URL points at production, where the user is
     sent to a different host and the PKCE verifier cookie is left behind. Still
     add the entries.

   - **`kb_versions` is empty.** Nothing reads it at runtime — it is provenance, not configuration — so it blocks nothing, but an export will not name a KB version until a row is seeded.

   Connection note for whoever comes next: direct connections to `db.<ref>.supabase.co` are **IPv6-only** and unroutable from the author's network. Use the IPv4 session pooler at `aws-0-ap-southeast-2.pooler.supabase.com:5432` with username `postgres.<ref>` — session mode, port 5432, because the transaction pooler on 6543 cannot run DDL.
