import { describe, expect, it } from "vitest";

import type { ConflictReport, ResolveResponse } from "@/lib/api-client";
import { describeScope } from "@/lib/constraints/scope-preview";
import {
  SEVERITY_COPY,
  SEVERITY_ORDER,
  bySeverity,
  generationGate,
  settlesConflict,
  summarise,
  unacknowledgedSoft,
  unsettledHard,
} from "@/lib/constraints/severity";
import {
  describeDeltas,
  levelWord,
  thresholdRows,
} from "@/lib/constraints/thresholds";

type Conflict = ConflictReport["conflicts"][number];

/** A conflict shaped like the detector's, with only the fields under test set. */
function conflict(overrides: Partial<Conflict> & Pick<Conflict, "rule_id">) {
  return {
    severity: "HARD",
    title: "A tension",
    explanation: "Two constraints pull against each other.",
    resolutions: [],
    evidence: {},
    ...overrides,
  } as Conflict;
}

const CLAMP = {
  id: "clamp_to_rating",
  label: "Hold the content at what the certificate allows",
  description: "Lower the ceiling to the permitted level.",
  effect: { kind: "clamp_dimension_to_permitted", dimension: "violence" },
} as Conflict["resolutions"][number];

const ACKNOWLEDGE = {
  id: "acknowledge_separate_cut",
  label: "Cut a separate version for that market",
  description: "Accept that a second, trimmed cut will be made.",
} as Conflict["resolutions"][number];

const REVISE = {
  id: "raise_the_certificate",
  label: "Aim at a higher certificate",
  description: "Go back and change the rating you are targeting.",
  effect: { kind: "requires_bundle_change" },
} as Conflict["resolutions"][number];

describe("settlesConflict", () => {
  it("treats a clamp as settling the conflict", () => {
    expect(settlesConflict(CLAMP)).toBe(true);
  });

  it("treats an option with no declared effect as an acknowledgement", () => {
    // The engine reads a missing effect the same way — see `resolution._delta`.
    expect(settlesConflict(ACKNOWLEDGE)).toBe(true);
  });

  it("does not treat an intent to revise as settling anything", () => {
    // `requires_bundle_change` is the writer saying they will change an
    // answer. Until they do, the conflict stands, and the engine's
    // `_is_cleared` says exactly this.
    expect(settlesConflict(REVISE)).toBe(false);
  });
});

describe("generationGate", () => {
  const hard = conflict({
    rule_id: "horror_exceeds_pg13",
    severity: "HARD",
    title: "Horror intensity exceeds PG-13",
    resolutions: [CLAMP, REVISE],
  });
  const soft = conflict({
    rule_id: "hybrid_tone_pressure",
    severity: "SOFT",
    title: "Horror-comedy pulls in two directions",
    resolutions: [ACKNOWLEDGE],
  });
  const advisory = conflict({
    rule_id: "micro_budget_locations",
    severity: "ADVISORY",
    title: "Location count is ambitious for this tier",
  });

  it("blocks while a HARD conflict has no resolution chosen", () => {
    const gate = generationGate([hard], [], new Set());
    expect(gate.allowed).toBe(false);
    expect(gate.allowed === false && gate.reason).toContain(
      "Horror intensity exceeds PG-13",
    );
  });

  it("stays blocked when the chosen resolution only promises a revision", () => {
    const gate = generationGate(
      [hard],
      [{ rule_id: hard.rule_id, resolution_id: REVISE.id }],
      new Set(),
    );
    expect(gate.allowed).toBe(false);
  });

  it("opens once a settling resolution is chosen for every HARD conflict", () => {
    const gate = generationGate(
      [hard],
      [{ rule_id: hard.rule_id, resolution_id: CLAMP.id }],
      new Set(),
    );
    expect(gate).toEqual({ allowed: true });
  });

  it("ignores a choice naming a resolution the conflict does not offer", () => {
    // The API rejects this outright. The client must not let it look settled
    // in the meantime, or the button would enable on a request bound to 409.
    const gate = generationGate(
      [hard],
      [{ rule_id: hard.rule_id, resolution_id: "invented" }],
      new Set(),
    );
    expect(gate.allowed).toBe(false);
  });

  it("counts rather than names when several conflicts block", () => {
    const other = conflict({ rule_id: "second", severity: "HARD" });
    const gate = generationGate([hard, other], [], new Set());
    expect(gate.allowed === false && gate.reason).toContain("2 conflicts");
  });

  it("blocks on an unacknowledged SOFT conflict even with no HARD ones", () => {
    const gate = generationGate([soft], [], new Set());
    expect(gate.allowed).toBe(false);
    expect(gate.allowed === false && gate.reason).toContain("Acknowledge");
  });

  it("opens once the SOFT conflict is acknowledged", () => {
    expect(generationGate([soft], [], new Set([soft.rule_id]))).toEqual({
      allowed: true,
    });
  });

  it("reports HARD before SOFT when both are outstanding", () => {
    // A writer told to acknowledge something while a blocking conflict stands
    // would acknowledge it and find the button still disabled.
    const gate = generationGate([hard, soft], [], new Set());
    expect(gate.allowed === false && gate.reason).toContain("blocked");
  });

  it("never blocks on an advisory, acknowledged or not", () => {
    expect(generationGate([advisory], [], new Set())).toEqual({
      allowed: true,
    });
  });

  it("allows generation when there are no conflicts at all", () => {
    expect(generationGate([], [], new Set())).toEqual({ allowed: true });
  });

  it("selects the outstanding conflicts it reports on", () => {
    expect(unsettledHard([hard, soft], [])).toEqual([hard]);
    expect(unacknowledgedSoft([hard, soft], new Set())).toEqual([soft]);
    expect(unacknowledgedSoft([soft], new Set([soft.rule_id]))).toEqual([]);
  });
});

describe("summarise", () => {
  it("says so plainly when nothing conflicts", () => {
    expect(summarise([])).toBe("No conflicts in these constraints.");
  });

  it("counts each severity in blocking-first order", () => {
    const conflicts = [
      conflict({ rule_id: "a", severity: "ADVISORY" }),
      conflict({ rule_id: "b", severity: "HARD" }),
      conflict({ rule_id: "c", severity: "SOFT" }),
    ];
    const summary = summarise(conflicts);
    expect(summary.indexOf("blocking")).toBeLessThan(
      summary.indexOf("decision"),
    );
    expect(summary.indexOf("decision")).toBeLessThan(
      summary.indexOf("knowing"),
    );
  });

  it("omits severities that did not fire", () => {
    expect(summarise([conflict({ rule_id: "a", severity: "HARD" })])).toBe(
      "1 blocking",
    );
  });
});

describe("severity copy", () => {
  it("covers every severity the API can send", () => {
    // A severity with no copy would render an empty badge, which conveys the
    // conflict's weight by colour alone.
    for (const severity of SEVERITY_ORDER) {
      expect(SEVERITY_COPY[severity].label).not.toBe("");
      expect(SEVERITY_COPY[severity].announcement).not.toBe("");
    }
  });

  it("groups by severity without reordering within a group", () => {
    const first = conflict({ rule_id: "first", severity: "HARD" });
    const second = conflict({ rule_id: "second", severity: "HARD" });
    // The API sorts by severity then rule id; the panel must not resort.
    expect(bySeverity([first, second], "HARD")).toEqual([first, second]);
  });
});

describe("describeScope", () => {
  it("reads a tier's scope and an envelope's the same way", () => {
    const scope = {
      max_locations: 5,
      max_named_characters: 1,
      vfx_complexity: "practical_only",
      period_setting: "contemporary_only",
      action_complexity: "dialogue_driven",
      narrative_economy: "high",
    };
    expect(describeScope(scope)).toEqual([
      "up to 5 locations",
      "up to 1 speaking part",
      "practical effects only",
      "present day only",
      "dialogue-driven",
      "every scene must earn its place",
    ]);
  });

  it("reads a null bound as unlimited rather than dropping it", () => {
    // The studio tier stores `null` rather than an invented ceiling, and
    // omitting the line would read as "this tier does not constrain locations
    // enough to mention".
    expect(describeScope({ max_locations: null })[0]).toBe(
      "unlimited locations",
    );
  });
});

describe("thresholdRows", () => {
  const envelope = {
    thresholds: {
      violence: 2,
      sexual_content: 1,
      language: 2,
      thematic_darkness: 3,
      drug_use: 0,
      horror_intensity: 2,
    },
    provenance: [
      {
        dimension: "violence",
        level: 2,
        authority: "MPA PG-13",
        detail: "Intense sequences permitted without lingering on injury.",
      },
    ],
    scope: {},
    genre: { primary: "horror" },
    budget_tier_id: "micro",
    directives: [],
    guidance: [],
  } as unknown as ResolveResponse["envelope"];

  it("names the authority behind a ceiling that has one", () => {
    const violence = thresholdRows(envelope).find(
      (row) => row.dimension === "violence",
    );
    expect(violence?.word).toBe("moderate");
    expect(violence?.authority).toBe("MPA PG-13");
  });

  it("leaves an unexplained ceiling unattributed rather than borrowing one", () => {
    const language = thresholdRows(envelope).find(
      (row) => row.dimension === "language",
    );
    expect(language?.authority).toBeNull();
  });

  it("returns every dimension, including the ones set to none", () => {
    const rows = thresholdRows(envelope);
    expect(rows).toHaveLength(6);
    expect(rows.find((row) => row.dimension === "drug_use")?.word).toBe("none");
  });

  it("falls back to the number if the scale ever grows past explicit", () => {
    expect(levelWord(4)).toBe("explicit");
    expect(levelWord(9)).toBe("level 9");
  });
});

describe("describeDeltas", () => {
  it("names the movement a clamp made", () => {
    const [line] = describeDeltas([
      {
        rule_id: "horror_exceeds_pg13",
        resolution_id: "clamp_to_rating",
        effect_kind: "clamp_dimension_to_permitted",
        dimension: "horror_intensity",
        from_level: 4,
        to_level: 2,
      },
    ] as ResolveResponse["deltas"]);
    expect(line).toBe("Horror intensity held at moderate, down from explicit.");
  });

  it("does not claim an acknowledgement moved a bound", () => {
    const [line] = describeDeltas([
      {
        rule_id: "territory_restriction",
        resolution_id: "acknowledge_separate_cut",
        effect_kind: "acknowledge_relaxation",
      },
    ] as ResolveResponse["deltas"]);
    expect(line).toContain("no bound moved");
  });

  it("says a revision is still owed rather than reporting a change", () => {
    const [line] = describeDeltas([
      {
        rule_id: "audience_contradiction",
        resolution_id: "raise_the_certificate",
        effect_kind: "requires_bundle_change",
      },
    ] as ResolveResponse["deltas"]);
    expect(line).toContain("revise an answer");
  });
});
