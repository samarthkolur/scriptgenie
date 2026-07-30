import type { ConflictReport, ResolutionChoice } from "@/lib/api-client";

/**
 * What a conflict's severity means to the writer, and what it costs them.
 *
 * The API's `Severity` is deliberately not ordinal — see `app/domain/enums.py`
 * — so nothing here compares severities by position either. This is a policy
 * about interruption expressed as data: HARD stops the run, SOFT asks for a
 * decision, ADVISORY can be put away. Keeping it as a table rather than as
 * branches in the panel is what lets the same three sentences appear in the
 * badge, the group heading and the blocked-button explanation without three
 * chances to word them differently.
 */

type Conflict = ConflictReport["conflicts"][number];
type Severity = Conflict["severity"];
type ResolutionOption = Conflict["resolutions"][number];

/** Reading order: what blocks first, what can wait last. */
export const SEVERITY_ORDER = ["HARD", "SOFT", "ADVISORY"] as const;

export type SeverityCopy = {
  /** The word shown on the badge. */
  readonly label: string;
  /**
   * Read aloud in place of the colour. A screen-reader user must learn that a
   * conflict blocks generation from the text, not from the badge being red.
   */
  readonly announcement: string;
  /** The group heading, in the second person. */
  readonly heading: string;
  /** What this severity does to the writer, one sentence. */
  readonly meaning: string;
};

export const SEVERITY_COPY: Readonly<Record<Severity, SeverityCopy>> = {
  HARD: {
    label: "Blocking",
    announcement: "Blocking conflict",
    heading: "Has to be settled before you can generate",
    meaning:
      "No story satisfies both of these at once. Generation stays disabled until you settle each one.",
  },
  SOFT: {
    label: "Needs a decision",
    announcement: "Conflict needing a decision",
    heading: "Needs your acknowledgement",
    meaning:
      "This narrows what the generator can do. You can proceed, but only after saying you have seen it.",
  },
  ADVISORY: {
    label: "Worth knowing",
    announcement: "Advisory note",
    heading: "Worth knowing",
    meaning:
      "Nothing is blocked. This is a tension experienced writers usually want flagged.",
  },
};

/**
 * Whether choosing this option actually settles the conflict.
 *
 * `requires_bundle_change` never does: it is the writer saying they intend to
 * revise an answer, and until they do the conflict stands. The engine holds
 * the same rule in `resolution._is_cleared`, and re-runs detection to prove it
 * — this copy exists only so the button can grey out before the round trip,
 * never so the browser can decide the question. A disagreement between the two
 * ends with the API refusing, which is the correct way round.
 */
export function settlesConflict(option: ResolutionOption): boolean {
  const effect = option.effect;
  // No declared effect is an acknowledgement, which does settle it.
  if (effect === null || effect === undefined) return true;
  return effect.kind !== "requires_bundle_change";
}

/** The conflicts of one severity, in the order the API sorted them. */
export function bySeverity(
  conflicts: readonly Conflict[],
  severity: Severity,
): readonly Conflict[] {
  return conflicts.filter((conflict) => conflict.severity === severity);
}

/** A `rule_id -> resolution_id` view of the choices made so far. */
export function choiceMap(
  choices: readonly ResolutionChoice[],
): ReadonlyMap<string, string> {
  return new Map(
    choices.map((choice) => [choice.rule_id, choice.resolution_id]),
  );
}

/** The HARD conflicts that no chosen resolution would settle. */
export function unsettledHard(
  conflicts: readonly Conflict[],
  choices: readonly ResolutionChoice[],
): readonly Conflict[] {
  const chosen = choiceMap(choices);
  return bySeverity(conflicts, "HARD").filter((conflict) => {
    const resolutionId = chosen.get(conflict.rule_id);
    if (resolutionId === undefined) return true;
    const option = conflict.resolutions.find(
      (item) => item.id === resolutionId,
    );
    return option === undefined || !settlesConflict(option);
  });
}

/** The SOFT conflicts the writer has not yet ticked. */
export function unacknowledgedSoft(
  conflicts: readonly Conflict[],
  acknowledged: ReadonlySet<string>,
): readonly Conflict[] {
  return bySeverity(conflicts, "SOFT").filter(
    (conflict) => !acknowledged.has(conflict.rule_id),
  );
}

export type Gate =
  | { readonly allowed: true }
  | { readonly allowed: false; readonly reason: string };

/**
 * Whether generation may be attempted, and if not, why in one sentence.
 *
 * The sentence is the point. A disabled button with no explanation is the
 * failure mode this whole panel exists to prevent, so the caller is given
 * prose it can put next to the button and into `aria-describedby` rather than
 * a boolean it would have to narrate itself.
 *
 * ADVISORY conflicts are absent from this function on purpose: dismissing one
 * is a preference about what the writer wants to keep reading, and a
 * preference must never be able to change what the system permits.
 */
export function generationGate(
  conflicts: readonly Conflict[],
  choices: readonly ResolutionChoice[],
  acknowledged: ReadonlySet<string>,
): Gate {
  const hard = unsettledHard(conflicts, choices);
  if (hard.length > 0) {
    return {
      allowed: false,
      reason:
        hard.length === 1
          ? `Generation is blocked: “${hard[0]?.title}” has to be settled first.`
          : `Generation is blocked: ${hard.length} conflicts have to be settled first.`,
    };
  }

  const soft = unacknowledgedSoft(conflicts, acknowledged);
  if (soft.length > 0) {
    return {
      allowed: false,
      reason:
        soft.length === 1
          ? `Acknowledge “${soft[0]?.title}” to continue.`
          : `Acknowledge ${soft.length} conflicts to continue.`,
    };
  }

  return { allowed: true };
}

/**
 * A one-line summary of the report for the panel header.
 *
 * Counted from the conflicts rather than read from `report.counts`, so the
 * heading cannot disagree with the list beneath it.
 */
export function summarise(conflicts: readonly Conflict[]): string {
  if (conflicts.length === 0) return "No conflicts in these constraints.";

  const parts = SEVERITY_ORDER.map((severity) => {
    const count = bySeverity(conflicts, severity).length;
    return count === 0
      ? null
      : `${count} ${SEVERITY_COPY[severity].label.toLowerCase()}`;
  }).filter((part): part is string => part !== null);

  return parts.join(", ");
}
