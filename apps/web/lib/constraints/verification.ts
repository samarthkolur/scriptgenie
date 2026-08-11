import type { Variant } from "@/lib/api-client";
import { dimensionLabel } from "@/lib/constraints/thresholds";

/**
 * Reading the verdict a variant earned, axis by axis.
 *
 * Three values only, and they are not a scale from best to worst — `PASS` and
 * `FLAGGED` are opposite answers to an arithmetic question, while
 * `NEEDS_REVIEW` is a different question entirely: a keyword pass that cannot
 * clear an axis on its own, only raise it for a human. Copy earns its place
 * beside CLAUDE.md's rule that nothing here says "certified" or "compliant" —
 * `PASS` reads as "verified for scope", never as a claim a ratings board would
 * make.
 */
export type Verdict = "PASS" | "FLAGGED" | "NEEDS_REVIEW";

export const VERDICT_COPY: Readonly<
  Record<Verdict, { readonly label: string; readonly badgeClass: string }>
> = {
  PASS: {
    label: "Verified for scope",
    badgeClass: "border-transparent bg-emerald-600 text-white",
  },
  FLAGGED: {
    label: "Flagged",
    badgeClass: "border-transparent bg-destructive text-white",
  },
  NEEDS_REVIEW: {
    label: "Needs review",
    badgeClass:
      "border-amber-500/60 bg-amber-500/15 text-amber-900 dark:text-amber-200",
  },
};

/** True only when every axis this variant carries returned `PASS`. */
export function isVerified(verdicts: Variant["verdicts"]): boolean {
  return Object.values(verdicts).every((verdict) => verdict === "PASS");
}

/** The worst verdict a variant carries, for a single summary badge. */
export function overallVerdict(verdicts: Variant["verdicts"]): Verdict {
  const values = Object.values(verdicts) as Verdict[];
  if (values.includes("FLAGGED")) return "FLAGGED";
  if (values.includes("NEEDS_REVIEW")) return "NEEDS_REVIEW";
  return "PASS";
}

const SCOPE_PARAMETER_LABELS: Readonly<Record<string, string>> = {
  max_locations: "Locations",
  max_named_characters: "Named characters",
};

/** A scope check's parameter, in words. Content dimensions share the map. */
export function parameterLabel(parameter: string): string {
  return SCOPE_PARAMETER_LABELS[parameter] ?? dimensionLabel(parameter);
}
