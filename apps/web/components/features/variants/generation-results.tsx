"use client";

import { RefreshCwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { KbOptions } from "@/lib/api-client";
import { labelFor } from "@/lib/utils";
import type {
  FailedVariant,
  GenerationState,
} from "@/hooks/use-generate-variants";

type Props = {
  readonly state: GenerationState;
  readonly options: KbOptions;
  readonly onRetry: (failedVariant: FailedVariant) => void;
};

/**
 * What a generation run is doing, from the moment it is asked for.
 *
 * Renders nothing in `idle` — there is no card to show and no space it should
 * claim before the writer has asked for anything. Every other state occupies
 * the same slot below the constraint check, so the writer never loses their
 * place in the page to find out what happened.
 *
 * A successful run's own variant cards are deliberately not rendered here.
 * They are already persisted the moment generation succeeds, and `VariantLibrary`
 * — seeded from the same list on page load — is the single place they render,
 * with favouriting, notes and comparison built in; a second grid here would be
 * the same cards shown twice with no way to act on either copy consistently.
 * What stays here is genuinely specific to *this run*: how many it produced,
 * which slots failed and why, and the retry action for a failed slot.
 */
export function GenerationResults({ state, options, onRetry }: Props) {
  if (state.kind === "idle") return null;

  if (state.kind === "running") {
    return (
      <section aria-busy="true" className="space-y-3">
        <p aria-live="polite" className="text-sm text-muted-foreground">
          Generating {state.requested}{" "}
          {state.requested === 1 ? "variant" : "variants"}…
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: state.requested }, (_, index) => (
            <Card key={index} aria-hidden="true">
              <CardHeader className="space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-5 w-2/3" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    );
  }

  if (state.kind === "blocked") {
    return (
      <p role="alert" className="text-sm text-destructive">
        These constraints changed since the check ran and are blocked again.
        Resolve them before generating.
      </p>
    );
  }

  if (state.kind === "rate_limited") {
    return (
      <p role="alert" className="text-sm text-destructive">
        You have reached the generation limit for now. Try again in{" "}
        {state.retryAfterSeconds}s.
      </p>
    );
  }

  if (state.kind === "failed") {
    return (
      <p role="alert" className="text-sm text-destructive">
        {state.message}
      </p>
    );
  }

  const { variants, failures, retrying, retryError } = state;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">
          {variants.length} {variants.length === 1 ? "variant" : "variants"}{" "}
          generated
        </h3>
        <p className="text-xs text-muted-foreground">
          Knowledge base {state.run.kb_version} · prompt{" "}
          {state.run.prompt_version} · model {state.run.model}
        </p>
      </div>

      {variants.length === 0 && failures.length === 0 && (
        <p className="text-sm text-muted-foreground">
          This run produced nothing surfaceable. Try again, or loosen a
          resolution and re-check the constraints.
        </p>
      )}

      {failures.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground">
            Could not be generated
          </h4>
          {failures.map((failure) => (
            <Card key={failure.variant_index} className="border-dashed">
              <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
                <div className="space-y-1">
                  <p className="text-sm font-medium">
                    {labelFor(failure.archetype_id, options.archetypes)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {failure.reason}
                  </p>
                  {retryError !== null &&
                    retryError.archetypeId === failure.archetype_id && (
                      <p role="alert" className="text-xs text-destructive">
                        {retryError.message}
                      </p>
                    )}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={retrying !== null}
                  onClick={() => onRetry(failure)}
                >
                  <RefreshCwIcon
                    className={
                      retrying === failure.archetype_id
                        ? "size-3.5 animate-spin"
                        : "size-3.5"
                    }
                    aria-hidden="true"
                  />
                  {retrying === failure.archetype_id
                    ? "Generating…"
                    : "Generate a replacement"}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
