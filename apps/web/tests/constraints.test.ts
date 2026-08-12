import { describe, expect, it } from "vitest";

import type { KbOptions } from "@/lib/api-client";
import { FIELD_HELP } from "@/lib/constraints/field-help";
import {
  AUDIENCE_BANDS,
  PRODUCTION_SCALES,
  classificationForAge,
  quickStartValues,
} from "@/lib/constraints/quick-start";
import {
  DEFAULT_FORM_VALUES,
  bundleFormSchema,
  fromBundle,
  toBundle,
} from "@/lib/constraints/schema";

/** A knowledge base shaped like the real one, small enough to reason about. */
const OPTIONS: KbOptions = {
  kb_version: "0.1.1",
  genres: [
    { id: "horror", label: "Horror", hybrid_friendly: ["comedy"] },
    { id: "drama", label: "Drama", hybrid_friendly: [] },
  ],
  budget_tiers: [
    {
      id: "micro",
      label: "Micro",
      order: 0,
      min_usd: 0,
      max_usd: 250000,
      guild_context: "SAG-AFTRA Micro Budget",
      scope: {},
    },
    {
      id: "low_indie",
      label: "Low independent",
      order: 1,
      min_usd: 250000,
      max_usd: 2000000,
      guild_context: "SAG-AFTRA Low Budget",
      scope: {},
    },
    {
      id: "mid_indie",
      label: "Mid independent",
      order: 2,
      min_usd: 2000000,
      max_usd: 20000000,
      guild_context: "SAG-AFTRA Modified Low",
      scope: {},
    },
    {
      id: "studio",
      label: "Studio",
      order: 3,
      min_usd: 20000000,
      max_usd: null,
      guild_context: "SAG-AFTRA Theatrical",
      scope: {},
    },
  ],
  rating_systems: [
    {
      id: "mpa",
      label: "MPA",
      territory: "us",
      classifications: [
        { id: "g", label: "G", min_audience_age: 0 },
        { id: "pg", label: "PG", min_audience_age: 8 },
        { id: "pg_13", label: "PG-13", min_audience_age: 13 },
        { id: "r", label: "R", min_audience_age: 17 },
      ],
    },
  ],
  territories: [
    { id: "us", label: "United States", rating_system: "mpa" },
    { id: "india", label: "India", rating_system: "cbfc" },
  ],
  archetypes: [],
};

describe("bundleFormSchema", () => {
  it("accepts the defaults it ships with", () => {
    // A default set that does not validate is a wizard that opens broken.
    expect(bundleFormSchema.safeParse(DEFAULT_FORM_VALUES).success).toBe(true);
  });

  it("treats an empty secondary genre as no secondary genre", () => {
    const parsed = bundleFormSchema.safeParse({
      ...DEFAULT_FORM_VALUES,
      genreSecondary: "",
    });

    expect(parsed.success).toBe(true);
    expect(toBundle(DEFAULT_FORM_VALUES).genre.secondary).toBeUndefined();
  });

  it("refuses a secondary genre equal to the primary", () => {
    const parsed = bundleFormSchema.safeParse({
      ...DEFAULT_FORM_VALUES,
      genreSecondary: DEFAULT_FORM_VALUES.genrePrimary,
    });

    expect(parsed.success).toBe(false);
  });

  it("refuses an age band whose top is below its bottom", () => {
    const parsed = bundleFormSchema.safeParse({
      ...DEFAULT_FORM_VALUES,
      audienceMinAge: 40,
      audienceMaxAge: 18,
    });

    expect(parsed.success).toBe(false);
  });

  it("refuses a release in no territory at all", () => {
    const parsed = bundleFormSchema.safeParse({
      ...DEFAULT_FORM_VALUES,
      territoryIds: [],
    });

    expect(parsed.success).toBe(false);
  });

  it("round-trips a bundle through the form and back", () => {
    // Reopening a saved draft must show what was saved, not an approximation.
    const bundle = toBundle(DEFAULT_FORM_VALUES);

    expect(toBundle(fromBundle(bundle))).toEqual(bundle);
  });

  it("round-trips a bundle carrying a secondary genre", () => {
    const values = { ...DEFAULT_FORM_VALUES, genreSecondary: "comedy" };

    expect(toBundle(fromBundle(toBundle(values))).genre).toEqual({
      primary: values.genrePrimary,
      secondary: "comedy",
    });
  });
});

describe("classificationForAge", () => {
  const mpa = OPTIONS.rating_systems[0]!;

  it("picks the strictest certificate the audience clears", () => {
    // 13 clears PG-13. Aiming a teen film at G is not what anyone means.
    expect(classificationForAge(mpa, 13)).toBe("pg_13");
  });

  it("does not pick a certificate the audience is too young for", () => {
    expect(classificationForAge(mpa, 8)).toBe("pg");
    expect(classificationForAge(mpa, 12)).toBe("pg");
  });

  it("gives an adult audience the adult certificate", () => {
    expect(classificationForAge(mpa, 18)).toBe("r");
  });

  it("falls back to the most permissive when the band is below them all", () => {
    const strict = {
      ...mpa,
      classifications: [{ id: "fifteen", label: "15", min_audience_age: 15 }],
    };

    // A bundle naming no certificate cannot be generated at all, so something
    // has to be chosen.
    expect(classificationForAge(strict, 6)).toBe("fifteen");
  });

  it("is null only when the system defines no certificates", () => {
    expect(
      classificationForAge({ ...mpa, classifications: [] }, 13),
    ).toBeNull();
  });
});

describe("quickStartValues", () => {
  it("produces a bundle the API schema accepts", () => {
    // The acceptance criterion: three plain-English answers, a valid bundle.
    const values = quickStartValues(
      { genrePrimary: "horror", audienceBandId: "teen", scaleId: "contained" },
      OPTIONS,
    );

    expect(values).not.toBeNull();
    expect(bundleFormSchema.safeParse(values).success).toBe(true);
  });

  it("never asks the writer for a guild tier", () => {
    // Nothing a writer reads in Quick Start may name the thing it maps to.
    const wording = PRODUCTION_SCALES.flatMap((scale) => [
      scale.id,
      scale.label,
      scale.description,
    ])
      .join(" ")
      .toLowerCase();

    expect(wording).not.toContain("sag");
    expect(wording).not.toContain("aftra");
    for (const tier of OPTIONS.budget_tiers) {
      expect(wording).not.toContain(tier.id);
    }
  });

  it("maps each scale to a distinct tier, cheapest to largest", () => {
    const tiers = PRODUCTION_SCALES.map(
      (scale) =>
        quickStartValues(
          { genrePrimary: "drama", audienceBandId: "teen", scaleId: scale.id },
          OPTIONS,
        )?.budgetTierId,
    );

    expect(tiers).toEqual(["micro", "low_indie", "mid_indie", "studio"]);
  });

  it("derives the rating system from the territory rather than assuming one", () => {
    const values = quickStartValues(
      { genrePrimary: "drama", audienceBandId: "family", scaleId: "mid" },
      OPTIONS,
    );

    expect(values?.ratingSystem).toBe("mpa");
    expect(values?.territoryIds).toEqual(["us"]);
  });

  it("gives each audience band the certificate that band clears", () => {
    const certificates = AUDIENCE_BANDS.map(
      (band) =>
        quickStartValues(
          {
            genrePrimary: "drama",
            audienceBandId: band.id,
            scaleId: "mid",
          },
          OPTIONS,
        )?.ratingClassification,
    );

    expect(certificates).toEqual(["g", "pg_13", "r"]);
  });

  it("keeps the genre the writer chose", () => {
    const values = quickStartValues(
      { genrePrimary: "horror", audienceBandId: "adult", scaleId: "large" },
      OPTIONS,
    );

    expect(values?.genrePrimary).toBe("horror");
  });

  it("reports a knowledge base with no territories rather than inventing one", () => {
    const empty = { ...OPTIONS, territories: [] };

    expect(
      quickStartValues(
        { genrePrimary: "drama", audienceBandId: "teen", scaleId: "mid" },
        empty,
      ),
    ).toBeNull();
  });
});

describe("field help", () => {
  it("covers every field the form collects", () => {
    // The criterion is "every field has a tooltip", which needs enumerating
    // rather than spot-checking.
    for (const field of Object.keys(DEFAULT_FORM_VALUES)) {
      expect(FIELD_HELP, `no help for ${field}`).toHaveProperty(field);
    }
  });

  it("explains each field in production terms, not implementation terms", () => {
    const forbidden = ["dimension", "envelope", "predicate", "enum", "schema"];

    for (const [field, entry] of Object.entries(FIELD_HELP)) {
      expect(
        entry.help.length,
        `${field} help is too short to help`,
      ).toBeGreaterThan(60);
      for (const word of forbidden) {
        expect(
          entry.help.toLowerCase(),
          `${field} help leaks the word "${word}"`,
        ).not.toContain(word);
      }
    }
  });
});
