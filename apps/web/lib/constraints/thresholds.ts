import type { ResolveResponse } from "@/lib/api-client";

/**
 * The content ceilings an envelope carries, in words rather than numbers.
 *
 * `ContentLevel` is 0–4 and the arithmetic that produces it is the point of
 * the engine, but "violence: 2" is not a sentence anyone writes a script from.
 * The levels are named here once so the ceiling reads the same wherever it is
 * shown, and the level is kept beside the word so the ordering stays visible.
 *
 * Provenance matters as much as the number. A ceiling with no named authority
 * is indistinguishable from an arbitrary limit, and a writer who cannot see
 * that the MPA imposed it has no way to judge whether it is worth arguing with.
 */

type Envelope = ResolveResponse["envelope"];
type Dimension = keyof Envelope["thresholds"];
type Level = Envelope["thresholds"][Dimension];

const DIMENSION_LABELS: Readonly<Record<Dimension, string>> = {
  violence: "Violence",
  sexual_content: "Sexual content",
  language: "Language",
  thematic_darkness: "Thematic darkness",
  drug_use: "Drug use",
  horror_intensity: "Horror intensity",
};

/** Reading order: the dimensions boards cut for, before the ones they note. */
const DIMENSION_ORDER: readonly Dimension[] = [
  "violence",
  "sexual_content",
  "language",
  "drug_use",
  "thematic_darkness",
  "horror_intensity",
];

const LEVEL_WORDS: readonly string[] = [
  "none",
  "mild",
  "moderate",
  "strong",
  "explicit",
];

/** The word for a level, falling back to the number if the scale ever grows. */
export function levelWord(level: number): string {
  return LEVEL_WORDS[level] ?? `level ${String(level)}`;
}

export type ThresholdRow = {
  readonly dimension: Dimension;
  readonly label: string;
  readonly level: Level;
  readonly word: string;
  /** The board or tier that set this ceiling, when the envelope names one. */
  readonly authority: string | null;
  readonly detail: string | null;
};

/**
 * Every content ceiling in the envelope, with the authority behind it.
 *
 * Provenance is matched by dimension. An entry the envelope does not explain
 * keeps a `null` authority rather than borrowing another dimension's, because
 * attributing a ceiling to a board that did not impose it is worse than
 * admitting the ceiling is unattributed.
 */
export function thresholdRows(envelope: Envelope): readonly ThresholdRow[] {
  const sources = new Map(
    envelope.provenance.map((source) => [source.dimension, source]),
  );

  return DIMENSION_ORDER.map((dimension) => {
    const level = envelope.thresholds[dimension];
    const source = sources.get(dimension);
    return {
      dimension,
      label: DIMENSION_LABELS[dimension],
      level,
      word: levelWord(level),
      authority: source?.authority ?? null,
      detail: source?.detail ?? null,
    };
  });
}

/**
 * What the chosen resolutions actually moved, as sentences.
 *
 * Only clamps move a level; an acknowledgement records a decision and changes
 * no number. Rendering both as "changed" would tell the writer their
 * acknowledgement had tightened the envelope when it had not.
 */
export function describeDeltas(
  deltas: ResolveResponse["deltas"],
): readonly string[] {
  return deltas.map((delta) => {
    const dimension = delta.dimension ?? null;
    const label =
      dimension === null ? null : DIMENSION_LABELS[dimension as Dimension];

    if (
      delta.effect_kind === "clamp_dimension_to_permitted" &&
      label !== null &&
      delta.from_level !== null &&
      delta.from_level !== undefined &&
      delta.to_level !== null &&
      delta.to_level !== undefined
    ) {
      return `${label} held at ${levelWord(delta.to_level)}, down from ${levelWord(delta.from_level)}.`;
    }

    if (delta.effect_kind === "requires_bundle_change") {
      return `${delta.rule_id}: you have chosen to revise an answer rather than settle this here.`;
    }

    return (
      delta.guidance ?? `${delta.rule_id}: acknowledged, with no bound moved.`
    );
  });
}
