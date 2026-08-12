"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { KbOptions } from "@/lib/api-client";
import {
  AUDIENCE_BANDS,
  PRODUCTION_SCALES,
  quickStartValues,
} from "@/lib/constraints/quick-start";
import type { BundleFormValues } from "@/lib/constraints/schema";
import { cn } from "@/lib/utils";

type Props = {
  readonly options: KbOptions;
  readonly onApply: (values: BundleFormValues) => void;
  readonly onSkip: () => void;
};

/**
 * Three questions that produce a complete bundle.
 *
 * Nothing here names a certificate, a rating board or a guild tier. A writer
 * who knows their film is a horror for adults that can afford four locations
 * should not have to learn what a SAG-AFTRA modified-low agreement is to say
 * so; the mapping happens in `lib/constraints/quick-start.ts`, where it is
 * derived from the knowledge base and tested.
 *
 * What it produces is a real bundle, not a partial one. The writer lands on
 * the last step of the full wizard with every answer filled in, so the
 * translation is visible and can be corrected rather than hidden.
 */
export function QuickStart({ options, onApply, onSkip }: Props) {
  const [genre, setGenre] = useState(options.genres[0]?.id ?? "");
  const [band, setBand] = useState(AUDIENCE_BANDS[1]?.id ?? "");
  const [scale, setScale] = useState(PRODUCTION_SCALES[1]?.id ?? "");
  const [error, setError] = useState<string | null>(null);

  function apply() {
    const values = quickStartValues(
      { genrePrimary: genre, audienceBandId: band, scaleId: scale },
      options,
    );
    if (values === null) {
      setError(
        "The knowledge base is missing something these answers need. Use the full wizard.",
      );
      return;
    }
    onApply(values);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick start</CardTitle>
        <p className="text-sm text-muted-foreground">
          Three questions. We translate them into a certificate, a scope and a
          territory, and show you the result so you can change any of it.
        </p>
      </CardHeader>

      <CardContent className="space-y-8">
        <div className="space-y-2">
          <Label htmlFor="quick-genre">What kind of film is it?</Label>
          <Select value={genre} onValueChange={setGenre}>
            <SelectTrigger id="quick-genre">
              <SelectValue placeholder="Choose a genre" />
            </SelectTrigger>
            <SelectContent>
              {options.genres.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">Who is it for?</legend>
          <RadioGroup value={band} onValueChange={setBand} className="gap-2">
            {AUDIENCE_BANDS.map((item) => (
              <label
                key={item.id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                  band === item.id
                    ? "border-foreground/40 bg-muted"
                    : "hover:border-foreground/20",
                )}
              >
                <RadioGroupItem value={item.id} className="mt-1" />
                <span className="space-y-0.5">
                  <span className="block text-sm font-medium">
                    {item.label}
                  </span>
                  <span className="block text-sm text-muted-foreground">
                    {item.description}
                  </span>
                </span>
              </label>
            ))}
          </RadioGroup>
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">
            How much can you shoot?
          </legend>
          <RadioGroup value={scale} onValueChange={setScale} className="gap-2">
            {PRODUCTION_SCALES.map((item) => (
              <label
                key={item.id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                  scale === item.id
                    ? "border-foreground/40 bg-muted"
                    : "hover:border-foreground/20",
                )}
              >
                <RadioGroupItem value={item.id} className="mt-1" />
                <span className="space-y-0.5">
                  <span className="block text-sm font-medium">
                    {item.label}
                  </span>
                  <span className="block text-sm text-muted-foreground">
                    {item.description}
                  </span>
                </span>
              </label>
            ))}
          </RadioGroup>
        </fieldset>

        {error !== null && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <Button type="button" variant="ghost" size="sm" onClick={onSkip}>
            Set everything myself
          </Button>
          <Button type="button" size="sm" onClick={apply}>
            Continue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
