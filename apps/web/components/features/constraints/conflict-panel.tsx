"use client";

import { AlertTriangleIcon, FlagIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConflictReport, ResolutionChoice } from "@/lib/api-client";
import {
  SEVERITY_COPY,
  SEVERITY_ORDER,
  bySeverity,
  choiceMap,
  settlesConflict,
  summarise,
} from "@/lib/constraints/severity";
import { cn } from "@/lib/utils";

type Conflict = ConflictReport["conflicts"][number];
type Severity = Conflict["severity"];

/**
 * Severity's visual treatment, kept beside nothing else.
 *
 * Colour is the last thing added and the first thing that must not be load
 * bearing. Every card states its severity in words in the badge, and the badge
 * additionally carries a full sentence for screen readers, so these classes
 * only ever make visible a distinction that is already in the text.
 */
const SEVERITY_STYLES: Readonly<Record<Severity, string>> = {
  HARD: "border-destructive/50 bg-destructive/5",
  SOFT: "border-amber-500/50 bg-amber-500/5",
  ADVISORY: "border-border bg-muted/30",
};

const SEVERITY_BADGE: Readonly<Record<Severity, string>> = {
  HARD: "border-transparent bg-destructive text-white",
  SOFT: "border-amber-500/60 bg-amber-500/15 text-amber-900 dark:text-amber-200",
  ADVISORY: "",
};

type Props = {
  readonly state: {
    readonly report: ConflictReport | null;
    readonly judgedAt: Date | null;
    readonly pending: boolean;
    readonly error: string | null;
    readonly stale: boolean;
  };
  readonly choices: readonly ResolutionChoice[];
  readonly onChoose: (ruleId: string, resolutionId: string) => void;
  readonly acknowledged: ReadonlySet<string>;
  readonly onAcknowledge: (ruleId: string, next: boolean) => void;
  readonly flagged: ReadonlySet<string>;
  readonly onFlag: (ruleId: string) => void;
};

/**
 * What the constraint engine makes of the answers so far.
 *
 * Grouped by severity rather than listed flat, because the three groups ask
 * for three different things from the writer and a single list would make
 * "you cannot generate" and "you might like to know" look like peers. The
 * groups are rendered in `SEVERITY_ORDER` — what blocks first.
 *
 * Advisory dismissal is held here and nowhere else. It is a preference about
 * what the writer wants to keep reading, it must not be able to change what
 * the system permits, and so it is deliberately kept out of the state the gate
 * is computed from. Dismissal is also not persisted: the next report is a
 * fresh judgement, and an advisory the writer put away three edits ago may be
 * about a constraint they have since changed.
 */
export function ConflictPanel({
  state,
  choices,
  onChoose,
  acknowledged,
  onAcknowledge,
  flagged,
  onFlag,
}: Props) {
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const { report, judgedAt, pending, error, stale } = state;

  const conflicts = report?.conflicts ?? [];
  const chosen = choiceMap(choices);

  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Constraint check</CardTitle>
          {pending && (
            <span className="text-xs text-muted-foreground">Rechecking…</span>
          )}
        </div>

        {/*
         * Polite rather than assertive: the verdict changes as the writer
         * types, and an assertive region would interrupt them mid-field to
         * read out a report about the answer they are still giving.
         */}
        <p aria-live="polite" className="text-sm text-muted-foreground">
          {report === null
            ? "Waiting for enough answers to check."
            : stale
              ? "These answers have changed since the last check."
              : summarise(conflicts)}
        </p>
      </CardHeader>

      <CardContent className="space-y-6">
        {error !== null && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        {report === null && error === null && (
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}

        {report !== null && conflicts.length === 0 && (
          <p className="text-sm">
            Nothing in these constraints pulls against anything else. That is
            not a promise the film is easy to make — only that the engine found
            no rule these answers break.
          </p>
        )}

        {SEVERITY_ORDER.map((severity) => {
          const group = bySeverity(conflicts, severity).filter(
            (conflict) =>
              severity !== "ADVISORY" || !dismissed.has(conflict.rule_id),
          );
          if (group.length === 0) return null;

          return (
            <section key={severity} className="space-y-3">
              <div className="space-y-1">
                <h3 className="text-sm font-medium">
                  {SEVERITY_COPY[severity].heading}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {SEVERITY_COPY[severity].meaning}
                </p>
              </div>

              {group.map((conflict) => (
                <ConflictCard
                  key={conflict.rule_id}
                  conflict={conflict}
                  chosenResolution={chosen.get(conflict.rule_id)}
                  onChoose={onChoose}
                  acknowledged={acknowledged.has(conflict.rule_id)}
                  onAcknowledge={onAcknowledge}
                  flagged={flagged.has(conflict.rule_id)}
                  onFlag={onFlag}
                  onDismiss={
                    severity === "ADVISORY"
                      ? () =>
                          setDismissed(
                            (current) =>
                              new Set([...current, conflict.rule_id]),
                          )
                      : undefined
                  }
                />
              ))}
            </section>
          );
        })}

        {report !== null && (
          <p className="border-t pt-3 text-xs text-muted-foreground">
            Judged by knowledge base {report.kb_version} against{" "}
            {report.rules_evaluated}{" "}
            {report.rules_evaluated === 1 ? "rule" : "rules"}
            {judgedAt === null
              ? "."
              : ` at ${judgedAt.toLocaleTimeString()}.`}{" "}
            A later version may reach a different verdict on the same answers.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function ConflictCard({
  conflict,
  chosenResolution,
  onChoose,
  acknowledged,
  onAcknowledge,
  flagged,
  onFlag,
  onDismiss,
}: {
  readonly conflict: Conflict;
  readonly chosenResolution: string | undefined;
  readonly onChoose: (ruleId: string, resolutionId: string) => void;
  readonly acknowledged: boolean;
  readonly onAcknowledge: (ruleId: string, next: boolean) => void;
  readonly flagged: boolean;
  readonly onFlag: (ruleId: string) => void;
  readonly onDismiss?: (() => void) | undefined;
}) {
  const severity = conflict.severity;
  const copy = SEVERITY_COPY[severity];
  const titleId = `${conflict.rule_id}-title`;

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        "space-y-3 rounded-lg border p-4",
        SEVERITY_STYLES[severity],
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 id={titleId} className="text-sm font-medium">
          {conflict.title}
        </h4>
        <div className="flex items-center gap-1">
          <Badge variant="outline" className={SEVERITY_BADGE[severity]}>
            {severity === "HARD" && (
              <AlertTriangleIcon className="size-3" aria-hidden="true" />
            )}
            {copy.label}
            {/* The colour says this too, and to fewer people. */}
            <span className="sr-only">. {copy.announcement}.</span>
          </Badge>
          {onDismiss !== undefined && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={onDismiss}
              aria-label={`Dismiss “${conflict.title}”`}
            >
              <XIcon className="size-3.5" aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>

      <p className="text-sm">{conflict.explanation}</p>

      <Tension conflict={conflict} />

      {conflict.hard_rationale !== null &&
        conflict.hard_rationale !== undefined &&
        conflict.hard_rationale !== "" && (
          <p className="text-xs text-muted-foreground italic">
            {conflict.hard_rationale}
          </p>
        )}

      {conflict.resolutions.length > 0 && (
        <fieldset className="space-y-2">
          <legend className="text-xs font-medium text-muted-foreground">
            How do you want to settle this?
          </legend>
          <div
            role="radiogroup"
            aria-label={`Resolutions for ${conflict.title}`}
            className="space-y-2"
          >
            {conflict.resolutions.map((option) => {
              const selected = chosenResolution === option.id;
              const settles = settlesConflict(option);
              return (
                <button
                  key={option.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => onChoose(conflict.rule_id, option.id)}
                  className={cn(
                    "w-full rounded-md border bg-background/60 p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                    selected
                      ? "border-foreground/40 bg-background"
                      : "hover:border-foreground/20",
                  )}
                >
                  <span className="block text-sm font-medium">
                    {option.label}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {option.description}
                  </span>
                  {!settles && (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      Choosing this leaves the conflict standing — it says you
                      will go back and change an answer.
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </fieldset>
      )}

      {severity === "SOFT" && (
        <label className="flex items-start gap-3 rounded-md border border-dashed p-3 text-sm">
          <Checkbox
            checked={acknowledged}
            onCheckedChange={(state) =>
              onAcknowledge(conflict.rule_id, state === true)
            }
          />
          <span>
            I have read this and want to continue with it in place.
            <span className="mt-1 block text-xs text-muted-foreground">
              Required before generating. Choosing a resolution above changes
              what the generator is told; this only records that you saw it.
            </span>
          </span>
        </label>
      )}

      <div className="flex justify-end border-t border-dashed pt-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-auto py-1 text-xs text-muted-foreground"
          onClick={() => onFlag(conflict.rule_id)}
          disabled={flagged}
        >
          <FlagIcon className="size-3" aria-hidden="true" />
          {flagged ? "Flagged as wrong" : "This conflict is wrong"}
        </Button>
      </div>

      {flagged && (
        <p className="text-xs text-muted-foreground">
          Noted against rule <code>{conflict.rule_id}</code>. The report is
          filed alongside your next generation, because a rule complaint is only
          useful with the output it produced attached to it.
        </p>
      )}
    </article>
  );
}

/**
 * The two values actually in tension, from the rule's own evidence.
 *
 * The explanation already says this in prose, but prose is what a writer
 * skims. Naming the demanded value beside the permitted one is what turns
 * "your horror content exceeds PG-13" into something they can act on without
 * rereading the sentence.
 */
function Tension({ conflict }: { readonly conflict: Conflict }) {
  const evidence = conflict.evidence ?? {};
  const demanded = evidence.left;
  const permitted = evidence.right;
  if (demanded === undefined || permitted === undefined) return null;

  const dimension = evidence.dimension?.replaceAll("_", " ");
  const territory = evidence.territory;

  return (
    <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
      {dimension !== undefined && (
        <>
          <dt className="text-muted-foreground">Dimension</dt>
          <dd className="capitalize">{dimension}</dd>
        </>
      )}
      <dt className="text-muted-foreground">Your constraints ask for</dt>
      <dd className="font-mono">{demanded}</dd>
      <dt className="text-muted-foreground">What is permitted</dt>
      <dd className="font-mono">{permitted}</dd>
      {territory !== undefined && (
        <>
          <dt className="text-muted-foreground">Territory</dt>
          <dd className="uppercase">{territory}</dd>
        </>
      )}
    </dl>
  );
}
