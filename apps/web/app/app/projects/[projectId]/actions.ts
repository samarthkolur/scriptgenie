"use server";

import { revalidatePath } from "next/cache";

import {
  detectConflicts as detectConflictsRequest,
  generateVariants as generateVariantsRequest,
  resolveConflicts as resolveConflictsRequest,
  saveBundleDraft,
  submitFeedback as submitFeedbackRequest,
  updateVariant as updateVariantRequest,
  type ConflictReport,
  type ConstraintBundle,
  type Feedback,
  type GenerationResponse,
  type ResolutionChoice,
  type ResolveResponse,
  type Variant,
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

/**
 * Apply the writer's resolutions and return the envelope they produce.
 *
 * Also free of model calls: the API re-runs detection, applies the choices and
 * re-runs detection again to prove they took. That last step is why this is
 * worth calling on every selection — the envelope it returns is the one
 * generation would actually be held to, not a client-side guess at it.
 *
 * A 409 is not a failure to report as one. It means a HARD conflict is still
 * unsettled, which the panel already knows and is already showing; treating it
 * as an error would put a red toast over a state the writer is in the middle
 * of resolving. It comes back as `blocked` so the caller can leave the
 * previous envelope on screen and say why it has not moved.
 */
export async function resolveConflictsAction(
  bundle: ConstraintBundle,
  choices: readonly ResolutionChoice[],
): Promise<
  | { readonly ok: true; readonly data: ResolveResponse }
  | { readonly ok: false; readonly blocked: true }
  | { readonly ok: false; readonly blocked?: false; readonly error: string }
> {
  try {
    return { ok: true, data: await resolveConflictsRequest(bundle, choices) };
  } catch (error) {
    if (error instanceof ApiError && error.problem.status === 409) {
      return { ok: false, blocked: true };
    }
    return failure(error, "That resolution could not be applied just now.");
  }
}

/**
 * Run the generation pipeline for a project.
 *
 * Three outcomes beyond success, and none of them is an ordinary error:
 * 409 — a HARD conflict survived (the gate should already have prevented the
 * call, so this only fires on a race with another tab); 429 — the per-user
 * rate limit, with the wait it names; anything else is a real failure. None of
 * the three spends model quota, and distinguishing them is what lets the
 * caller say the right sentence instead of a generic one.
 */
export async function generateVariantsAction(
  projectId: string,
  bundle: ConstraintBundle,
  choices: readonly ResolutionChoice[],
  variantCount: number,
  seed: number,
): Promise<
  | { readonly ok: true; readonly data: GenerationResponse }
  | { readonly ok: false; readonly blocked: true }
  | {
      readonly ok: false;
      readonly blocked?: false;
      readonly rateLimited: true;
      readonly retryAfterSeconds: number;
    }
  | {
      readonly ok: false;
      readonly blocked?: false;
      readonly rateLimited?: false;
      readonly error: string;
    }
> {
  try {
    const data = await generateVariantsRequest(projectId, {
      bundle,
      choices,
      variant_count: variantCount,
      seed,
    });
    return { ok: true, data };
  } catch (error) {
    if (error instanceof ApiError && error.problem.status === 409) {
      return { ok: false, blocked: true };
    }
    if (error instanceof ApiError && error.problem.status === 429) {
      const raw = error.problem.extra.retry_after_seconds;
      return {
        ok: false,
        rateLimited: true,
        retryAfterSeconds: typeof raw === "number" ? raw : 60,
      };
    }
    return failure(error, "Generation could not be started just now.");
  }
}

/**
 * Report a rule as a false positive against the variant it produced.
 *
 * The rule id is the payload; the variant is only the anchor evidence points
 * at, which is why the caller does not need to pick a "correct" variant to
 * attach it to — any variant from the run the flag was raised for reading is
 * fine.
 */
export async function submitFeedbackAction(
  variantId: string,
  falsePositiveRuleId: string,
): Promise<ActionResult<Feedback>> {
  try {
    return {
      ok: true,
      data: await submitFeedbackRequest(variantId, {
        false_positive_rule_id: falsePositiveRuleId,
      }),
    };
  } catch (error) {
    return failure(error, "That report could not be filed just now.");
  }
}

/**
 * Toggle a variant's favourite mark or update its note.
 *
 * `notes: null` clears an existing note; an omitted `notes` leaves it alone —
 * see `updateVariant`'s own note on why the two must stay distinguishable.
 */
export async function updateVariantAction(
  variantId: string,
  changes: { favourite?: boolean; notes?: string | null },
): Promise<ActionResult<Variant>> {
  try {
    return { ok: true, data: await updateVariantRequest(variantId, changes) };
  } catch (error) {
    return failure(error, "That change could not be saved just now.");
  }
}
