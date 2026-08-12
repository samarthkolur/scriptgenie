import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConflictPanel } from "@/components/features/constraints/conflict-panel";
import type { ConflictReport } from "@/lib/api-client";

type Conflict = ConflictReport["conflicts"][number];

const CLAMP = {
  id: "clamp_to_rating",
  label: "Hold the content at what the certificate allows",
  description: "Lower the ceiling to the permitted level.",
  effect: {
    kind: "clamp_dimension_to_permitted",
    dimension: "horror_intensity",
  },
} as Conflict["resolutions"][number];

const REVISE = {
  id: "raise_the_certificate",
  label: "Aim at a higher certificate",
  description: "Go back and change the rating you are targeting.",
  effect: { kind: "requires_bundle_change" },
} as Conflict["resolutions"][number];

const HARD = {
  rule_id: "horror_exceeds_pg13",
  severity: "HARD",
  title: "Horror intensity exceeds PG-13",
  explanation: "Horror at explicit intensity cannot hold a PG-13 certificate.",
  hard_rationale: "No cut satisfies both the genre convention and the board.",
  resolutions: [CLAMP, REVISE],
  evidence: {
    left: "4",
    right: "2",
    dimension: "horror_intensity",
    territory: "us",
  },
} as Conflict;

const SOFT = {
  rule_id: "hybrid_tone_pressure",
  severity: "SOFT",
  title: "Horror-comedy pulls in two directions",
  explanation: "Tonal whiplash is the usual failure of this pairing.",
  resolutions: [],
  evidence: {},
} as Conflict;

const ADVISORY = {
  rule_id: "micro_budget_locations",
  severity: "ADVISORY",
  title: "Location count is ambitious for this tier",
  explanation: "Micro-budget schedules rarely absorb this many moves.",
  resolutions: [],
  evidence: {},
} as Conflict;

function report(conflicts: readonly Conflict[]): ConflictReport {
  return {
    blocking: conflicts.some((conflict) => conflict.severity === "HARD"),
    bundle: {} as ConflictReport["bundle"],
    conflicts: [...conflicts],
    counts: { hard: 0, soft: 0, advisory: 0 },
    kb_version: "0.1.1",
    rules_evaluated: 27,
  };
}

function renderPanel(
  conflicts: readonly Conflict[],
  overrides: Partial<Parameters<typeof ConflictPanel>[0]> = {},
) {
  const props = {
    state: {
      report: report(conflicts),
      judgedAt: new Date("2026-07-30T14:32:00Z"),
      pending: false,
      error: null,
      stale: false,
    },
    choices: [],
    onChoose: vi.fn(),
    acknowledged: new Set<string>(),
    onAcknowledge: vi.fn(),
    flagged: new Set<string>(),
    onFlag: vi.fn(),
    ...overrides,
  };
  render(<ConflictPanel {...props} />);
  return props;
}

describe("ConflictPanel", () => {
  it("announces severity in words, not only in colour", () => {
    // The criterion this covers: a screen-reader user must be told a conflict
    // blocks generation. Both the badge label and the sentence beside it are
    // text, so neither depends on the destructive palette being perceived.
    renderPanel([HARD]);
    const card = screen.getByRole("article", {
      name: "Horror intensity exceeds PG-13",
    });
    expect(card.textContent).toContain("Blocking");
    expect(card.textContent).toContain("Blocking conflict");
  });

  it("gives each severity its own heading and consequence", () => {
    renderPanel([HARD, SOFT, ADVISORY]);
    expect(
      screen.getByRole("heading", {
        name: "Has to be settled before you can generate",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Needs your acknowledgement" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Worth knowing" })).toBeTruthy();
  });

  it("puts blocking conflicts above the ones that can wait", () => {
    renderPanel([ADVISORY, SOFT, HARD]);
    const headings = screen
      .getAllByRole("heading", { level: 3 })
      .map((heading) => heading.textContent);
    expect(headings).toEqual([
      "Has to be settled before you can generate",
      "Needs your acknowledgement",
      "Worth knowing",
    ]);
  });

  it("names both sides of the tension, not just the verdict", () => {
    renderPanel([HARD]);
    const card = screen.getByRole("article", {
      name: "Horror intensity exceeds PG-13",
    });
    expect(within(card).getByText("Your constraints ask for")).toBeTruthy();
    expect(within(card).getByText("What is permitted")).toBeTruthy();
    expect(within(card).getByText("horror intensity")).toBeTruthy();
  });

  it("warns that an option promising a revision does not settle anything", () => {
    renderPanel([HARD]);
    const option = screen.getByRole("radio", {
      name: /Aim at a higher certificate/,
    });
    expect(option.textContent).toContain("leaves the conflict standing");
  });

  it("reports a chosen resolution up rather than deciding locally", async () => {
    // The panel does not apply resolutions. The API re-runs detection to prove
    // one took, and the workspace is what holds the choices it sends.
    const props = renderPanel([HARD]);
    fireEvent.click(screen.getByRole("radio", { name: /Hold the content/ }));
    expect(props.onChoose).toHaveBeenCalledWith(
      "horror_exceeds_pg13",
      "clamp_to_rating",
    );
  });

  it("marks the chosen resolution as checked", () => {
    renderPanel([HARD], {
      choices: [
        { rule_id: "horror_exceeds_pg13", resolution_id: "clamp_to_rating" },
      ],
    });
    expect(
      screen
        .getByRole("radio", { name: /Hold the content/ })
        .getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("offers an acknowledgement checkbox on SOFT conflicts only", async () => {
    const props = renderPanel([HARD, SOFT, ADVISORY]);
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(1);

    fireEvent.click(boxes[0] as HTMLElement);
    expect(props.onAcknowledge).toHaveBeenCalledWith(
      "hybrid_tone_pressure",
      true,
    );
  });

  it("lets an advisory be dismissed and nothing else", async () => {
    renderPanel([HARD, SOFT, ADVISORY]);
    const dismiss = screen.getAllByRole("button", { name: /^Dismiss/ });
    expect(dismiss).toHaveLength(1);

    fireEvent.click(dismiss[0] as HTMLElement);
    expect(
      screen.queryByRole("article", {
        name: "Location count is ambitious for this tier",
      }),
    ).toBeNull();
    // Dismissing one advisory must not take the group's other members with it.
    expect(
      screen.getByRole("article", { name: "Horror intensity exceeds PG-13" }),
    ).toBeTruthy();
  });

  it("records a false-positive report against the rule id", async () => {
    const props = renderPanel([HARD]);
    fireEvent.click(
      screen.getByRole("button", { name: /This conflict is wrong/ }),
    );
    expect(props.onFlag).toHaveBeenCalledWith("horror_exceeds_pg13");
  });

  it("says where a flagged rule goes, rather than implying it was sent", async () => {
    renderPanel([HARD], { flagged: new Set(["horror_exceeds_pg13"]) });
    expect(
      screen.getByText(/filed alongside your next generation/),
    ).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: /Flagged as wrong/ })
        .hasAttribute("disabled"),
    ).toBe(true);
  });

  it("names the knowledge base and the moment behind the verdict", () => {
    renderPanel([HARD]);
    expect(screen.getByText(/knowledge base 0\.1\.1/)).toBeTruthy();
    expect(screen.getByText(/27 rules/)).toBeTruthy();
    expect(
      screen.getByText(/A later version may reach a different verdict/),
    ).toBeTruthy();
  });

  it("says the answers have moved on rather than showing a stale verdict as current", () => {
    // The old report stays on screen — emptying the panel would read as "no
    // conflicts" — but it must not be presented as a judgement of what is
    // currently typed.
    renderPanel([HARD], {
      state: {
        report: report([HARD]),
        judgedAt: new Date(),
        pending: true,
        error: null,
        stale: true,
      },
    });
    expect(
      screen.getByText(/answers have changed since the last check/),
    ).toBeTruthy();
    expect(screen.getByText("Rechecking…")).toBeTruthy();
  });

  it("distinguishes no conflicts from no answer yet", () => {
    renderPanel([]);
    expect(screen.getByText(/Nothing in these constraints/)).toBeTruthy();
  });

  it("surfaces a failed check as an alert instead of an all-clear", () => {
    render(
      <ConflictPanel
        state={{
          report: null,
          judgedAt: null,
          pending: false,
          error: "The constraints could not be checked just now.",
          stale: true,
        }}
        choices={[]}
        onChoose={vi.fn()}
        acknowledged={new Set()}
        onAcknowledge={vi.fn()}
        flagged={new Set()}
        onFlag={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "could not be checked",
    );
    expect(screen.queryByText(/Nothing in these constraints/)).toBeNull();
  });
});
