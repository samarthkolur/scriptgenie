# ScriptGenie

**Constraint-Aware Script Ideation Engine (CASIE)** — generates structurally diverse, production-viable plot variants under simultaneous genre, audience, budget and censorship constraints.

> NVIDIA PS241 — Media & Entertainment. Built by **Samarth D Kolur**.

---

## The problem

Existing AI writing tools treat production constraints as suggestions. A writer asks for "a PG-13 horror film on a micro-budget for US and India" and gets back a story that needs eight locations, a stunt sequence, and content that would trigger mandatory cuts at CBFC. The constraints were in the prompt; nothing enforced them.

ScriptGenie enforces them **before** generation, deterministically.

## How it works

```
Constraint bundle          genre · audience + rating · budget tier · territories
        │
        ▼
Layer 1  Conflict detection      deterministic rules over a curated knowledge base
        │                        → HARD (blocks) / SOFT (acknowledge) / ADVISORY (info)
        │                        → same bundle always produces the same report
        ▼
Layer 2  Scope parameterization  budget tier → max locations, max cast, VFX ceiling,
        │                        period setting, action complexity
        │                        rating × territory → six content-dimension thresholds
        ▼
Layer 3  Variant generation      one distinct narrative archetype assigned per variant
        │                        before the LLM call, then N parallel Groq calls
        ▼
         Verification            extracted locations/cast/content re-checked against
                                 the envelope — flagged, never silently passed
```

Three rules define the architecture:

1. **The LLM never reasons about production constraints.** Conflict detection and scope parameterization are deterministic Python over versioned JSON. The model only writes narrative inside an already-validated envelope.
2. **Budget tier is a narrative shaper, not a label.** Scope bounds are numeric, injected as structured prompt fields, and re-verified after generation.
3. **Archetypes are assigned by the system before generation.** Structural diversity is architectural, not a side effect of sampling temperature.

## Stack

| Layer           | Technology                                                                     |
| --------------- | ------------------------------------------------------------------------------ |
| Frontend        | Next.js (App Router, TypeScript strict) + shadcn/ui + Tailwind                 |
| Backend         | FastAPI (Python 3.12, Pydantic v2, `uv`)                                       |
| LLM             | Groq API                                                                       |
| Database & Auth | Supabase Postgres + Supabase Auth (Google OAuth)                               |
| CI              | GitHub Actions — lint, typecheck, tests, secret scan, dependency audit, CodeQL |

## Repository layout

```
apps/web              Next.js frontend
apps/api              FastAPI backend (deterministic engines live in app/engines/)
packages/constraint-kb  versioned JSON knowledge base — single source of domain truth
supabase/migrations   forward-only SQL
docs/                 ADRs, API reference, runbook
```

## Local development

**Prerequisites:** Node 22.13+, pnpm 9+, Python 3.12+, [uv](https://docs.astral.sh/uv/), and the [Supabase CLI](https://supabase.com/docs/guides/cli).

```bash
# install
pnpm install
cd apps/api && uv sync && cd ../..

# configure — copy and fill in, never commit the result
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env

# run
pnpm dev            # web on :3000
pnpm dev:api        # api on :8000
```

Full environment variable reference: [docs/runbook.md](docs/runbook.md).

## Quality gates

```bash
pnpm verify   # format check → lint → typecheck → no-placeholders → tests → secret scan
```

The same gates run on every pull request. `main` is protected and requires all of them.

## Documentation

| Document                                                                 | Purpose                                                 |
| ------------------------------------------------------------------------ | ------------------------------------------------------- |
| [CLAUDE.md](CLAUDE.md)                                                   | Engineering operating manual — read before contributing |
| [BUILD_PLAN.md](BUILD_PLAN.md)                                           | Phased build plan and current progress                  |
| [PS241_Research_Gap_Analysis_v2.txt](PS241_Research_Gap_Analysis_v2.txt) | Requirements source of truth                            |
| [docs/adr/](docs/adr/)                                                   | Architecture decision records                           |
| [SECURITY.md](SECURITY.md)                                               | Vulnerability disclosure                                |

## Scope

ScriptGenie is a **pre-development ideation tool**. It produces beat-level plot variants — not screenplays, not scene dialogue, not formatted scripts. Its output is the input to script development, not a replacement for it.

Generated variants are reported as _verified for scope_ against the parameters listed on each card. They are never presented as certified compliant with any rating board. Classification decisions belong to CARA, BBFC, CBFC and FSK, not to this software.

## Copyright

Copyright © 2026 Samarth D Kolur. All rights reserved.

No licence is granted. Without one, default copyright applies: others may view
this code but have no right to use, copy, modify or distribute it. If that is
not the intent, add a licence file — that is a decision for the owner, and it
should be checked against any applicable university or problem-statement terms
before publishing.
