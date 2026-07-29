"use client";

import { useState } from "react";

import { ConstraintWizard } from "@/components/features/constraints/wizard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { KbOptions } from "@/lib/api-client";
import type { BundleFormValues } from "@/lib/constraints/schema";

type Props = {
  readonly projectId: string;
  readonly options: KbOptions;
  readonly initialValues: BundleFormValues;
  readonly hasSavedDraft: boolean;
};

/**
 * The client half of the project page.
 *
 * It owns the constraint answers because more than one panel needs them: the
 * wizard writes them, and the summary — and, from Stage 6.2, the conflict
 * panel — read them. Holding them here rather than in the wizard is what lets
 * those panels update the moment an answer changes, without the wizard having
 * to know they exist.
 */
export function ProjectWorkspace({
  projectId,
  options,
  initialValues,
  hasSavedDraft,
}: Props) {
  const [values, setValues] = useState(initialValues);
  const [saved, setSaved] = useState(hasSavedDraft);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <ConstraintWizard
        projectId={projectId}
        options={options}
        initialValues={initialValues}
        hasSavedDraft={hasSavedDraft}
        onSaved={(next) => {
          setValues(next);
          setSaved(true);
        }}
      />

      <aside className="space-y-4">
        <Summary options={options} values={values} saved={saved} />
      </aside>
    </div>
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
