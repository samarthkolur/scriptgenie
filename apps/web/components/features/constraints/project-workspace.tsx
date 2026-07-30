"use client";

import { useCallback, useMemo, useState } from "react";

import { ConflictPanel } from "@/components/features/constraints/conflict-panel";
import { ScopePanel } from "@/components/features/constraints/scope-panel";
import { ConstraintWizard } from "@/components/features/constraints/wizard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useConflictReport } from "@/hooks/use-conflict-report";
import { useGenerationEnvelope } from "@/hooks/use-generation-envelope";
import type { KbOptions, ResolutionChoice } from "@/lib/api-client";
import type { BundleFormValues } from "@/lib/constraints/schema";
import { generationGate } from "@/lib/constraints/severity";

type Props = {
  readonly projectId: string;
  readonly options: KbOptions;
  readonly initialValues: BundleFormValues;
  readonly hasSavedDraft: boolean;
};

/**
 * The client half of the project page.
 *
 * It owns the constraint answers because four things need them: the wizard
 * writes them, and the summary, the conflict panel and the scope preview all
 * read them. Holding them here rather than in the wizard is what lets those
 * panels update the moment an answer changes, without the wizard having to
 * know they exist.
 *
 * It also owns the three pieces of state the generation gate is computed from
 * — the resolutions chosen, the soft conflicts acknowledged, and nothing else.
 * Keeping the gate here rather than inside the panel is deliberate: the button
 * it governs lives outside the panel, and a gate computed in two places is a
 * gate that will eventually disagree with itself.
 */
export function ProjectWorkspace({
  projectId,
  options,
  initialValues,
  hasSavedDraft,
}: Props) {
  const [values, setValues] = useState(initialValues);
  const [savedKey, setSavedKey] = useState<string | null>(
    hasSavedDraft ? JSON.stringify(initialValues) : null,
  );

  const [choices, setChoices] = useState<readonly ResolutionChoice[]>([]);
  const [acknowledged, setAcknowledged] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [flagged, setFlagged] = useState<ReadonlySet<string>>(new Set());

  const conflicts = useConflictReport(values);
  const envelope = useGenerationEnvelope(values, choices);

  const gate = useMemo(
    () =>
      generationGate(conflicts.report?.conflicts ?? [], choices, acknowledged),
    [conflicts.report, choices, acknowledged],
  );

  const choose = useCallback((ruleId: string, resolutionId: string) => {
    setChoices((current) => [
      ...current.filter((choice) => choice.rule_id !== ruleId),
      { rule_id: ruleId, resolution_id: resolutionId },
    ]);
  }, []);

  const acknowledge = useCallback((ruleId: string, next: boolean) => {
    setAcknowledged((current) => {
      const updated = new Set(current);
      if (next) updated.add(ruleId);
      else updated.delete(ruleId);
      return updated;
    });
  }, []);

  const flag = useCallback((ruleId: string) => {
    setFlagged((current) => new Set([...current, ruleId]));
  }, []);

  /*
   * A resolution names a rule from one report, and the API rejects a choice
   * whose rule is not in the report it is judging. Once the answers change,
   * yesterday's choices may name rules that no longer fire — so they are
   * dropped rather than sent, which is also the honest reading: a decision
   * about a conflict that no longer exists has not been made about anything.
   */
  const onValuesChange = useCallback((next: BundleFormValues) => {
    setValues(next);
    setChoices([]);
    setAcknowledged(new Set());
  }, []);

  const saved = savedKey === JSON.stringify(values);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="space-y-6">
        <ConstraintWizard
          projectId={projectId}
          options={options}
          initialValues={initialValues}
          hasSavedDraft={hasSavedDraft}
          onSaved={(next) => setSavedKey(JSON.stringify(next))}
          onValuesChange={onValuesChange}
        />

        <ConflictPanel
          state={conflicts}
          choices={choices}
          onChoose={choose}
          acknowledged={acknowledged}
          onAcknowledge={acknowledge}
          flagged={flagged}
          onFlag={flag}
        />
      </div>

      <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <Summary options={options} values={values} saved={saved} />
        <ScopePanel
          options={options}
          budgetTierId={values.budgetTierId}
          envelope={envelope}
        />
        <GenerateGate gate={gate} checking={conflicts.stale} />
      </aside>
    </div>
  );
}

/**
 * The Generate button and, whenever it is disabled, the reason in a sentence.
 *
 * The reason is tied to the button by `aria-describedby` rather than merely
 * printed near it, so the explanation is read out with the control instead of
 * being something a screen-reader user has to go looking for after being told
 * it is unavailable.
 *
 * `onGenerate` is absent until Stage 6.3 and the button stays disabled without
 * it. That is not a stub: a live button with nothing behind it is a worse lie
 * than a disabled one, and the state that actually matters here — the gate —
 * is computed, explained and tested in full. Passing a handler is the only
 * change 6.3 makes to this component.
 */
export function GenerateGate({
  gate,
  checking,
  onGenerate,
}: {
  readonly gate: ReturnType<typeof generationGate>;
  readonly checking: boolean;
  readonly onGenerate?: (() => void) | undefined;
}) {
  const reason = !gate.allowed
    ? gate.reason
    : checking
      ? "Waiting on the constraint check for these answers."
      : onGenerate === undefined
        ? "These constraints are ready. Generation itself arrives at the next stage."
        : null;

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <Button
          type="button"
          className="w-full"
          disabled={reason !== null}
          {...(onGenerate === undefined ? {} : { onClick: onGenerate })}
          {...(reason === null ? {} : { "aria-describedby": "generate-gate" })}
        >
          Generate variants
        </Button>

        {reason !== null && (
          <p id="generate-gate" className="text-xs text-muted-foreground">
            {reason}
          </p>
        )}

        <p className="text-xs text-muted-foreground">
          Checking constraints costs nothing — detection and resolution are
          deterministic and never call a model.
        </p>
      </CardContent>
    </Card>
  );
}

function labelFor(
  id: string,
  from: readonly { readonly id: string; readonly label: string }[],
): string {
  return from.find((item) => item.id === id)?.label ?? id;
}

function Summary({
  options,
  values,
  saved,
}: {
  readonly options: KbOptions;
  readonly values: BundleFormValues;
  readonly saved: boolean;
}) {
  const system = options.rating_systems.find(
    (item) => item.id === values.ratingSystem,
  );

  const rows: readonly { readonly label: string; readonly value: string }[] = [
    {
      label: "Genre",
      value:
        values.genreSecondary === ""
          ? labelFor(values.genrePrimary, options.genres)
          : `${labelFor(values.genrePrimary, options.genres)} · ${labelFor(values.genreSecondary, options.genres)}`,
    },
    {
      label: "Audience",
      value: `${values.audienceMinAge}–${values.audienceMaxAge}`,
    },
    {
      label: "Certificate",
      value:
        system === undefined
          ? values.ratingClassification
          : `${labelFor(values.ratingClassification, system.classifications)} (${system.label})`,
    },
    {
      label: "Scale",
      value: labelFor(values.budgetTierId, options.budget_tiers),
    },
    {
      label: "Territories",
      value:
        values.territoryIds
          .map((id) => labelFor(id, options.territories))
          .join(", ") || "None chosen",
    },
  ];

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-medium">Current constraints</h2>
          <Badge variant={saved ? "secondary" : "outline"}>
            {saved ? "Saved" : "Unsaved"}
          </Badge>
        </div>

        <dl className="space-y-2 text-sm">
          {rows.map((row) => (
            <div key={row.label} className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className="text-right">{row.value}</dd>
            </div>
          ))}
        </dl>

        <p className="border-t pt-3 text-xs text-muted-foreground">
          Knowledge base {options.kb_version}. These bounds come from that
          version, and a later one may judge the same answers differently.
        </p>
      </CardContent>
    </Card>
  );
}
