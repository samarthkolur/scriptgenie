import "server-only";

import { apiBaseUrl } from "@/lib/env";
import { ApiError, toProblem } from "@/lib/api/problem";
import { accessToken } from "@/lib/supabase/server";

/**
 * Calling the ScriptGenie API from the server, as the signed-in user.
 *
 * `import "server-only"` is the guard that matters. This module reaches the
 * user's access token, and a token that ends up in a Client Component is a
 * token in the JavaScript bundle. The import makes that a build error rather
 * than a code review someone has to remember to do.
 *
 * Every call is `cache: "no-store"`. The responses here are one user's private
 * data, and Next.js's default caching would let one user's projects be served
 * to the next request that matched the same URL.
 */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = await accessToken();
  if (token === null) {
    throw new ApiError({
      type: "https://scriptgenie.app/problems/unauthenticated",
      title: "Authentication required",
      status: 401,
      detail: "You are not signed in.",
      extra: {},
    });
  }

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl().replace(/\/$/, "")}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch (cause) {
    // The API being unreachable is a different problem from the API refusing,
    // and a UI that conflates them tells the user to check their input when
    // they should be told to try again.
    throw new ApiError({
      type: "https://scriptgenie.app/problems/upstream-unavailable",
      title: "Service unavailable",
      status: 503,
      detail: "The ScriptGenie API could not be reached.",
      extra: { cause: String(cause) },
    });
  }

  if (!response.ok) {
    throw new ApiError(await toProblem(response));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
