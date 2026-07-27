# ADR 0001 — Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** Samarth D Kolur

## Context

ScriptGenie's value depends on a small number of architectural commitments that are easy to erode under delivery pressure — most importantly that constraint reasoning stays deterministic and outside the LLM. Without a written record, a future contributor (or a future session) can quietly "simplify" the conflict detector into a prompt and destroy the product's differentiator without anyone noticing in review.

## Decision

Every architecturally significant decision is recorded as a numbered Markdown file in `docs/adr/`, using this template: Context, Decision, Consequences, Alternatives considered.

A decision is architecturally significant if it does any of the following:

- adds, removes or replaces a technology in the locked stack
- changes the boundary between the deterministic engines and the LLM
- changes the knowledge base schema in a backwards-incompatible way
- changes the authentication, authorization or data isolation model
- introduces a new external service dependency

ADRs are immutable once accepted. A reversal is a new ADR that supersedes the old one, and the old one is edited only to add a `Superseded by ADR NNNN` line to its status.

## Consequences

- Review has a concrete artifact to point at when a PR drifts from the architecture.
- New contributors and new sessions can reconstruct _why_ the system is shaped this way without archaeology through git history.
- Small overhead per significant decision; explicitly not required for routine implementation choices.

## Alternatives considered

- **Decisions in commit messages only** — rejected: not discoverable, and Conventional Commit subjects are too short to carry rationale.
- **A single running DECISIONS.md** — rejected: merge conflicts on every parallel branch, and no stable identifier to cite from code review.
