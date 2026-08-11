"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Variant } from "@/lib/api-client";
import {
  VERDICT_COPY,
  isVerified,
  overallVerdict,
  parameterLabel,
  type Verdict,
} from "@/lib/constraints/verification";
import { cn } from "@/lib/utils";

const VERDICT_ICON: Readonly<Record<Verdict, typeof CheckCircle2Icon>> = {
  PASS: CheckCircle2Icon,
  FLAGGED: AlertTriangleIcon,
  NEEDS_REVIEW: HelpCircleIcon,
};

type Props = {
  readonly variant: Variant;
  readonly archetypeLabel: string;
};

/**
 * One generated variant: what it is, what it holds to, and what checked it.
 *
 * The satisfaction report and the verdict badges are two different questions
 * answered together. `satisfaction` is arithmetic — did the structural
 * counts and content ceilings hold — and is decisive. The verdicts add the
 * keyword pass on top, which can only ever raise `NEEDS_REVIEW`; it never
 * turns a satisfied report into an unverified one, and never turns a failed
 * one into a passing one. `surfaceable` already encodes both, so the summary
 * badge reads that rather than recomputing it.
 */
export function VariantCard({ variant, archetypeLabel }: Props) {
  const verdict = overallVerdict(variant.verdicts);
  const Icon = VERDICT_ICON[verdict];
  const verified = isVerified(variant.verdicts);

  return (
    <Card
      className={cn(
        !verified && "border-amber-500/40",
        verdict === "FLAGGED" && "border-destructive/40",
      )}
    >
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <Badge variant="outline">{archetypeLabel}</Badge>
            <CardTitle className="text-base">{variant.title}</CardTitle>
          </div>
          <Badge variant="outline" className={VERDICT_COPY[verdict].badgeClass}>
            <Icon className="size-3" aria-hidden="true" />
            {VERDICT_COPY[verdict].label}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{variant.logline}</p>
      </CardHeader>

      <CardContent className="space-y-4">
        <ol className="space-y-2 text-sm">
          {variant.beats.map((beat) => (
            <li key={beat.index} className="flex gap-2">
              <span
                aria-hidden="true"
                className="text-xs font-medium text-muted-foreground"
              >
                {beat.index + 1}.
              </span>
              <span>
                <span className="font-medium">{beat.function}</span> —{" "}
                {beat.summary}
              </span>
            </li>
          ))}
        </ol>

        <SatisfactionReport variant={variant} />

        {variant.relaxations.length > 0 && (
          <div className="space-y-1 border-t pt-3">
            <h4 className="text-xs font-medium">Genre conventions set aside</h4>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {variant.relaxations.map((relaxation) => (
                <li key={relaxation}>{relaxation}</li>
              ))}
            </ul>
          </div>
        )}

        {/*
         * These name what the variant actually uses; the satisfaction report
         * above counts the same two things against their limits. The labels
         * are deliberately not "Locations" and "Named characters" — those are
         * the scope parameters' own names, and repeating them here would put
         * two identically labelled terms in one card meaning different things.
         */}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
          <dt>Locations used</dt>
          <dd className="text-right">
            {variant.locations.length === 0
              ? "None named"
              : variant.locations.join(", ")}
          </dd>
          <dt>Characters named</dt>
          <dd className="text-right">
            {variant.named_characters.length === 0
              ? "None named"
              : variant.named_characters.join(", ")}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

function SatisfactionReport({ variant }: { readonly variant: Variant }) {
  const { satisfaction } = variant;
  const rows = [
    ...satisfaction.dimension_checks.map((check) => ({
      key: `dimension:${check.dimension}`,
      label: parameterLabel(check.dimension),
      observed: check.observed,
      permitted: check.permitted,
      satisfied: check.satisfied,
    })),
    ...satisfaction.scope_checks.map((check) => ({
      key: `scope:${check.parameter}`,
      label: parameterLabel(check.parameter),
      observed: check.observed,
      permitted: check.limit,
      satisfied: check.satisfied,
    })),
  ];

  return (
    <div className="space-y-2 border-t pt-3">
      <h4 className="text-xs font-medium">Constraint satisfaction</h4>
      <dl className="space-y-1 text-xs">
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
      {satisfaction.violations.length > 0 && (
        <p className="text-xs text-destructive">
          Exceeds: {satisfaction.violations.map(parameterLabel).join(", ")}
        </p>
      )}
    </div>
  );
}
