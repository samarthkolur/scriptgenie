"use client";

import { StarIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { VariantCard } from "@/components/features/variants/variant-card";
import { VariantComparison } from "@/components/features/variants/variant-comparison";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { KbOptions, Variant } from "@/lib/api-client";
import { cn, labelFor } from "@/lib/utils";

const MAX_COMPARISON = 5;
const MIN_COMPARISON = 2;

type Props = {
  readonly variants: readonly Variant[];
  readonly options: KbOptions;
  readonly onToggleFavourite: (variant: Variant) => void;
  readonly onNotesChange: (variant: Variant, notes: string | null) => void;
};

/**
 * Every variant a project has ever produced, kept and actionable.
 *
 * Distinct from the transient run in `GenerationResults`: this list is seeded
 * from the database on page load and grows as runs succeed, so favouriting,
 * annotating and comparing all survive a reload — a variant a writer marked
 * last week is still marked when they come back to it.
 *
 * Search is client-side over what is already on the page rather than a server
 * round trip, because a project's variant count is bounded by how much has
 * been generated for it, not by a catalogue a query needs to page through.
 */
export function VariantGallery({
  variants,
  options,
  onToggleFavourite,
  onNotesChange,
}: Props) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [comparing, setComparing] = useState(false);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") return variants;
    return variants.filter((variant) => {
      const archetype = labelFor(
        variant.archetype_id,
        options.archetypes,
      ).toLowerCase();
      return (
        variant.title.toLowerCase().includes(needle) ||
        variant.logline.toLowerCase().includes(needle) ||
        archetype.includes(needle)
      );
    });
  }, [variants, query, options.archetypes]);

  function toggleSelected(variantId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(variantId)) {
        next.delete(variantId);
      } else if (next.size < MAX_COMPARISON) {
        next.add(variantId);
      }
      return next;
    });
  }

  const selectedVariants = variants.filter((variant) =>
    selected.has(variant.id),
  );

  if (variants.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Nothing generated yet. Variants appear here, favouritable and
          searchable, the moment a run produces one.
        </CardContent>
      </Card>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-medium">
          Library · {variants.length}{" "}
          {variants.length === 1 ? "variant" : "variants"}
        </h3>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search title, logline or archetype"
            aria-label="Search variants"
            className="w-56"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={selected.size < MIN_COMPARISON}
            onClick={() => setComparing(true)}
          >
            Compare {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing here matches “{query}”.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {filtered.map((variant) => (
            <div key={variant.id} className="space-y-2">
              <VariantCard
                variant={variant}
                archetypeLabel={labelFor(
                  variant.archetype_id,
                  options.archetypes,
                )}
              />
              <VariantToolbar
                variant={variant}
                selected={selected.has(variant.id)}
                selectionDisabled={
                  !selected.has(variant.id) && selected.size >= MAX_COMPARISON
                }
                onToggleSelected={() => toggleSelected(variant.id)}
                onToggleFavourite={() => onToggleFavourite(variant)}
                onNotesChange={(notes) => onNotesChange(variant, notes)}
              />
            </div>
          ))}
        </div>
      )}

      <VariantComparison
        variants={selectedVariants}
        options={options}
        open={comparing}
        onOpenChange={setComparing}
      />
    </section>
  );
}

function VariantToolbar({
  variant,
  selected,
  selectionDisabled,
  onToggleSelected,
  onToggleFavourite,
  onNotesChange,
}: {
  readonly variant: Variant;
  readonly selected: boolean;
  readonly selectionDisabled: boolean;
  readonly onToggleSelected: () => void;
  readonly onToggleFavourite: () => void;
  readonly onNotesChange: (notes: string | null) => void;
}) {
  const [notes, setNotes] = useState(variant.notes ?? "");
  const fieldId = `variant-notes-${variant.id}`;
  const compareId = `variant-compare-${variant.id}`;

  function saveNotes() {
    const trimmed = notes.trim();
    if (trimmed === (variant.notes ?? "")) return;
    onNotesChange(trimmed === "" ? null : trimmed);
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed p-3">
      <div className="flex items-center justify-between gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-pressed={variant.favourite}
          onClick={onToggleFavourite}
        >
          <StarIcon
            className={cn(
              "size-4",
              variant.favourite && "fill-current text-amber-500",
            )}
            aria-hidden="true"
          />
          <span className="sr-only">
            {variant.favourite
              ? `Remove ${variant.title} from favourites`
              : `Mark ${variant.title} a favourite`}
          </span>
        </Button>

        <div className="flex items-center gap-1.5">
          <Checkbox
            id={compareId}
            checked={selected}
            disabled={selectionDisabled}
            onCheckedChange={onToggleSelected}
          />
          <Label htmlFor={compareId} className="text-xs font-normal">
            Compare
          </Label>
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor={fieldId} className="text-xs text-muted-foreground">
          Notes
        </Label>
        <Textarea
          id={fieldId}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          onBlur={saveNotes}
          placeholder="Nothing noted yet."
          maxLength={4000}
          className="min-h-12 text-xs"
        />
      </div>
    </div>
  );
}
