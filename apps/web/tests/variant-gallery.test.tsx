import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VariantGallery } from "@/components/features/variants/variant-gallery";
import type { KbOptions, Variant } from "@/lib/api-client";

const OPTIONS = {
  archetypes: [
    {
      id: "heist_caper",
      label: "Heist Caper",
      description: "",
      min_beats: 5,
    },
    {
      id: "crucible",
      label: "Crucible",
      description: "",
      min_beats: 5,
    },
  ],
} as unknown as KbOptions;

function variant(overrides: Partial<Variant> = {}): Variant {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    variant_index: 0,
    archetype_id: "heist_caper",
    title: "The Last Vault",
    logline: "A crew of misfits plan one final job.",
    beats: [{ index: 0, function: "Setup", summary: "The crew is assembled." }],
    locations: [],
    named_characters: [],
    relaxations: [],
    satisfaction: {
      dimension_checks: [],
      scope_checks: [],
      satisfied: true,
      violations: [],
    },
    verdicts: {},
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

describe("VariantGallery", () => {
  it("shows a real empty state before anything has been generated", () => {
    render(
      <VariantGallery
        variants={[]}
        options={OPTIONS}
        onToggleFavourite={vi.fn()}
        onNotesChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/Nothing generated yet/)).toBeTruthy();
  });

  it("filters by title, logline and archetype label", () => {
    render(
      <VariantGallery
        variants={[
          variant(),
          variant({
            id: "00000000-0000-0000-0000-000000000002",
            archetype_id: "crucible",
            title: "The Cabin",
            logline: "Five friends cannot leave.",
          }),
        ]}
        options={OPTIONS}
        onToggleFavourite={vi.fn()}
        onNotesChange={vi.fn()}
      />,
    );

    expect(screen.getByText("The Last Vault")).toBeTruthy();
    expect(screen.getByText("The Cabin")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Search variants"), {
      target: { value: "cabin" },
    });

    expect(screen.queryByText("The Last Vault")).toBeNull();
    expect(screen.getByText("The Cabin")).toBeTruthy();
  });

  it("toggles favourite through the callback rather than local-only state", () => {
    const onToggleFavourite = vi.fn();
    render(
      <VariantGallery
        variants={[variant()]}
        options={OPTIONS}
        onToggleFavourite={onToggleFavourite}
        onNotesChange={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Mark The Last Vault a favourite" }),
    );

    expect(onToggleFavourite).toHaveBeenCalledWith(variant());
  });

  it("saves a note when the field loses focus, but not before", () => {
    const onNotesChange = vi.fn();
    render(
      <VariantGallery
        variants={[variant()]}
        options={OPTIONS}
        onToggleFavourite={vi.fn()}
        onNotesChange={onNotesChange}
      />,
    );

    const field = screen.getByLabelText("Notes");
    fireEvent.change(field, { target: { value: "Strong opening beat." } });
    expect(onNotesChange).not.toHaveBeenCalled();

    fireEvent.blur(field);
    expect(onNotesChange).toHaveBeenCalledWith(
      variant(),
      "Strong opening beat.",
    );
  });

  it("clears a note to null rather than an empty string", () => {
    const onNotesChange = vi.fn();
    render(
      <VariantGallery
        variants={[variant({ notes: "Old note." })]}
        options={OPTIONS}
        onToggleFavourite={vi.fn()}
        onNotesChange={onNotesChange}
      />,
    );

    const field = screen.getByLabelText("Notes");
    fireEvent.change(field, { target: { value: "  " } });
    fireEvent.blur(field);

    expect(onNotesChange).toHaveBeenCalledWith(
      variant({ notes: "Old note." }),
      null,
    );
  });

  it("only allows comparing between two and five variants", () => {
    const variants = [
      variant({ id: "1" }),
      variant({ id: "2", title: "B" }),
      variant({ id: "3", title: "C" }),
    ];
    render(
      <VariantGallery
        variants={variants}
        options={OPTIONS}
        onToggleFavourite={vi.fn()}
        onNotesChange={vi.fn()}
      />,
    );

    const compareButton = screen.getByRole("button", { name: /^Compare/ });
    expect((compareButton as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getAllByRole("checkbox", { name: "Compare" })[0]!);
    expect((compareButton as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getAllByRole("checkbox", { name: "Compare" })[1]!);
    expect((compareButton as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(compareButton);
    expect(screen.getByText("Comparing 2 variants")).toBeTruthy();
  });
});
