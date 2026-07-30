"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { KbOptions } from "@/lib/api-client";
import { describeScope } from "@/lib/constraints/scope-preview";
import { describeDeltas, thresholdRows } from "@/lib/constraints/thresholds";
import type { EnvelopeState } from "@/hooks/use-generation-envelope";

type Props = {
  readonly options: KbOptions;
  readonly budgetTierId: string;
  readonly envelope: EnvelopeState;
};

/**
 * What the generator will actually be allowed to do.
 *
 * Two sources, and the difference between them is the whole point of the
 * panel. Before any conflict is settled the only scope in hand is the budget
 * tier's, which is a ceiling on production. Once the API can resolve the
 * bundle it returns a `GenerationEnvelope`, which is that ceiling intersected
 * with everything else that binds — the certificate, the territories, and the
 * resolutions the writer just chose. Selecting a resolution moves the second
 * one, which is what makes this preview answer the question "what did that
 * choice cost me?" rather than merely restating the tier.
 *
 * The heading says which of the two is on screen. A preview that silently fell
 * back to the tier's scope while a HARD conflict was outstanding would show
 * the writer bounds looser than any they could generate under.
 */
export function ScopePanel({ options, budgetTierId, envelope }: Props) {
  const tier = options.budget_tiers.find((item) => item.id === budgetTierId);
  const resolved = envelope.resolved;
  const live = resolved !== null && !envelope.stale;

  const phrases =
    resolved === null
      ? tier === undefined
        ? []
        : describeScope(tier.scope as Record<string, unknown>)
      : describeScope(resolved.envelope.scope);

  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">
            {resolved === null ? "Scope at this tier" : "Scope for generation"}
          </CardTitle>
          {envelope.pending ? (
            <span className="text-xs text-muted-foreground">Recomputing…</span>
          ) : (
            !live &&
            resolved !== null && <Badge variant="outline">Out of date</Badge>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          {resolved === null
            ? envelope.blocked
              ? "The budget tier's ceiling. The bounds generation is held to cannot be computed until the blocking conflicts are settled."
              : "The budget tier's ceiling, before anything else narrows it."
            : "The tier, the certificate, the territories and your resolutions, intersected."}
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        <ul className="space-y-1 text-sm">
          {phrases.map((phrase) => (
            <li key={phrase} className="flex gap-2">
              <span aria-hidden="true" className="text-muted-foreground">
                ·
              </span>
              <span>{phrase}</span>
            </li>
          ))}
        </ul>

        {resolved !== null && (
          <div className="space-y-2 border-t pt-3">
            <h3 className="text-xs font-medium">Content ceilings</h3>
            <dl className="space-y-1 text-xs">
              {thresholdRows(resolved.envelope).map((row) => (
                <div
                  key={row.dimension}
                  className="flex flex-wrap justify-between gap-x-3"
                >
                  <dt className="text-muted-foreground">{row.label}</dt>
                  <dd className="text-right">
                    {row.word}
                    {row.authority !== null && (
                      <span className="block text-muted-foreground">
                        set by {row.authority}
                      </span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {resolved !== null && resolved.deltas.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            <h3 className="text-xs font-medium">What your choices changed</h3>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {describeDeltas(resolved.deltas).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        )}

        {envelope.error !== null && (
          <p role="alert" className="text-xs text-destructive">
            {envelope.error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
