# ADR 0002 — Constraint reasoning is deterministic and lives outside the LLM

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** Samarth D Kolur

## Context

The research gap analysis (PS241_Research_Gap_Analysis_v2.txt, §4 Reason 3) establishes that LLMs cannot reliably reason about constraint conflicts: they satisfy constraints probabilistically and hold no representation of the logical relationship between a budget-tier scope bound and a genre convention. Separately (§4 Reason 2), alignment training gives models a single undifferentiated content threshold that does not correspond to any rating framework — Mahomed et al. (2024) measured ChatGPT's moderation endpoint flagging ~70% of aired TV scripts, including PG-rated material.

The tempting shortcut is to put the knowledge base into a system prompt and ask the model to detect conflicts and respect scope bounds. It demos well and it is much less code.

## Decision

Constraint reasoning is implemented as deterministic Python over a versioned JSON knowledge base, in `apps/api/app/engines/`. Specifically:

- `conflict_detector` evaluates rule predicates. **No LLM call.**
- `scope_parameterizer` computes numeric scope bounds and content thresholds. **No LLM call.**
- `archetype_selector` assigns one distinct archetype per variant. **No LLM call.**

The LLM is invoked at exactly two points: generating narrative inside an already-validated envelope, and structured extraction during post-generation verification. In neither case is it asked to *decide* whether a constraint is satisfiable.

Modules under `engines/` are pure functions — no network, no database, no filesystem. The knowledge base is passed in as data.

**Guarantee:** the same constraint bundle evaluated against the same knowledge base version produces a byte-identical conflict report, every time.

## Consequences

- Conflict detection is unit-testable to 100% branch coverage and benchmarkable (target p95 < 100 ms). A probabilistic implementation would be neither.
- Users get the same answer twice for the same input, which is a precondition for trusting a tool that blocks their work.
- The knowledge base becomes a maintained asset with a version, a changelog and citations — and a publishable research artifact in its own right (§8 of the research doc).
- Cost: domain data must be curated by hand. Encoding four rating systems, four budget tiers, ten genres, five territories and the conflict rule set is real work that cannot be shortcut by asking a model to generate it. Generated domain data would be plausible and wrong, which is the worst possible failure mode for a compliance-adjacent tool.
- Adding a new territory or rating system is a data change, not a code change.

## Alternatives considered

- **Knowledge base in the system prompt, LLM detects conflicts** — rejected: non-deterministic, unverifiable, and reproduces exactly the failure documented in the source research. Also unbounded in cost as the rule set grows.
- **Fine-tuning a model on constraint compliance** — rejected: requires a labelled dataset that does not exist (research doc Risk 6), and still yields probabilistic enforcement.
- **A general-purpose constraint solver (SMT/ASP) over the rule set** — deferred, not rejected. The current rule set is small enough for direct predicate evaluation, and the explanation quality matters more than solver generality. Revisit if the rule set exceeds a few hundred interacting rules.
