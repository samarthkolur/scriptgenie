import type { KbOptions } from "@/lib/api-client";
import type { BundleFormValues } from "@/lib/constraints/schema";

/**
 * Quick Start: three questions that produce a complete, valid bundle.
 *
 * The acceptance criterion is that a writer reaches a working bundle *without
 * knowing SAG-AFTRA tiers*. So nothing here is named after the thing it maps
 * to — the writer picks "a few locations, a small cast", not `low_indie`, and
 * "old enough for swearing and real violence", not `r`.
 *
 * The mapping is derived from the knowledge base rather than hardcoded
 * wherever it can be. Classifications are chosen by comparing the audience
 * band against each certificate's own `min_audience_age`, so adding a rating
 * system or renaming a certificate changes the result here automatically. The
 * one thing that cannot be derived is which *tier* corresponds to "a small
 * cast", because that is an editorial judgement, not a fact in the data —
 * those are matched by `order`, which is the knowledge base's own ranking, so
 * they survive a tier being renamed.
 */

type RatingSystem = KbOptions["rating_systems"][number];

export type AudienceBand = {
  readonly id: string;
  readonly label: string;
  /** Written in what the audience can see, not in certificate names. */
  readonly description: string;
  readonly minAge: number;
  readonly maxAge: number;
};

export const AUDIENCE_BANDS: readonly AudienceBand[] = [
  {
    id: "family",
    label: "Everyone, including children",
    description:
      "Watchable by a family together. Mild peril at most, no sex, no strong language.",
    minAge: 6,
    maxAge: 70,
  },
  {
    id: "teen",
    label: "Teenagers and adults",
    description:
      "The broad commercial middle. Real violence and one hard swear, but nothing explicit.",
    minAge: 13,
    maxAge: 55,
  },
  {
    id: "adult",
    label: "Adults only",
    description:
      "Sustained violence, explicit language and adult themes are all available.",
    minAge: 18,
    maxAge: 65,
  },
];

export type ProductionScale = {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  /** Position in the knowledge base's own tier ordering, cheapest first. */
  readonly tierOrder: number;
};

export const PRODUCTION_SCALES: readonly ProductionScale[] = [
  {
    id: "contained",
    label: "Contained",
    description:
      "A handful of locations and a small cast. Shot over weeks, not months.",
    tierOrder: 0,
  },
  {
    id: "small",
    label: "Small independent",
    description:
      "Several locations, a named cast, limited effects work and no crowds.",
    tierOrder: 1,
  },
  {
    id: "mid",
    label: "Mid-size independent",
    description:
      "Location moves, a full speaking cast and effects where the story needs them.",
    tierOrder: 2,
  },
  {
    id: "large",
    label: "Large-scale production",
    description: "No practical ceiling on locations, cast, effects or period.",
    tierOrder: 3,
  },
];

/**
 * The certificate in `system` that admits an audience starting at `minAge`.
 *
 * The strictest certificate the audience actually clears: the highest
 * `min_audience_age` that does not exceed the band's own floor. Choosing the
 * *lowest* certificate instead would aim every teen film at a G, which no
 * writer means; choosing the highest available would aim a family film at an
 * R. When the band is younger than every certificate in the system — possible
 * for a board with no children's rating — the most permissive one is returned,
 * because a bundle naming no certificate cannot be generated at all.
 */
export function classificationForAge(
  system: RatingSystem,
  minAge: number,
): string | null {
  const ordered = [...system.classifications].sort(
    (a, b) => a.min_audience_age - b.min_audience_age,
  );
  if (ordered.length === 0) return null;

  let chosen = ordered[0];
  for (const option of ordered) {
    if (option.min_audience_age <= minAge) chosen = option;
  }
  return chosen?.id ?? null;
}

/** The territory the wizard opens on: the US when present, else the first. */
function defaultTerritory(options: KbOptions) {
  return (
    options.territories.find((t) => t.id === "us") ?? options.territories[0]
  );
}

function tierByOrder(options: KbOptions, order: number): string | null {
  const ordered = [...options.budget_tiers].sort((a, b) => a.order - b.order);
  return ordered[order]?.id ?? ordered[ordered.length - 1]?.id ?? null;
}

export type QuickStartAnswers = {
  readonly genrePrimary: string;
  readonly audienceBandId: string;
  readonly scaleId: string;
};

/**
 * The three answers as a full set of form values.
 *
 * Returns `null` only when the knowledge base is missing something the bundle
 * cannot be built without — no territories, no tiers, no certificates. That is
 * a broken knowledge base rather than a bad answer, and the caller shows it as
 * such instead of writing a bundle the API would refuse.
 */
export function quickStartValues(
  answers: QuickStartAnswers,
  options: KbOptions,
): BundleFormValues | null {
  const band =
    AUDIENCE_BANDS.find((b) => b.id === answers.audienceBandId) ??
    AUDIENCE_BANDS[1];
  const scale =
    PRODUCTION_SCALES.find((s) => s.id === answers.scaleId) ??
    PRODUCTION_SCALES[1];
  if (band === undefined || scale === undefined) return null;

  const territory = defaultTerritory(options);
  if (territory === undefined) return null;

  const system = options.rating_systems.find(
    (s) => s.id === territory.rating_system,
  );
  if (system === undefined) return null;

  const classification = classificationForAge(system, band.minAge);
  if (classification === null) return null;

  const budgetTierId = tierByOrder(options, scale.tierOrder);
  if (budgetTierId === null) return null;

  return {
    genrePrimary: answers.genrePrimary,
    genreSecondary: "",
    audienceMinAge: band.minAge,
    audienceMaxAge: band.maxAge,
    ratingSystem: system.id,
    ratingClassification: classification,
    budgetTierId,
    territoryIds: [territory.id],
  };
}
