import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VariantComparison } from "@/components/features/variants/variant-comparison";
import type { KbOptions, Variant } from "@/lib/api-client";

const OPTIONS = {
  archetypes: [
    { id: "heist_caper", label: "Heist Caper", description: "", min_beats: 5 },
    { id: "crucible", label: "Crucible", description: "", min_beats: 5 },
  ],
} as unknown as KbOptions;

function variant(overrides: Partial<Variant> = {}): Variant {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    variant_index: 0,
    archetype_id: "heist_caper",
    title: "The Last Vault",
    logline: "A crew of misfits plan one final job.",
    beats: [
      { index: 0, function: "Setup", summary: "The crew is assembled." },
      { index: 1, function: "Turn", summary: "The plan changes." },
    ],
    locations: ["Vault", "Safehouse"],
    named_characters: ["Ren"],
    relaxations: [],
    satisfaction: {
      dimension_checks: [
        { dimension: "violence", observed: 1, permitted: 2, satisfied: true },
      ],
      scope_checks: [
        {
          parameter: "max_locations",
          observed: 2,
          limit: 4,
          satisfied: true,
        },
      ],
      satisfied: true,
      violations: [],
    },
    verdicts: { violence: "PASS" },
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

describe("VariantComparison", () => {
  it("compares every selected variant's structure, counts and satisfaction", () => {
    render(
      <VariantComparison
        variants={[
          variant(),
          variant({
            id: "00000000-0000-0000-0000-000000000002",
            archetype_id: "crucible",
            title: "The Cabin",
            locations: ["Cabin"],
            named_characters: ["Mara", "Deb"],
          }),
        ]}
        options={OPTIONS}
        open
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Comparing 2 variants")).toBeTruthy();
    expect(screen.getByText("The Last Vault")).toBeTruthy();
    expect(screen.getByText("The Cabin")).toBeTruthy();
    // Both fixtures share an archetype-derived min_beats, a two-beat outline
    // and the same satisfaction fixture, so these rows legitimately repeat
    // once per card.
    expect(screen.getAllByText("2 beats (min 5)")).toHaveLength(2);
    expect(screen.getAllByText(/^Violence$/)).toHaveLength(2);
    expect(screen.getAllByText("1 / 2")).toHaveLength(2);
  });

  it("renders nothing when closed", () => {
    render(
      <VariantComparison
        variants={[variant()]}
        options={OPTIONS}
        open={false}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.queryByText("The Last Vault")).toBeNull();
  });

  it("stacks one card per row at the base grid size, so mobile never needs to scroll sideways", () => {
    // Dialog content renders through a portal, so it lands on `document.body`
    // rather than inside `render`'s own container.
    render(
      <VariantComparison
        variants={[variant()]}
        options={OPTIONS}
        open
        onOpenChange={vi.fn()}
      />,
    );

    const grid = document.body.querySelector(".grid-cols-1");
    expect(grid).not.toBeNull();
    expect(grid?.className).not.toMatch(/overflow-x/);
  });
});
