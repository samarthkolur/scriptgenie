"use server";

import { revalidatePath } from "next/cache";

import {
  detectConflicts as detectConflictsRequest,
  saveBundleDraft,
  type ConflictReport,
  type ConstraintBundle,
} from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";

/**
 * The wizard's server-side half.
 *
 * The typed client is `server-only` because it reaches the caller's access
 * token, so a Client Component cannot call it — importing it there is a build
 * error rather than a token in the browser bundle. Server Actions are the
 * bridge: the form runs in the browser, these run on the server with the
 * session, and nothing about the credential crosses over.
 *
 * Both return a discriminated result rather than throwing. An action that
 * throws surfaces in the browser as a digest and an error boundary, which is
 * the right treatment for a bug and the wrong one for "that bundle has a
 * conflict" — the caller needs to render the problem next to the field that
 * caused it, and for that it needs the message rather than a hash of it.
 */

export type ActionResult<T> =
  | { readonly ok: true; readonly data: T }
  | { readonly ok: false; readonly error: string };

function failure(
  error: unknown,
  fallback: string,
): { ok: false; error: string } {
  if (error instanceof ApiError) {
    return { ok: false, error: error.problem.detail };
  }
  // Anything else is a bug or an outage, and its message may name internals.
  return { ok: false, error: fallback };
}

/** Persist the wizard's answers. Returns when the write is durable. */
export async function saveDraftAction(
  projectId: string,
  bundle: ConstraintBundle,
): Promise<ActionResult<{ updatedAt: string; cited: boolean }>> {
  try {
    const draft = await saveBundleDraft(projectId, bundle);
    // The workspace reads the draft on the server, so the cached render has to
    // be discarded or a reload would show the previous answers.
    revalidatePath(`/app/projects/${projectId}`);
    return {
      ok: true,
      data: { updatedAt: draft.updated_at, cited: draft.cited },
    };
  } catch (error) {
    return failure(error, "Your answers could not be saved. Try again.");
  }
}

/**
 * Evaluate a bundle without saving or spending anything.
 *
 * Detection is deterministic and involves no model call, which is what makes
 * it safe to run on every edit.
 */
export async function detectConflictsAction(
  bundle: ConstraintBundle,
): Promise<ActionResult<ConflictReport>> {
  try {
    return { ok: true, data: await detectConflictsRequest(bundle) };
  } catch (error) {
    return failure(error, "The constraints could not be checked just now.");
  }
}
