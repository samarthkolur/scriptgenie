"use client";

import { useCallback, useRef, useState } from "react";

import {
  generateVariantsAction,
  submitFeedbackAction,
} from "@/app/app/projects/[projectId]/actions";
import type {
  ConstraintBundle,
  GenerationResponse,
  ResolutionChoice,
} from "@/lib/api-client";

export type FailedVariant = GenerationResponse["failures"][number];

export type GenerationState =
  | { readonly kind: "idle" }
  | { readonly kind: "running"; readonly requested: number }
  | { readonly kind: "blocked" }
  | { readonly kind: "rate_limited"; readonly retryAfterSeconds: number }
  | { readonly kind: "failed"; readonly message: string }
  | {
      readonly kind: "done";
      readonly run: GenerationResponse["run"];
      readonly envelope: GenerationResponse["envelope"];
      readonly variants: readonly GenerationResponse["variants"][number][];
      readonly failures: readonly FailedVariant[];
      /** The archetype currently being retried, if any. */
      readonly retrying: string | null;
      /** The most recent retry's own failure, if the retry itself failed. */
      readonly retryError: {
        readonly archetypeId: string;
        readonly message: string;
      } | null;
    };

/**
 * Runs the generation pipeline and holds what it produced.
 *
 * Unlike `useConflictReport` and `useGenerationEnvelope`, this is not a query
 * that re-fires on every edit — generation spends model quota, so it only ever
 * runs when `generate` is called from the trigger, and nothing here debounces
 * or auto-retries it.
 *
 * `retry` is scoped to one failed slot. The API has no way to ask for a
 * specific archetype again — `archetype_selector.select` only ranks by score
 * for the count requested — so a retry asks for one more variant rather than
 * promising the identical archetype back. That is the honest version of
 * "retry this variant": a replacement, not a resurrection.
 */
export function useGenerateVariants(projectId: string) {
  const [state, setState] = useState<GenerationState>({ kind: "idle" });
  const nextSeed = useRef(0);

  const generate = useCallback(
    async (
      bundle: ConstraintBundle,
      choices: readonly ResolutionChoice[],
      variantCount: number,
      flaggedRuleIds: readonly string[] = [],
    ): Promise<{
      readonly variants: readonly GenerationResponse["variants"][number][];
      readonly filed: boolean;
    }> => {
      const seed = nextSeed.current;
      nextSeed.current += 1;
      setState({ kind: "running", requested: variantCount });

      const result = await generateVariantsAction(
        projectId,
        bundle,
        choices,
        variantCount,
        seed,
      );

      if (!result.ok) {
        if (result.blocked) {
          setState({ kind: "blocked" });
        } else if (result.rateLimited) {
          setState({
            kind: "rate_limited",
            retryAfterSeconds: result.retryAfterSeconds,
          });
        } else {
          setState({ kind: "failed", message: result.error });
        }
        return { variants: [], filed: false };
      }

      setState({
        kind: "done",
        run: result.data.run,
        envelope: result.data.envelope,
        variants: result.data.variants,
        failures: result.data.failures,
        retrying: null,
        retryError: null,
      });

      const anchor = result.data.variants[0];
      if (anchor === undefined || flaggedRuleIds.length === 0) {
        return { variants: result.data.variants, filed: false };
      }

      await Promise.all(
        flaggedRuleIds.map((ruleId) => submitFeedbackAction(anchor.id, ruleId)),
      );
      return { variants: result.data.variants, filed: true };
    },
    [projectId],
  );

  const retry = useCallback(
    async (
      bundle: ConstraintBundle,
      choices: readonly ResolutionChoice[],
      failedVariant: FailedVariant,
    ): Promise<readonly GenerationResponse["variants"][number][]> => {
      setState((current) =>
        current.kind === "done"
          ? {
              ...current,
              retrying: failedVariant.archetype_id,
              retryError: null,
            }
          : current,
      );

      const seed = nextSeed.current;
      nextSeed.current += 1;
      const result = await generateVariantsAction(
        projectId,
        bundle,
        choices,
        1,
        seed,
      );

      setState((current) => {
        if (current.kind !== "done") return current;
        if (!result.ok) {
          const message = result.blocked
            ? "These constraints changed and are blocked again — resolve them before retrying."
            : result.rateLimited
              ? `The generation limit was reached; try again in ${String(result.retryAfterSeconds)}s.`
              : result.error;
          return {
            ...current,
            retrying: null,
            retryError: { archetypeId: failedVariant.archetype_id, message },
          };
        }
        const failures = current.failures.filter(
          (item) => item.variant_index !== failedVariant.variant_index,
        );
        return {
          ...current,
          variants: [...current.variants, ...result.data.variants],
          failures: [...failures, ...result.data.failures],
          retrying: null,
          retryError: null,
        };
      });

      // Derived straight from the already-resolved `result` rather than from
      // inside the updater above: React does not guarantee that updater runs
      // synchronously with this call, so a closure variable it assigned could
      // still be unset by the time this function returns.
      return result.ok ? result.data.variants : [];
    },
    [projectId],
  );

  return { state, generate, retry };
}
