import "server-only";

import { apiBaseUrl } from "@/lib/env";
import type { ConstraintBundle, ProjectList, Project } from "@/lib/api-client";

/**
 * A project worth opening, created the first time the dev login is used.
 *
 * Not fixtures and not mock data: this goes through the same `POST /v1/projects`
 * and `PUT /v1/projects/{id}/bundle` the wizard uses, under the test user's own
 * token, and lands in Postgres subject to the same row level security. What it
 * saves is the two minutes of clicking that otherwise stands between signing in
 * and having anything on screen to look at.
 *
 * The bundle is the worked example from Phase 2 — horror with a comedy
 * secondary, aimed at PG-13, shot at micro scale, released in the US and India
 * — chosen because it is documented to produce conflicts at every severity,
 * including HARD ones. A demo project with no conflicts would exercise none of
 * Stage 6.2.
 *
 * Every identifier below is checked against `packages/constraint-kb/data`. A
 * bundle naming a genre the knowledge base does not have is a 422, not a
 * silently empty page.
 */

const DEMO_TITLE = "Worked example — horror-comedy at micro scale";

const DEMO_DESCRIPTION =
  "Seeded by the local sign-in shortcut. Safe to rename or delete; it is an " +
  "ordinary project owned by this account.";

const DEMO_BUNDLE: ConstraintBundle = {
  genre: { primary: "horror", secondary: "comedy" },
  audience: { min_age: 13, max_age: 55 },
  rating: { system: "mpa", classification: "pg_13" },
  budget_tier_id: "micro",
  territories: { ids: ["us", "india"] },
};

async function call<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");

  const response = await fetch(`${apiBaseUrl().replace(/\/$/, "")}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(
      `${init.method ?? "GET"} ${path} answered ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

/**
 * Give the account something to open, unless it already has something.
 *
 * Idempotent by checking for any project at all rather than by title, so a
 * developer who renamed the demo or made their own does not get a fresh copy
 * on every sign-in.
 *
 * Never throws. Seeding is a convenience attached to signing in, and a failure
 * here — the API not running yet is the likely one — must not stop the sign-in
 * that succeeded. The reason is logged where a developer will see it.
 */
export async function ensureDemoProject(token: string): Promise<void> {
  try {
    const existing = await call<ProjectList>(token, "/v1/projects?limit=1");
    if (existing.total > 0) return;

    const project = await call<Project>(token, "/v1/projects", {
      method: "POST",
      body: JSON.stringify({
        title: DEMO_TITLE,
        description: DEMO_DESCRIPTION,
      }),
    });

    await call(token, `/v1/projects/${project.id}/bundle`, {
      method: "PUT",
      body: JSON.stringify({ bundle: DEMO_BUNDLE }),
    });

    console.info(`dev-login: seeded demo project ${project.id}`);
  } catch (cause) {
    console.warn(
      `dev-login: signed in, but the demo project could not be seeded ` +
        `(${String(cause)}). Is the API running on ${apiBaseUrl()}?`,
    );
  }
}
