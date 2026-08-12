"use client";

import { useEffect, useRef, useState } from "react";

import { resolveConflictsAction } from "@/app/app/projects/[projectId]/actions";
import { DETECT_DEBOUNCE_MS } from "@/hooks/use-conflict-report";
import type {
  ConstraintBundle,
  ResolutionChoice,
  ResolveResponse,
} from "@/lib/api-client";
import {
  bundleFormSchema,
  toBundle,
  type BundleFormValues,
} from "@/lib/constraints/schema";

export type EnvelopeState = {
  /** The last envelope the API produced, or `null` if it never has. */
  readonly resolved: ResolveResponse | null;
  readonly pending: boolean;
  /**
   * True when a HARD conflict is stopping the API from producing one.
   *
   * Distinct from an error, and it has to be: the writer is mid-resolution and
   * the panel beside this is already telling them what is outstanding. What
   * this changes is only whether the scope shown is the tier's ceiling or the
   * one generation would actually be held to.
   */
  readonly blocked: boolean;
  readonly error: string | null;
  /** True when the answers or choices have moved on since `resolved`. */
  readonly stale: boolean;
};

type Outcome =
  | { readonly kind: "resolved"; readonly resolved: ResolveResponse }
  | { readonly kind: "blocked" }
  | { readonly kind: "failed"; readonly message: string };

/**
 * The envelope the writer's current answers and resolutions produce.
 *
 * This is what makes the scope preview respond to a resolution rather than
 * only to a budget tier. A clamp lowers a content ceiling, and the number it
 * lowers it to is computed by the parameteriser from the strictest applicable
 * authority — which is not something the browser can work out, and must not
 * guess at, because a preview that disagreed with the envelope generation is
 * held to would be worse than no preview.
 *
 * Same properties as `useConflictReport`: nothing is sent until the form
 * parses, out-of-order responses are dropped, the last good envelope survives
 * while a new one is fetched, and every derived flag is computed from which
 * request the outcome belongs to rather than stored alongside it.
 */
export function useGenerationEnvelope(
  values: BundleFormValues,
  choices: readonly ResolutionChoice[],
): EnvelopeState {
  const parsed = bundleFormSchema.safeParse(values);
  const key: string | null = parsed.success
    ? JSON.stringify({ bundle: toBundle(parsed.data), choices })
    : null;

  /** The last envelope, whichever request produced it. Kept across edits. */
  const [held, setHeld] = useState<{
    readonly key: string;
    readonly resolved: ResolveResponse;
  } | null>(null);
  /** What became of the most recent request, and which one it was. */
  const [outcome, setOutcome] = useState<{
    readonly key: string;
    readonly outcome: Outcome;
  } | null>(null);
  const sequence = useRef(0);

  useEffect(() => {
    if (key === null || outcome?.key === key) return;

    const current = ++sequence.current;
    const timer = setTimeout(() => {
      const request = JSON.parse(key) as {
        bundle: ConstraintBundle;
        choices: ResolutionChoice[];
      };
      void resolveConflictsAction(request.bundle, request.choices).then(
        (result) => {
          if (current !== sequence.current) return;
          if (result.ok) {
            setHeld({ key, resolved: result.data });
            setOutcome({
              key,
              outcome: { kind: "resolved", resolved: result.data },
            });
          } else if (result.blocked === true) {
            setOutcome({ key, outcome: { kind: "blocked" } });
          } else {
            setOutcome({
              key,
              outcome: { kind: "failed", message: result.error },
            });
          }
        },
      );
    }, DETECT_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [key, outcome?.key]);

  const current =
    outcome !== null && outcome.key === key ? outcome.outcome : null;

  return {
    resolved: held?.resolved ?? null,
    pending: key !== null && current === null,
    blocked: current?.kind === "blocked",
    error: current?.kind === "failed" ? current.message : null,
    stale: held === null || held.key !== key,
  };
}
