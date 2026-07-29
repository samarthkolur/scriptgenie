import "server-only";

import type { components } from "@/types/api";
import { apiFetch } from "@/lib/api/server";

/**
 * The typed surface of the ScriptGenie API.
 *
 * Every shape here is drawn from `types/api.ts`, which is generated from
 * `apps/api/openapi.json` by `pnpm codegen` and checked in CI. Nothing in this
 * file declares a response shape of its own — a hand-written interface beside
 * a generated one is two statements of the same contract, and the hand-written
 * one is the one that silently goes stale.
 *
 * Transport lives in `lib/api/server.ts`: it injects the caller's verified
 * access token, refuses to run without one, and turns any failure into an
 * `ApiError` carrying a parsed RFC 9457 problem document. This module is the
 * vocabulary on top of it — one function per question the UI asks.
 *
 * `import "server-only"` because everything below reaches the user's access
 * token through `apiFetch`. Importing it from a Client Component is a build
 * error rather than a token in the JavaScript bundle.
 */

type Schemas = components["schemas"];

export type KbOptions = Schemas["KbOptions"];
export type ConstraintBundle = Schemas["ConstraintBundle"];
export type ConflictReport = Schemas["ConflictReportResponse"];
export type ResolveResponse = Schemas["ResolveResponse"];
export type ResolutionChoice = Schemas["ResolutionChoice"];
export type Project = Schemas["Project"];
export type ProjectList = Schemas["ProjectList"];
export type Variant = Schemas["Variant"];
export type VariantList = Schemas["VariantList"];
export type GenerationResponse = Schemas["GenerationResponse"];
export type ExportBundle = Schemas["ExportBundle"];
export type Profile = Schemas["Profile"];
export type Feedback = Schemas["Feedback"];
export type BundleDraft = Schemas["BundleDraft"];

/** Query parameters as a string map, skipping anything unset. */
function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const rendered = search.toString();
  return rendered === "" ? "" : `?${rendered}`;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

// ------------------------------------------------------------------ account

export function getProfile(): Promise<Profile> {
  return apiFetch<Profile>("/v1/me");
}

// ----------------------------------------------------------- knowledge base

/**
 * Everything the constraint wizard renders, in one request.
 *
 * The API sets `Cache-Control: private, max-age=3600` and an ETag keyed to the
 * knowledge base version, so repeat calls within a session are cheap. It is
 * still `no-store` at the fetch layer — see `lib/api/server.ts` — because the
 * response travels under one user's token and must not be shared between them.
 */
export function getKbOptions(): Promise<KbOptions> {
  return apiFetch<KbOptions>("/v1/kb/options");
}

// ---------------------------------------------------------------- conflicts

export function detectConflicts(
  bundle: ConstraintBundle,
): Promise<ConflictReport> {
  return post<ConflictReport>("/v1/conflicts/detect", { bundle });
}

/**
 * Apply resolutions and get the envelope generation will be held to.
 *
 * Throws an `ApiError` with status 409 while any HARD conflict is unresolved.
 * Its `problem.extra.conflicts` carries the blocking conflicts, so the caller
 * can show exactly what still has to be decided rather than only that
 * something does.
 */
export function resolveConflicts(
  bundle: ConstraintBundle,
  choices: readonly ResolutionChoice[] = [],
): Promise<ResolveResponse> {
  return post<ResolveResponse>("/v1/conflicts/resolve", { bundle, choices });
}

// ----------------------------------------------------------------- projects

export function listProjects(
  options: { limit?: number; offset?: number } = {},
) {
  return apiFetch<ProjectList>(`/v1/projects${query(options)}`);
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/v1/projects/${encodeURIComponent(projectId)}`);
}

export function createProject(input: {
  title: string;
  description?: string | null;
}): Promise<Project> {
  return post<Project>("/v1/projects", input);
}

export function updateProject(
  projectId: string,
  changes: { title?: string; description?: string | null; status?: string },
): Promise<Project> {
  return apiFetch<Project>(`/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function deleteProject(projectId: string): Promise<void> {
  return apiFetch<void>(`/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}

// ------------------------------------------------------------ bundle draft

/**
 * Save the wizard's answers so a refresh does not lose them.
 *
 * Idempotent, and it overwrites the working draft rather than appending —
 * see the route's own note on why a bundle a conflict report already cites is
 * left alone instead.
 */
export function saveBundleDraft(
  projectId: string,
  bundle: ConstraintBundle,
): Promise<BundleDraft> {
  return apiFetch<BundleDraft>(
    `/v1/projects/${encodeURIComponent(projectId)}/bundle`,
    { method: "PUT", body: JSON.stringify({ bundle }) },
  );
}

/**
 * The saved draft.
 *
 * Throws an `ApiError` with status 404 when the wizard has never been
 * completed for this project, which is the ordinary first-visit case and not
 * an error the caller should surface as one.
 */
export function getBundleDraft(projectId: string): Promise<BundleDraft> {
  return apiFetch<BundleDraft>(
    `/v1/projects/${encodeURIComponent(projectId)}/bundle`,
  );
}

// --------------------------------------------------------------- generation

/**
 * Run the pipeline for a project.
 *
 * Two failures the caller must distinguish, both `ApiError`:
 * 409 — a HARD conflict is unresolved, with the conflicts attached;
 * 429 — the per-user rate limit, with `retry_after_seconds`.
 * Neither spends model quota.
 */
export function generateVariants(
  projectId: string,
  input: {
    bundle: ConstraintBundle;
    choices?: readonly ResolutionChoice[];
    variant_count?: number;
    seed?: number;
  },
): Promise<GenerationResponse> {
  return post<GenerationResponse>(
    `/v1/projects/${encodeURIComponent(projectId)}/generate`,
    input,
  );
}

export function listVariants(
  projectId: string,
  options: { limit?: number; offset?: number } = {},
): Promise<VariantList> {
  return apiFetch<VariantList>(
    `/v1/projects/${encodeURIComponent(projectId)}/variants${query(options)}`,
  );
}

export function exportProject(projectId: string): Promise<ExportBundle> {
  return apiFetch<ExportBundle>(
    `/v1/projects/${encodeURIComponent(projectId)}/export`,
  );
}

// ------------------------------------------------------------------ feedback

export function submitFeedback(
  variantId: string,
  input: {
    rating?: number;
    notes?: string;
    false_positive_rule_id?: string;
  },
): Promise<Feedback> {
  return post<Feedback>(
    `/v1/variants/${encodeURIComponent(variantId)}/feedback`,
    input,
  );
}
