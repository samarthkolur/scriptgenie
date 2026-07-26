# ScriptGenie Production Build Plan

**Project:** ScriptGenie: A Constraint-Aware AI Screenplay Generator

**Author:** Samarth D Kolur
**GitHub:** samarthkolur

**Email:** samarthdkolur1@gmail.com

**Goal:** Deliver an end-to-end production-ready screenplay generation platform that generates multiple screenplay variants, validates budget and content constraints, supports Google auth, and ships with production-grade engineering practices.

---

## 1. Product Scope

ScriptGenie will be a constraint-aware AI writing platform for screenplay ideation and outline generation. Users will provide:

- Genre
- Audience category
- Budget level
- Censorship rating
- Optional theme, premise, or prompt

The system will output:

- A logline and core plot summary
- At least three distinct screenplay variants
- Scene-by-scene outlines with INT./EXT. structure
- Budget feasibility scoring and cost notes
- Censorship and audience compliance adjustments
- Constraint annotations and revision rationale

The implementation must be modular, production-safe, and ready for real-world use by the end of the build.

---

## 2. Mandatory Tech Stack

### Frontend
- Next.js
- shadcn/ui for UI components
- Modular component architecture
- Do not modify shadcn/ui source files in `components/ui`
- Use props and wrappers to customize behavior and styling

### Backend
- FastAPI
- Python-based API layer for orchestration, validation, and scoring
- Separate service boundaries for generation, validation, and reporting

### AI / LLM Access
- Groq API for model inference
- Structured prompting for screenplay generation and revision loops
- Output normalization for predictable downstream validation

### Data and Auth
- Supabase for database
- Supabase Auth for authentication
- Google auth integration through Supabase

### Delivery and Quality
- Conventional commits
- GitHub Actions for lint, test, security, and build checks
- Prettier hook for frontend formatting
- Environment and secret hygiene checks
- Production-grade validation and release process

---

## 3. Product Architecture

### 3.1 High-Level Flow
1. User signs in with Google.
2. User submits screenplay constraints and prompt.
3. Next.js frontend sends the request to FastAPI.
4. FastAPI validates input, builds generation context, and calls Groq.
5. The generator produces multiple screenplay variants.
6. Validation modules check budget, censorship, audience, and structural constraints.
7. If a variant fails, the revision loop repairs it and re-validates.
8. Valid outputs are stored in Supabase and rendered in the UI.
9. The user can export, compare, and revisit previous generations.

### 3.2 Recommended Service Boundaries
- `web`: Next.js app and UI layer
- `api`: FastAPI backend and orchestration
- `shared`: shared schemas, types, and prompt contracts
- `db`: Supabase schema, policies, and seed data
- `infra`: CI workflows, hooks, and deployment support files

### 3.3 Core Domain Modules
- Auth and session management
- Prompt construction and template management
- Screenplay generation orchestration
- Budget validator
- Censorship validator
- Audience suitability validator
- Revision planner and repair loop
- Variant comparison and reporting
- Audit logging and observability

---

## 4. Engineering Principles

- Build modular features, not monoliths.
- Keep generation logic isolated from validation logic.
- Treat all LLM output as untrusted until validated.
- Prefer typed request and response contracts.
- Keep every output explainable with explicit constraint notes.
- Optimize for maintainability, traceability, and safe iteration.
- Fail closed on missing env values, invalid auth, or unsafe content.

---

## 5. Phase Plan

## Phase 0: Product and Foundation Setup

### Stage 0.1: Requirements lock
- Convert the project report into concrete functional requirements.
- Define the exact generation outputs and validation rules.
- Freeze the MVP scope and identify future enhancements.

### Stage 0.2: Repo and workspace setup
- Initialize the Next.js frontend.
- Initialize the FastAPI backend.
- Create a shared contract layer for schemas and enums.
- Establish folder conventions for modular development.

### Stage 0.3: Tooling baseline
- Set up ESLint for frontend code quality.
- Set up Prettier for formatting.
- Add backend linting and formatting tools.
- Add pre-commit hooks to block broken formatting and unsafe files.
- Add environment variable templates and secret scanning checks.

### Stage 0.4: Definition of done
- The app can be installed and run locally.
- Linting and formatting pass.
- The repository has a documented setup path.
- Secrets are not stored in git.

---

## Phase 1: Design System and Frontend Shell

### Stage 1.1: UI foundation
- Build the app shell with Next.js.
- Set up route structure for auth, dashboard, generation flow, history, and reports.
- Use shadcn/ui components via wrappers only.

### Stage 1.2: Interface architecture
- Create reusable layout, form, result, and comparison components.
- Keep feature components small and domain-specific.
- Centralize shared state only where necessary.

### Stage 1.3: User journey screens
- Landing page
- Sign-in page
- Prompt submission page
- Results comparison page
- History and saved outputs page
- Settings and account page

### Stage 1.4: Frontend quality gates
- Add formatting checks.
- Add type checking.
- Add component-level test coverage where practical.
- Ensure responsive behavior on desktop and mobile.

### Deliverable
- A polished but minimal frontend shell with navigation, auth entry points, and prompt submission forms.

---

## Phase 2: Authentication and Data Layer

### Stage 2.1: Supabase project setup
- Create Supabase project.
- Define database schema for users, generations, variants, validations, and exports.
- Configure Row Level Security.

### Stage 2.2: Google auth integration
- Configure Google OAuth with Supabase Auth.
- Support sign-in, sign-out, session refresh, and protected routes.
- Persist user profile metadata.

### Stage 2.3: Data modeling
- Model screenplay requests as immutable generation jobs.
- Store each variant separately for comparison and revision history.
- Store validation outcomes as structured records.

### Stage 2.4: Access control and privacy
- Restrict user data to the owning account.
- Add policy-level protections for all tables.
- Document the auth and privacy model.

### Deliverable
- Secure login and durable storage for generation history and validation artifacts.

---

## Phase 3: FastAPI Backend and Contract Layer

### Stage 3.1: API skeleton
- Build FastAPI app structure.
- Add health checks, versioning, and structured logging.
- Create request and response schemas.

### Stage 3.2: Contract-first development
- Define shared request objects for prompt input.
- Define response objects for screenplay variants and reports.
- Validate all inputs at the boundary.

### Stage 3.3: Generation orchestration
- Implement the orchestration endpoint for screenplay generation.
- Break generation into deterministic substeps.
- Add retries and failure handling for external API calls.

### Stage 3.4: Persistence integration
- Store request metadata and final outputs in Supabase.
- Track generation status transitions.
- Preserve audit details for later inspection.

### Deliverable
- A production-shaped backend that can accept a prompt, orchestrate generation, and persist results reliably.

---

## Phase 4: Groq-Powered Generation Engine

### Stage 4.1: Prompt design
- Create structured prompts for logline, outline, scenes, and variants.
- Use explicit output schemas and formatting constraints.
- Separate creative prompting from compliance prompting.

### Stage 4.2: Variant generation
- Generate at least three distinct screenplay variants per request.
- Encourage different narrative angles and tonal choices.
- Keep the outputs comparable in structure.

### Stage 4.3: Determinism controls
- Use stable prompt templates.
- Normalize the output into a predictable JSON-like structure before rendering.
- Add fallback handling for malformed or incomplete model responses.

### Stage 4.4: Prompt safety
- Reject unsafe or malformed user input.
- Prevent prompt injection from user fields.
- Sanitize all model-facing context.

### Deliverable
- A reliable generation layer that consistently produces structured screenplay candidates.

---

## Phase 5: Constraint Validation Engine

### Stage 5.1: Budget validator
- Count locations from scene headings.
- Count character usage.
- Detect expensive production cues such as VFX-heavy actions.
- Score outputs against the selected budget tier.

### Stage 5.2: Censorship validator
- Detect disallowed language, violence, and explicit content.
- Map content to rating expectations.
- Flag and rewrite non-compliant content.

### Stage 5.3: Audience suitability validator
- Match tone and thematic intensity to the selected audience.
- Block content that conflicts with family or teen suitability.
- Capture reasons for every flag.

### Stage 5.4: Constraint reporting
- Return structured pass or fail results.
- Include offending lines, scenes, or tokens.
- Produce a clear explanation for every decision.

### Deliverable
- A deterministic validation layer that can explain why each variant passed or failed.

---

## Phase 6: Iterative Repair and Revision Workflow

### Stage 6.1: Repair planner
- Add a repair step for failed outputs.
- Generate minimal edits instead of full regeneration when possible.
- Preserve user intent while fixing constraint violations.

### Stage 6.2: Loop control
- Revalidate every repaired draft.
- Cap repair attempts to prevent infinite loops.
- Escalate unresolved conflicts to the user.

### Stage 6.3: Conflict handling
- Detect impossible combinations early.
- Warn the user when constraints clash.
- Offer the nearest compliant alternative.

### Deliverable
- A revision loop that improves outputs automatically without hiding constraint failures.

---

## Phase 7: Reporting, Comparison, and Export

### Stage 7.1: Variant comparison UI
- Show three variants side by side.
- Display budget, rating, and feasibility scores.
- Let users compare story direction and production cost.

### Stage 7.2: Export outputs
- Support export to markdown or PDF-ready formatting.
- Include a clean report with annotations.
- Keep the export deterministic and readable.

### Stage 7.3: History and reuse
- Save prior generations.
- Let users reopen and regenerate from previous prompts.
- Preserve version history for auditability.

### Deliverable
- A usable production workflow for review, comparison, and export of screenplay drafts.

---

## Phase 8: Security, Compliance, and Operational Hardening

### Stage 8.1: Secret and env protection
- Add `.env.example` and validation rules.
- Block accidental commits of env files, service keys, and tokens.
- Add secret scanning and git ignore protections.

### Stage 8.2: Security automation
- Run dependency audits in CI.
- Add backend and frontend vulnerability checks.
- Fail the pipeline on high-severity findings.

### Stage 8.3: Auth and session hardening
- Enforce secure session handling.
- Limit token exposure in the browser.
- Protect API routes with authenticated access control.

### Stage 8.4: Logging and traceability
- Log request ids and generation ids.
- Avoid logging secrets or raw sensitive content.
- Keep security logs actionable but privacy-safe.

### Deliverable
- A hardened application that resists common operational and supply-chain risks.

---

## Phase 9: CI/CD and Release Engineering

### Stage 9.1: GitHub Actions
- Lint frontend and backend on every pull request.
- Run tests and type checks.
- Run security checks for dependencies and secrets.
- Validate builds before merge.

### Stage 9.2: Commit discipline
- Use conventional commits only.
- Standardize messages such as `feat:`, `fix:`, `chore:`, and `docs:`.
- Keep commits small and reviewable.

### Stage 9.3: Hook strategy
- Add pre-commit formatting and lint hooks.
- Add pre-push checks for tests and vulnerability scanning.
- Block merges on failing gates.

### Stage 9.4: Release flow
- Use staged environments.
- Promote from local to staging to production.
- Require green checks before deployment.

### Deliverable
- A modern delivery pipeline that keeps quality and security checks automatic.

---

## 6. Suggested Repository Structure

```text
scriptgenie/
├── web/
│   ├── app/
│   ├── components/
│   ├── features/
│   ├── lib/
│   └── styles/
├── api/
│   ├── app/
│   ├── routers/
│   ├── services/
│   ├── validators/
│   ├── schemas/
│   └── tests/
├── shared/
│   ├── schemas/
│   └── constants/
├── db/
│   ├── migrations/
│   └── seed/
├── .github/
│   └── workflows/
└── docs/
    ├── architecture/
    ├── security/
    └── releases/
```

---

## 7. Quality Gates

The project should not be considered complete unless the following are true:

- Frontend and backend lint cleanly.
- Automated tests pass.
- Supabase auth works with Google login.
- No secrets are committed.
- Env validation fails fast on missing required values.
- At least three screenplay variants are generated per request.
- Constraint validators run on every generated draft.
- Revisions occur automatically when constraints fail.
- Outputs are stored and retrievable by the signed-in user.
- CI blocks unsafe or broken changes from merging.

---

## 8. Definition of Done

ScriptGenie is done when a user can:

1. Sign in with Google.
2. Submit a screenplay prompt with genre, audience, budget, and rating constraints.
3. Receive at least three structured screenplay variants.
4. Review budget, censorship, and audience validation reports.
5. See automatic repair attempts for failed variants.
6. Save and revisit generated outputs later.
7. Trust that the application is deployed with production-grade quality gates.

---

## 9. Commit and Authorship Rules

For every commit during implementation:

- Use conventional commit format only.
- Keep the author as Samarth D Kolur.
- Use the GitHub identity `samarthkolur`.
- Use the email `samarthdkolur1@gmail.com`.
- Do not attribute commits to any AI assistant or external agent.
- Avoid vague commit messages.
- Prefer one concern per commit.

Recommended examples:

- `feat: add auth shell and protected routes`
- `fix: validate env variables before startup`
- `chore: add github actions for lint and security checks`
- `docs: add production build plan`

---

## 10. Practical Build Order

If implementing in sequence, the most effective order is:

1. Foundation and repo setup
2. Next.js shell and shadcn integration
3. Supabase auth and storage
4. FastAPI contract layer
5. Groq-based generation pipeline
6. Budget and content validators
7. Revision loop and repair planner
8. History, export, and comparison UI
9. CI, hooks, and security hardening
10. Final QA, release preparation, and deployment

---

## 11. Final Outcome Target

By the end of this build, ScriptGenie should function as a polished, secure, production-ready screenplay generation product with:

- A modern Next.js frontend
- A FastAPI orchestration backend
- Groq-based generation
- Supabase auth and persistence
- Google sign-in
- Constraint-aware validations
- Revision and repair logic
- CI/CD and security automation
- Modular code and maintainable architecture

This plan is designed to support a complete end-to-end implementation, not just a prototype.

---

## Phase 12: Comprehensive Testing Strategy

### Stage 12.1: Test pyramid
- Unit tests for prompt builders, validators, parsers, scoring, auth helpers, and utility modules.
- Integration tests for FastAPI routes, Supabase access, Groq orchestration, and persistence flows.
- Frontend component tests for form states, auth states, variant comparison, and error rendering.
- End-to-end tests for sign-in, prompt submission, generation, validation, save, and history retrieval.

### Stage 12.2: Contract and API testing
- Add request and response contract tests for all REST endpoints.
- Validate JSON schemas for generation and validation payloads.
- Verify error responses are stable and machine-readable.

### Stage 12.3: AI regression testing
- Maintain prompt regression fixtures for representative screenplay requests.
- Maintain validator regression fixtures for budget, censorship, and audience cases.
- Use a golden dataset of prompts and expected structural properties.
- Mock Groq responses for deterministic CI execution.

### Stage 12.4: Coverage expectations and gating
- Target at least 80% unit coverage for core orchestration and validation code.
- Require critical-path coverage for auth, generation, validation, and persistence.
- Fail CI on broken tests, schema mismatches, or prompt regression drift.
- Require test reports to be visible in CI artifacts.

### Deliverable
- A repeatable test suite that validates engineering correctness, AI quality, and regression safety before every merge.

---

## Phase 13: Observability & Monitoring

### Stage 13.1: Logging and traceability
- Use structured JSON logs across frontend-facing API requests and backend services.
- Generate request IDs and propagate trace IDs through every generation request.
- Log prompt version, generation ID, variant ID, and validator outcomes.
- Exclude secrets, tokens, and raw auth credentials from logs.

### Stage 13.2: Metrics and dashboards
- Track request latency, Groq latency, validation latency, and database round-trip time.
- Track token usage, prompt length, response length, and retry counts.
- Track validator pass rates, fail rates, and repair-loop iteration counts.
- Recommend dashboards for API health, AI usage, error rate, and cost trends.

### Stage 13.3: Tracing and alerts
- Add distributed tracing across API, validator, and persistence boundaries.
- Monitor error rates, p95 latency, timeout frequency, and rate-limit events.
- Alert on sustained Groq failures, repeated validation crashes, auth errors, and storage failures.

### Deliverable
- A production observability layer that makes latency, cost, reliability, and failures visible to operators.

---

## Phase 14: Prompt Versioning and Management

### Stage 14.1: Prompt repository
- Store prompts in a dedicated prompt repository directory.
- Separate system prompts, generation prompts, repair prompts, and validator prompts.
- Assign stable version IDs to every prompt template.

### Stage 14.2: Versioning model
- Persist the prompt version with every generation request and every saved variant.
- Track template changes as backward-compatible versions.
- Keep migration notes when a prompt changes behavior or schema.

### Stage 14.3: Rollback strategy
- Allow fast rollback to the previous prompt version if regression tests fail.
- Preserve old versions for reproducibility and auditability.
- Support side-by-side comparison of old and new prompt outputs.

### Deliverable
- A controlled prompt management system that supports experimentation without losing reproducibility.

---

## Phase 15: Caching Strategy

### Stage 15.1: Request deduplication
- Compute a prompt hash for each normalized generation request.
- Detect duplicate requests within a configurable time window.
- Reuse prior results when the same prompt version and constraints match exactly.

### Stage 15.2: Cache layers
- Cache completed generation outputs when safe to do so.
- Cache validation outcomes for identical content and validator versions.
- Cache non-sensitive API responses where freshness requirements allow.

### Stage 15.3: Invalidation rules
- Invalidate caches when prompt versions change.
- Invalidate caches when validator logic changes.
- Invalidate caches on policy changes, auth changes, or database record updates.

### Deliverable
- A caching layer that reduces cost and latency while preserving correctness and auditability.

---

## Phase 16: Error Handling & Failure Matrix

### Stage 16.1: Groq and model failures
- Handle timeout, rate limit, malformed output, and partial output cases.
- Retry transient failures with bounded exponential backoff.
- Fall back to a safe degraded message when the model is unavailable.

### Stage 16.2: API and database failures
- Handle Supabase write failures, auth failures, and network interruptions.
- Return clear user-facing messages for retryable versus terminal errors.
- Store failure metadata for operator review.

### Stage 16.3: Output and repair failures
- Detect invalid JSON, hallucinated schema fields, and partial variant failures.
- Retry parsing before regeneration.
- Escalate to a repair prompt or a fresh generation when validation repeatedly fails.

### Stage 16.4: Resilience controls
- Use circuit breakers for repeated Groq or database failures.
- Limit retries to avoid thundering herd behavior.
- Provide user messages that explain what failed and what the user can do next.

### Deliverable
- A clear failure matrix that reduces ambiguity for both users and operators.

---

## Phase 17: Database Design

### Stage 17.1: Entity relationship overview
- User accounts own generations.
- Each generation contains multiple variants.
- Each variant has associated validation records, prompt versions, and audit entries.
- Each saved export references the originating generation and user.

### Stage 17.2: Core tables
- `profiles`
- `generation_requests`
- `screenplay_variants`
- `validation_reports`
- `prompt_versions`
- `generation_events`
- `audit_logs`
- `exports`

### Stage 17.3: Key design rules
- Use primary keys and foreign keys for every relationship.
- Add indexes on user id, request id, prompt version, generation status, and created-at fields.
- Apply Row Level Security to all user-owned records.
- Use soft delete flags for recoverable records and maintain immutable audit rows.

### Stage 17.4: Audit and compliance
- Store write events and state transitions in audit tables.
- Keep validation history attached to each variant.
- Ensure deleted content remains traceable for operational review.

### Deliverable
- A normalized and auditable database model that supports history, access control, and analytics.

---

## Phase 18: API Design

### Stage 18.1: REST surface
- `POST /v1/generate`
- `GET /v1/generations/{id}`
- `GET /v1/generations`
- `GET /v1/generations/{id}/variants`
- `POST /v1/generations/{id}/regenerate`
- `GET /v1/prompts`
- `GET /health`

### Stage 18.2: Request and response contracts
- Define typed schemas for generation input, generation output, validation report, and error payloads.
- Return structured errors with stable error codes.
- Include pagination for list endpoints.

### Stage 18.3: Authentication and versioning
- Require authenticated access for all user data endpoints.
- Use versioned routes and preserve backward compatibility where possible.
- Attach request metadata for tracing and audit.

### Deliverable
- A stable REST API that can be consumed safely by the frontend and tested independently.

---

## Phase 19: Deployment Architecture

### Stage 19.1: Hosting model
- Host the Next.js frontend on a production web platform with CDN support.
- Host the FastAPI backend on a container or managed app platform.
- Use Supabase as the managed auth and database layer.

### Stage 19.2: Environment and secrets
- Separate development, staging, and production environments.
- Keep production secrets in the deployment platform and not in git.
- Document every required environment variable.

### Stage 19.3: Network and resilience
- Serve all traffic over HTTPS.
- Use domain configuration and CDN caching for static assets.
- Support horizontal scaling for the API layer.
- Maintain backup and disaster recovery procedures for database and file assets.

### Deliverable
- A deployment model that is secure, scalable, and recoverable.

---

## Phase 20: Security Hardening

### Stage 20.1: Web application security
- Address OWASP Top 10 risks explicitly.
- Protect against prompt injection, XSS, CSRF, SQL injection, and insecure direct object access.
- Add CSP headers and secure cookie settings.

### Stage 20.2: Identity and token security
- Validate JWTs on every protected request.
- Enforce short-lived sessions and secure refresh flows.
- Support secret rotation and revocation procedures.

### Stage 20.3: Output and dependency safety
- Sanitize model output before rendering.
- Apply dependency scanning and patching rules.
- Add rate limiting to protect both the API and Groq usage.

### Deliverable
- A hardened application baseline that reduces common application, prompt, and supply-chain risks.

---

## Phase 21: AI-Specific Engineering

### Stage 21.1: Structured output handling
- Parse model output into structured objects before rendering.
- Validate JSON with schema checks.
- Reject malformed or incomplete generations before downstream use.

### Stage 21.2: Quality and safety controls
- Use multi-stage prompting for generation, validation, and repair.
- Add fallback prompting when the primary response fails.
- Apply safety filters before displaying content.

### Stage 21.3: Evaluation model
- Track confidence scoring for each variant and validator result.
- Measure prompt adherence, constraint satisfaction, novelty, and repair success rate.
- Keep explainability annotations tied to every AI decision.

### Deliverable
- An AI pipeline that is structured, inspectable, and measurable rather than purely generative.

---

## Phase 22: Performance Engineering

### Stage 22.1: Response time targets
- Target fast initial API acknowledgement for generation jobs.
- Use async processing for long-running generation and validation work.
- Stream partial responses when the UX benefits from early feedback.

### Stage 22.2: Concurrency model
- Run validators in parallel where dependencies allow.
- Offload heavy tasks to background jobs or queues.
- Optimize database access with indexes and bounded queries.

### Stage 22.3: Frontend performance
- Use pagination and lazy loading for history and large result sets.
- Keep rendering paths lightweight for variant comparison and report views.

### Deliverable
- A platform that stays responsive under normal production workload patterns.

---

## Phase 23: Repository Improvements

### Stage 23.1: Expanded directory layout
```text
scriptgenie/
├── web/             # Next.js frontend application
├── api/             # FastAPI backend and orchestration services
├── shared/          # Shared schemas, constants, and contracts
├── db/              # Supabase migrations, seeds, and policy files
├── tests/           # Unit, integration, contract, and E2E tests
├── scripts/         # Automation scripts for setup, migration, and checks
├── docs/            # Architecture, security, API, and operations documentation
├── prompts/         # Versioned prompt templates and prompt registry files
├── infrastructure/  # Deployment and environment infrastructure definitions
├── monitoring/      # Dashboards, alerts, and observability assets
├── docker/          # Container files and local service composition helpers
├── deployment/      # Release, rollout, and rollback documentation
└── examples/        # Sample prompts, payloads, and golden datasets
```

### Stage 23.2: Directory purpose
- `tests/` holds all automated verification layers.
- `scripts/` holds maintenance and admin automation.
- `docs/` holds the technical design, runbooks, and API references.
- `prompts/` holds versioned AI prompt templates and rollback history.
- `infrastructure/` holds environment and provisioning assets.
- `monitoring/` holds dashboard and alert definitions.
- `docker/` holds local and production container definitions.
- `deployment/` holds release process and rollback guidance.
- `examples/` holds payload samples and golden test fixtures.

### Deliverable
- A repository layout that supports engineering scale, operational clarity, and testability.

---

## Phase 24: CI/CD Enhancements

### Stage 24.1: Pipeline structure
- Use multi-stage pipelines for lint, test, security, build, and deploy.
- Run checks on pull requests and on protected branches.
- Require branch protection and required reviews before merge.

### Stage 24.2: Release discipline
- Use semantic versioning for releases.
- Auto-generate changelogs from conventional commits.
- Tag releases and deploy staged builds before production promotion.

### Stage 24.3: Security and dependency workflow
- Run dependency update checks and security scans continuously.
- Fail the pipeline on severe vulnerabilities or secret leaks.
- Support rollback when staging or production validation fails.

### Deliverable
- A CI/CD system that enforces quality, security, and release hygiene automatically.

---

## Phase 25: Operational Readiness

### Stage 25.1: Runbooks and incident response
- Document incident response steps for auth, API, database, and model outages.
- Provide runbooks for repeatable operational tasks.
- Define ownership and escalation paths.

### Stage 25.2: Health and readiness checks
- Add health checks, readiness probes, and liveness probes.
- Verify backups on a schedule and test restoration procedures.
- Document maintenance windows and routine operating procedures.

### Deliverable
- An operational handbook that allows the system to be maintained safely in production.

---

## Phase 26: Production Readiness Checklist

ScriptGenie is production-ready only when all of the following are true:

- Engineering: modular codebase, stable interfaces, documented architecture, and maintainable ownership boundaries.
- Security: auth verified, secrets protected, rate limiting enabled, and dependency risk addressed.
- Testing: unit, integration, contract, component, E2E, prompt regression, validator regression, and golden dataset checks pass.
- AI quality: structured parsing, repair logic, explainability, and regression metrics meet target thresholds.
- Performance: latency, concurrency, and background processing behavior meet expected production usage.
- Documentation: setup, API, prompts, runbooks, and deployment documentation are complete.
- Deployment: staging and production deployment workflows exist, are tested, and support rollback.
- Monitoring: logs, metrics, traces, dashboards, and alerts are configured.
- User acceptance: end-to-end workflows are verified by a real user flow.
- Compliance: content rules, access control, and auditability requirements are enforced.

### Deliverable
- A clear release gate that replaces the earlier definition of done with production-grade readiness criteria.
