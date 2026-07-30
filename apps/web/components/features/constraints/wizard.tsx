"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckIcon, ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";

import { saveDraftAction } from "@/app/app/projects/[projectId]/actions";
import { FieldRow } from "@/components/features/constraints/field-row";
import { QuickStart } from "@/components/features/constraints/quick-start-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { KbOptions } from "@/lib/api-client";
import { budgetBand, scopePhrases } from "@/lib/constraints/scope-preview";
import {
  bundleFormSchema,
  toBundle,
  type BundleFormValues,
} from "@/lib/constraints/schema";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: "genre", title: "Genre", blurb: "What the film is." },
  { id: "audience", title: "Audience & rating", blurb: "Who can watch it." },
  { id: "budget", title: "Production scale", blurb: "What you can shoot." },
  { id: "territories", title: "Territories", blurb: "Where it releases." },
] as const;

/** Which fields each step owns, so Next validates only what is on screen. */
const STEP_FIELDS: readonly (readonly (keyof BundleFormValues)[])[] = [
  ["genrePrimary", "genreSecondary"],
  ["audienceMinAge", "audienceMaxAge", "ratingSystem", "ratingClassification"],
  ["budgetTierId"],
  ["territoryIds"],
];

type Props = {
  readonly projectId: string;
  readonly options: KbOptions;
  readonly initialValues: BundleFormValues;
  /** Whether the draft came from the server rather than from the defaults. */
  readonly hasSavedDraft: boolean;
  readonly onSaved?: (values: BundleFormValues) => void;
  /**
   * Every edit, not only the saved ones.
   *
   * The conflict panel has to judge what is on screen rather than what was
   * last written down: a writer who changes a certificate and is told nothing
   * until they press Next has been left to discover the conflict at the step
   * where it is most expensive to act on.
   */
  readonly onValuesChange?: (values: BundleFormValues) => void;
};

/**
 * The constraint wizard.
 *
 * Four steps rather than one long form because the four decisions are not
 * independent — the rating you can hold depends on the audience you named, and
 * the scope you get depends on the tier — and a single page invites the writer
 * to fill it top to bottom without noticing that the third answer invalidated
 * the first.
 *
 * The draft is saved on every step transition rather than on every keystroke.
 * Per-keystroke autosave would put a network write behind each character, and
 * per-session saving would lose the work the criterion exists to protect. A
 * step boundary is where the writer has finished a thought.
 */
export function ConstraintWizard({
  projectId,
  options,
  initialValues,
  hasSavedDraft,
  onSaved,
  onValuesChange,
}: Props) {
  const [step, setStep] = useState(0);
  const [quickStart, setQuickStart] = useState(!hasSavedDraft);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<BundleFormValues>({
    resolver: zodResolver(bundleFormSchema),
    defaultValues: initialValues,
    mode: "onBlur",
  });

  const values = form.watch();
  const system = options.rating_systems.find(
    (candidate) => candidate.id === values.ratingSystem,
  );

  /*
   * `watch()` returns a fresh object on every render, so the effect is keyed
   * on the answers themselves rather than on their identity — otherwise it
   * would fire on every render and the panels downstream would refetch
   * forever. Serialising is also what makes "the answers did not really
   * change" a comparison the effect can make.
   */
  const serialised = JSON.stringify(values);
  useEffect(() => {
    onValuesChange?.(JSON.parse(serialised) as BundleFormValues);
  }, [serialised, onValuesChange]);

  function save(next: BundleFormValues) {
    startTransition(async () => {
      const result = await saveDraftAction(projectId, toBundle(next));
      if (!result.ok) {
        toast.error("Draft not saved", { description: result.error });
        return;
      }
      setSavedAt(result.data.updatedAt);
      onSaved?.(next);
    });
  }

  async function next() {
    const fields = STEP_FIELDS[step] ?? [];
    const valid = await form.trigger([...fields]);
    if (!valid) return;

    save(form.getValues());
    setStep((current) => Math.min(current + 1, STEPS.length - 1));
  }

  function applyQuickStart(next: BundleFormValues) {
    form.reset(next);
    setQuickStart(false);
    // Straight to the last step: Quick Start has answered everything, and
    // dropping the writer back on step one would imply it had not.
    setStep(STEPS.length - 1);
    save(next);
  }

  if (quickStart) {
    return (
      <QuickStart
        options={options}
        onApply={applyQuickStart}
        onSkip={() => setQuickStart(false)}
      />
    );
  }

  const current = STEPS[step];

  return (
    <Card>
      <CardHeader className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>{current?.title}</CardTitle>
          <div className="flex items-center gap-3">
            {savedAt !== null && (
              <span className="text-xs text-muted-foreground">Draft saved</span>
            )}
            <Badge variant="secondary">
              Step {step + 1} of {STEPS.length}
            </Badge>
          </div>
        </div>

        <ol className="flex flex-wrap gap-1" aria-label="Wizard progress">
          {STEPS.map((item, index) => (
            <li key={item.id} className="flex-1 basis-24">
              <button
                type="button"
                onClick={() => setStep(index)}
                aria-current={index === step ? "step" : undefined}
                className={cn(
                  "w-full rounded-md border px-2 py-1.5 text-left text-xs transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  index === step
                    ? "border-foreground/30 bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted/60",
                )}
              >
                <span className="flex items-center gap-1">
                  {index < step && (
                    <CheckIcon className="size-3" aria-hidden="true" />
                  )}
                  {item.title}
                </span>
              </button>
            </li>
          ))}
        </ol>
      </CardHeader>

      <CardContent className="space-y-6">
        {step === 0 && (
          <>
            <FieldRow
              name="genrePrimary"
              error={form.formState.errors.genrePrimary?.message}
            >
              <Controller
                control={form.control}
                name="genrePrimary"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger aria-label="Primary genre">
                      <SelectValue placeholder="Choose a genre" />
                    </SelectTrigger>
                    <SelectContent>
                      {options.genres.map((genre) => (
                        <SelectItem key={genre.id} value={genre.id}>
                          {genre.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </FieldRow>

            <FieldRow
              name="genreSecondary"
              error={form.formState.errors.genreSecondary?.message}
            >
              <Controller
                control={form.control}
                name="genreSecondary"
                render={({ field }) => (
                  <Select
                    value={field.value === "" ? "none" : field.value}
                    onValueChange={(value) =>
                      field.onChange(value === "none" ? "" : value)
                    }
                  >
                    <SelectTrigger aria-label="Secondary genre">
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      {options.genres
                        .filter((genre) => genre.id !== values.genrePrimary)
                        .map((genre) => (
                          <SelectItem key={genre.id} value={genre.id}>
                            {genre.label}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </FieldRow>
          </>
        )}

        {step === 1 && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <FieldRow
                name="audienceMinAge"
                htmlFor="audienceMinAge"
                error={form.formState.errors.audienceMinAge?.message}
              >
                <Input
                  id="audienceMinAge"
                  type="number"
                  min={0}
                  max={120}
                  {...form.register("audienceMinAge", { valueAsNumber: true })}
                />
              </FieldRow>
              <FieldRow
                name="audienceMaxAge"
                htmlFor="audienceMaxAge"
                error={form.formState.errors.audienceMaxAge?.message}
              >
                <Input
                  id="audienceMaxAge"
                  type="number"
                  min={0}
                  max={120}
                  {...form.register("audienceMaxAge", { valueAsNumber: true })}
                />
              </FieldRow>
            </div>

            <FieldRow
              name="ratingSystem"
              error={form.formState.errors.ratingSystem?.message}
            >
              <Controller
                control={form.control}
                name="ratingSystem"
                render={({ field }) => (
                  <Select
                    value={field.value}
                    onValueChange={(value) => {
                      field.onChange(value);
                      // A certificate is only meaningful inside its system, so
                      // changing the board must not leave the old one selected.
                      const next = options.rating_systems.find(
                        (candidate) => candidate.id === value,
                      );
                      form.setValue(
                        "ratingClassification",
                        next?.classifications[0]?.id ?? "",
                      );
                    }}
                  >
                    <SelectTrigger aria-label="Rating board">
                      <SelectValue placeholder="Choose a board" />
                    </SelectTrigger>
                    <SelectContent>
                      {options.rating_systems.map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </FieldRow>

            <FieldRow
              name="ratingClassification"
              error={form.formState.errors.ratingClassification?.message}
            >
              <Controller
                control={form.control}
                name="ratingClassification"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger aria-label="Target certificate">
                      <SelectValue placeholder="Choose a certificate" />
                    </SelectTrigger>
                    <SelectContent>
                      {(system?.classifications ?? []).map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.label} · {item.min_audience_age}+
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </FieldRow>
          </>
        )}

        {step === 2 && (
          <FieldRow
            name="budgetTierId"
            error={form.formState.errors.budgetTierId?.message}
          >
            <Controller
              control={form.control}
              name="budgetTierId"
              render={({ field }) => (
                <div
                  className="grid gap-3"
                  role="radiogroup"
                  aria-label="Production scale"
                >
                  {[...options.budget_tiers]
                    .sort((a, b) => a.order - b.order)
                    .map((tier) => {
                      const selected = field.value === tier.id;
                      return (
                        <button
                          key={tier.id}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          onClick={() => field.onChange(tier.id)}
                          className={cn(
                            "rounded-lg border p-4 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                            selected
                              ? "border-foreground/40 bg-muted"
                              : "hover:border-foreground/20",
                          )}
                        >
                          <span className="flex flex-wrap items-baseline justify-between gap-2">
                            <span className="font-medium">{tier.label}</span>
                            <span className="font-mono text-xs text-muted-foreground">
                              {budgetBand(tier)}
                            </span>
                          </span>
                          <span className="mt-2 block text-sm text-muted-foreground">
                            {scopePhrases(tier).join(" · ")}
                          </span>
                        </button>
                      );
                    })}
                </div>
              )}
            />
          </FieldRow>
        )}

        {step === 3 && (
          <FieldRow
            name="territoryIds"
            error={form.formState.errors.territoryIds?.message}
          >
            <Controller
              control={form.control}
              name="territoryIds"
              render={({ field }) => (
                <div className="grid gap-2 sm:grid-cols-2">
                  {options.territories.map((territory) => {
                    const checked = field.value.includes(territory.id);
                    return (
                      <label
                        key={territory.id}
                        className="flex items-center gap-3 rounded-md border p-3 text-sm transition-colors hover:border-foreground/20"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(state) =>
                            field.onChange(
                              state === true
                                ? [...field.value, territory.id]
                                : field.value.filter(
                                    (id) => id !== territory.id,
                                  ),
                            )
                          }
                        />
                        <span>
                          <span className="block">{territory.label}</span>
                          <span className="block text-xs text-muted-foreground uppercase">
                            {territory.rating_system}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            />
          </FieldRow>
        )}

        <div className="flex items-center justify-between gap-3 border-t pt-4">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setStep((current) => Math.max(current - 1, 0))}
            disabled={step === 0}
          >
            <ChevronLeftIcon className="size-4" aria-hidden="true" />
            Back
          </Button>

          <div className="flex items-center gap-2">
            {step === STEPS.length - 1 ? (
              <Button
                type="button"
                size="sm"
                disabled={pending}
                onClick={async () => {
                  const valid = await form.trigger();
                  if (valid) save(form.getValues());
                }}
              >
                {pending ? "Saving…" : "Save constraints"}
              </Button>
            ) : (
              <Button type="button" size="sm" onClick={next} disabled={pending}>
                Next
                <ChevronRightIcon className="size-4" aria-hidden="true" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
