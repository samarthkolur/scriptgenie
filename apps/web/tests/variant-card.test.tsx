import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VariantCard } from "@/components/features/variants/variant-card";
import type { Variant } from "@/lib/api-client";

function variant(overrides: Partial<Variant> = {}): Variant {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    variant_index: 0,
    archetype_id: "heist_caper",
    title: "The Last Vault",
    logline: "A crew of misfits plan one final job.",
    beats: [
      { index: 0, function: "Setup", summary: "The crew is assembled." },
      { index: 1, function: "Inciting incident", summary: "The job appears." },
      { index: 2, function: "Midpoint", summary: "The plan changes." },
      { index: 3, function: "Crisis", summary: "Everything falls apart." },
      {
        index: 4,
        function: "Resolution",
        summary: "They pull it off, barely.",
      },
    ],
    locations: ["Vault", "Safehouse"],
    named_characters: ["Ren", "Marlowe"],
    relaxations: [],
    satisfaction: {
      dimension_checks: [
        { dimension: "violence", observed: 1, permitted: 2, satisfied: true },
      ],
      scope_checks: [
        { parameter: "max_locations", observed: 2, limit: 4, satisfied: true },
      ],
      satisfied: true,
      violations: [],
    },
    verdicts: { violence: "PASS", max_locations: "PASS" },
    surfaceable: true,
    favourite: false,
    notes: null,
    provenance: {
      kb_version: "0.1.1",
      prompt_version: "1.0.0",
      model: "openai/gpt-oss-120b",
      archetype_id: "heist_caper",
      seed: 0,
      attempts: 1,
      repaired: false,
    },
    created_at: "2026-08-11T00:00:00Z",
    ...overrides,
  } as Variant;
}

describe("VariantCard", () => {
  it("renders the archetype, title, beats and a verified badge", () => {
    render(<VariantCard variant={variant()} archetypeLabel="Heist Caper" />);

    expect(screen.getByText("Heist Caper")).toBeTruthy();
    expect(screen.getByText("The Last Vault")).toBeTruthy();
    expect(screen.getByText("Verified for scope")).toBeTruthy();
    expect(screen.getByText(/The crew is assembled/)).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("shows the constraint satisfaction report with observed and permitted values", () => {
    render(<VariantCard variant={variant()} archetypeLabel="Heist Caper" />);

    // Scoped to the satisfaction report itself: "Locations" also names the
    // unrelated list of named locations further down the card.
    const report = screen
      .getByText("Constraint satisfaction")
      .closest("div") as HTMLElement;
    expect(within(report).getByText("Violence")).toBeTruthy();
    expect(within(report).getByText("1 / 2")).toBeTruthy();
    expect(within(report).getByText("Locations")).toBeTruthy();
    expect(within(report).getByText("2 / 4")).toBeTruthy();
  });

  it("flags a failed axis and names the exact parameter exceeded", () => {
    render(
      <VariantCard
        variant={variant({
          verdicts: { violence: "FLAGGED" },
          satisfaction: {
            dimension_checks: [
              {
                dimension: "violence",
                observed: 3,
                permitted: 2,
                satisfied: false,
              },
            ],
            scope_checks: [],
            satisfied: false,
            violations: ["violence"],
          },
        })}
        archetypeLabel="Heist Caper"
      />,
    );

    expect(screen.getByText("Flagged")).toBeTruthy();
    expect(screen.getByText(/exceeds/)).toBeTruthy();
    expect(screen.getByText("Exceeds: Violence")).toBeTruthy();
  });

  it("shows a needs-review badge without claiming a pass or a fail", () => {
    render(
      <VariantCard
        variant={variant({ verdicts: { violence: "NEEDS_REVIEW" } })}
        archetypeLabel="Heist Caper"
      />,
    );

    expect(screen.getByText("Needs review")).toBeTruthy();
  });

  it("lists relaxed genre conventions when the model reports any", () => {
    render(
      <VariantCard
        variant={variant({
          relaxations: ["Set aside the genre's expected third-act twist."],
        })}
        archetypeLabel="Heist Caper"
      />,
    );

    expect(
      screen.getByText("Set aside the genre's expected third-act twist."),
    ).toBeTruthy();
  });

  it("never claims regulatory certification", () => {
    render(<VariantCard variant={variant()} archetypeLabel="Heist Caper" />);

    expect(screen.queryByText(/certified/i)).toBeNull();
    expect(screen.queryByText(/compliant/i)).toBeNull();
  });
});
