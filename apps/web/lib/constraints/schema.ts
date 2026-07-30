import { z } from "zod";

import type { ConstraintBundle } from "@/lib/api-client";

/**
 * The wizard's form schema, mirroring the API's `ConstraintBundle`.
 *
 * Restating the shape here is deliberate and is not the duplication the
 * generated types exist to prevent. `types/api.ts` describes what the wire
 * accepts; this describes what a half-filled form looks like on its way there,
 * which is a different thing — a bundle has no partial state, and a form is
 * nothing but partial states. What keeps the two in step is `toBundle`, whose
 * return type is the generated `ConstraintBundle`: change the API shape and
 * this file stops compiling.
 *
 * The messages are written to be read by a writer, not a developer. "Required"
 * tells someone nothing they did not already know from the empty field.
 */

const identifier = z
  .string()
  .regex(/^[a-z][a-z0-9_]*$/, "not a value this knowledge base defines");

/**
 * Ages are plain numbers here, not `z.coerce.number()`.
 *
 * Coercion would make the schema's input type `unknown` and its output
 * `number`, and `useForm` is generic over a single type — the two would no
 * longer match and the resolver would not typecheck under
 * `exactOptionalPropertyTypes`. The string an `<input type="number">` yields is
 * converted at the field instead, with `valueAsNumber`, which is where the
 * conversion belongs: the form's values are numbers at every point the schema
 * sees them.
 */
const age = z
  .number()
  .int("An age is a whole number.")
  .min(0, "An age cannot be negative.")
  .max(120, "An age above 120 is not an audience.");

export const bundleFormSchema = z
  .object({
    genrePrimary: identifier.min(1, "Choose the genre the film sits in."),
    // "" is what an unselected <Select> yields, and it has to survive
    // validation as "no secondary genre" rather than failing as a bad id.
    genreSecondary: z.union([identifier, z.literal("")]),
    audienceMinAge: age,
    audienceMaxAge: age,
    ratingSystem: identifier.min(1, "Choose the board you are classifying to."),
    ratingClassification: identifier.min(
      1,
      "Choose the certificate you are aiming for.",
    ),
    budgetTierId: identifier.min(1, "Choose the scale you are producing at."),
    territoryIds: z
      .array(identifier)
      .min(
        1,
        "Choose at least one territory — scope depends on where it ships.",
      ),
  })
  .refine((value) => value.audienceMaxAge >= value.audienceMinAge, {
    path: ["audienceMaxAge"],
    message: "The oldest age in the band cannot be below the youngest.",
  })
  .refine((value) => value.genreSecondary !== value.genrePrimary, {
    path: ["genreSecondary"],
    message: "A secondary genre has to differ from the primary one.",
  });

export type BundleFormValues = z.infer<typeof bundleFormSchema>;

/**
 * The form's answers as the bundle the API accepts.
 *
 * The empty string becomes an absent secondary rather than an empty one. The
 * API would reject `""` as a genre id, and it means "none" here.
 */
export function toBundle(values: BundleFormValues): ConstraintBundle {
  return {
    genre: {
      primary: values.genrePrimary,
      ...(values.genreSecondary === ""
        ? {}
        : { secondary: values.genreSecondary }),
    },
    audience: {
      min_age: values.audienceMinAge,
      max_age: values.audienceMaxAge,
    },
    rating: {
      system: values.ratingSystem,
      classification: values.ratingClassification,
    },
    budget_tier_id: values.budgetTierId,
    territories: { ids: values.territoryIds },
  };
}

/** A saved bundle as form values, for reopening a draft. */
export function fromBundle(bundle: ConstraintBundle): BundleFormValues {
  return {
    genrePrimary: bundle.genre.primary,
    genreSecondary: bundle.genre.secondary ?? "",
    audienceMinAge: bundle.audience.min_age,
    audienceMaxAge: bundle.audience.max_age,
    ratingSystem: bundle.rating.system,
    ratingClassification: bundle.rating.classification,
    budgetTierId: bundle.budget_tier_id,
    territoryIds: [...bundle.territories.ids],
  };
}

/**
 * What the wizard opens on for a writer who has answered nothing.
 *
 * A US release at mid-tier independent scale aiming at PG-13, which the build
 * plan names as the sensible default. Defaults are not neutral — most writers
 * will change one field and generate — so these are chosen to be the least
 * surprising rather than the least restrictive.
 */
export const DEFAULT_FORM_VALUES: BundleFormValues = {
  genrePrimary: "drama",
  genreSecondary: "",
  audienceMinAge: 13,
  audienceMaxAge: 55,
  ratingSystem: "mpa",
  ratingClassification: "pg_13",
  budgetTierId: "mid_indie",
  territoryIds: ["us"],
};
