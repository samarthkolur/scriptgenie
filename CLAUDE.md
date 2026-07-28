# CLAUDE.md — ScriptGenie (CASIE)

Operating manual for any AI agent or developer working in this repository.
**Read this file top to bottom before touching code. Update `## CURRENT STATUS

<!-- ============================================================
     UPDATE THIS ENTIRE SECTION AT THE END OF EVERY SESSION.
     Keep it factual and short. It is the handoff contract.
     ============================================================ -->

**Last updated:** 2026-07-28
**Updated by:** Samarth D Kolur

| Field                | Value                                                    |
| -------------------- | -------------------------------------------------------- |
| Current phase        | **Phase 4 — Backend Platform**                           |
| Current stage        | **Stage 4.1** (not started)                              |
| Last completed stage | Phase 3 complete — Stage 3.4 verification                |
| Dependency baseline  | `32ac7f9` — Dependabot queue empty, 0 open PRs           |
| KB version           | `0.1.1`                                                  |
| Build health         | 🟢 390 API tests at 99.27%, 3 web tests, all gates green |

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

### Next: Phase 4 — Backend Platform

Supabase schema, auth, API surface, rate limits.

### Useful facts for the next session

- Run everything: `pnpm verify` (web + scripts) and `cd apps/api && uv run pytest`.
- The full pipeline is `detect` → `apply_resolutions` → `parameterize` → `select` → `generate_variants` → `verify`. The first four are deterministic and LLM-free; the last two are the only places a model is called.
- Prompt templates (`apps/api/app/prompts/`) and prompt snapshots are in `.prettierignore` deliberately. The pre-commit formatter was rewriting them, and reflowing a prompt changes what the model receives with no diff anyone reviewed. Regenerate snapshots with `uv run python -m tests.regenerate_prompt_snapshots`, never by hand.
- `gitleaks` is installed at `~/.local/bin/gitleaks`; hooks warn rather than fail if it is missing from `PATH`.
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

1. **🔴 Still open — rotate the leaked key.** The credential was removed from `prompt.txt` and never entered git history, but it stays valid until revoked at the provider.
2. Confirm the Groq model id for `GROQ_MODEL` against current Groq documentation at Stage 3.1.
3. Confirm the API hosting target (Fly.io or Render) before Stage 8.2.
4. ✅ **Resolved.** CI now runs on `github.com/samarthkolur/scriptgenie` and all 12 checks pass on `main`. Two runner-specific problems surfaced and were fixed on first contact (`880f74d`, `5e9e741`), which is exactly why this was worth doing before Phase 2 code landed.
5. **Branch protection on `main` is still not enabled**, and the remote no longer blocks it — this is now just an unticked setting. Until it is on, the gates are advisory: nothing stops a direct push to `main`. Turn it on and require the 12 checks.
6. **No licence.** Default copyright applies; no rights are granted. Stage 9.2 (open schema publication) is blocked until that is decided, and the decision may be constrained by university IP policy and the PS241 terms. Do not default one in.
7. Stage 1.5 encodes the worked example's three conflicts at the severities the research assigns, and tests assert that. Whether the detector _produces_ that exact report is a Stage 2.2 test, since no detector exists yet.
