import type { BundleFormValues } from "@/lib/constraints/schema";

/**
 * The label and explanation for every field the wizard asks about.
 *
 * Kept as data rather than as strings scattered through JSX for one reason:
 * the stage's acceptance criterion is that *every* field carries a tooltip
 * written in production terms, and a criterion phrased as "every" needs
 * something a test can enumerate. `tests/constraint-help.test.ts` walks the
 * form's own keys and asserts each has an entry, so a field added without help
 * fails a test rather than shipping bare.
 *
 * Research doc Risk 4 is the reason the wording matters. The audience for this
 * tool is writers and producers, not people who have read the knowledge base;
 * an explanation that says "sets the content ceiling on six dimensions"
 * describes our implementation, not their decision. Each of these says what
 * the choice does to the film.
 */

export type FieldName = keyof BundleFormValues;

export type FieldHelp = {
  readonly label: string;
  /** One or two sentences, in the vocabulary of a production meeting. */
  readonly help: string;
};

export const FIELD_HELP: Record<FieldName, FieldHelp> = {
  genrePrimary: {
    label: "Primary genre",
    help: "The genre the film is sold as. It sets what audiences expect to be delivered — a horror that never frightens is a failed horror, so this drives the intensity the generator aims for.",
  },
  genreSecondary: {
    label: "Secondary genre",
    help: "An optional modifier, not an equal partner. A horror-comedy is still a horror; the comedy changes the tone of scenes rather than halving the scares. Leave it empty unless the blend is deliberate.",
  },
  audienceMinAge: {
    label: "Youngest viewer",
    help: "The youngest person you intend to sell a ticket to. This is the number that decides which certificate you can realistically hold, so setting it low narrows what the story can show.",
  },
  audienceMaxAge: {
    label: "Oldest viewer",
    help: "The upper end of the audience you are writing for. It widens or narrows the band rather than restricting content, and mostly affects whether the material reads as too young for the people you are targeting.",
  },
  ratingSystem: {
    label: "Rating board",
    help: "Whose certificate you are aiming for — the MPA in the US, the BBFC in the UK, the CBFC in India. Boards do not agree with each other, so the same cut can pass in one country and be refused in another.",
  },
  ratingClassification: {
    label: "Target certificate",
    help: "The certificate you intend to be awarded. This is the hardest constraint in the tool: it sets a ceiling on violence, language, sexual content, drug use, thematic darkness and horror intensity, and the generator will not write past it.",
  },
  budgetTierId: {
    label: "Production scale",
    help: "What you can afford to shoot, expressed as the things a script actually spends: how many locations, how large a speaking cast, how much effects work, and whether a period setting is affordable.",
  },
  territoryIds: {
    label: "Release territories",
    help: "Where the film is intended to be released. Some territories restrict content beyond their certificate — material that clears the board can still be refused — so adding a territory can tighten the bounds rather than only widening the audience.",
  },
};
