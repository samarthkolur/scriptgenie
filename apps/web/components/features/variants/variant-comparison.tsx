"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { KbOptions, Variant } from "@/lib/api-client";
import {
  VERDICT_COPY,
  overallVerdict,
  parameterLabel,
  type Verdict,
} from "@/lib/constraints/verification";
import { cn, labelFor } from "@/lib/utils";

const VERDICT_ICON: Readonly<Record<Verdict, typeof CheckCircle2Icon>> = {
  PASS: CheckCircle2Icon,
  FLAGGED: AlertTriangleIcon,
  NEEDS_REVIEW: HelpCircleIcon,
};

type Props = {
  readonly variants: readonly Variant[];
  readonly options: KbOptions;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
};

/**
 * Two to five variants, side by side, on whatever they hold in common.
 *
 * `grid-cols-1` is the base and every wider column count is a `sm:`/`lg:`
 * prefix on top of it, so a narrow viewport always renders one card per row —
 * the comparison never needs the page itself to scroll sideways to be read,
 * which is the acceptance criterion this component exists to satisfy. Nothing
 * here needs `overflow-x`; stacking is the answer, not scrolling.
 */
export function VariantComparison({
  variants,
  options,
  open,
  onOpenChange,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Comparing {variants.length} variants</DialogTitle>
          <DialogDescription>
            Structure, cast and location counts, and how each held to the
            envelope it was generated inside.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {variants.map((variant) => (
            <ComparisonCard
              key={variant.id}
              variant={variant}
              archetypeLabel={labelFor(
                variant.archetype_id,
                options.archetypes,
              )}
              minBeats={
                options.archetypes.find(
                  (archetype) => archetype.id === variant.archetype_id,
                )?.min_beats ?? null
              }
            />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ComparisonCard({
  variant,
  archetypeLabel,
  minBeats,
}: {
  readonly variant: Variant;
  readonly archetypeLabel: string;
  readonly minBeats: number | null;
}) {
  const verdict = overallVerdict(variant.verdicts);
  const Icon = VERDICT_ICON[verdict];
  const rows = [
    ...variant.satisfaction.dimension_checks.map((check) => ({
      key: `dimension:${check.dimension}`,
      label: parameterLabel(check.dimension),
      observed: check.observed,
      permitted: check.permitted,
      satisfied: check.satisfied,
    })),
    ...variant.satisfaction.scope_checks.map((check) => ({
      key: `scope:${check.parameter}`,
      label: parameterLabel(check.parameter),
      observed: check.observed,
      permitted: check.limit,
      satisfied: check.satisfied,
    })),
  ];

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="space-y-1">
        <Badge variant="outline">{archetypeLabel}</Badge>
        <p className="font-heading text-sm font-medium">{variant.title}</p>
      </div>

      <Badge variant="outline" className={VERDICT_COPY[verdict].badgeClass}>
        <Icon className="size-3" aria-hidden="true" />
        {VERDICT_COPY[verdict].label}
      </Badge>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <dt>Structure</dt>
        <dd className="text-right">
          {variant.beats.length}
          {minBeats !== null && ` beats (min ${minBeats})`}
          {minBeats === null && " beats"}
        </dd>
        <dt>Locations</dt>
        <dd className="text-right">{variant.locations.length}</dd>
        <dt>Named characters</dt>
        <dd className="text-right">{variant.named_characters.length}</dd>
      </dl>

      {rows.length > 0 && (
        <dl className="space-y-1 border-t pt-3 text-xs">
          {rows.map((row) => (
            <div
              key={row.key}
              className={cn(
                "flex justify-between gap-3",
                !row.satisfied && "text-destructive",
              )}
            >
              <dt>{row.label}</dt>
              <dd className="text-right">
                {row.observed}
                {row.permitted !== null && ` / ${String(row.permitted)}`}
                {!row.satisfied && " — exceeds"}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
