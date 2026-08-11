import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GenerationResults } from "@/components/features/variants/generation-results";
import type { GenerationResponse, KbOptions, Variant } from "@/lib/api-client";

const OPTIONS = {
  archetypes: [
    {
      id: "heist_caper",
      label: "Heist Caper",
      description: "",
      min_beats: 5,
    },
  ],
} as unknown as KbOptions;

const VARIANT: Variant = {
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
} as unknown as Variant;

const RUN = {
  id: "00000000-0000-0000-0000-000000000002",
  project_id: "00000000-0000-0000-0000-000000000003",
  kb_version: "0.1.1",
  prompt_version: "1.0.0",
  model: "openai/gpt-oss-120b",
  seed: 0,
  status: "completed",
  requested_count: 1,
  generated_count: 1,
  failed_count: 0,
  created_at: "2026-08-11T00:00:00Z",
  completed_at: "2026-08-11T00:00:01Z",
  elapsed_ms: 1000,
} as unknown as GenerationResponse["run"];

describe("GenerationResults", () => {
  it("renders nothing before a run has been asked for", () => {
    const { container } = render(
      <GenerationResults
        state={{ kind: "idle" }}
        options={OPTIONS}
        onRetry={vi.fn()}
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("shows a skeleton for each variant requested while a run is in flight", () => {
    render(
      <GenerationResults
        state={{ kind: "running", requested: 3 }}
        options={OPTIONS}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("Generating 3 variants…")).toBeTruthy();
  });

  it("explains a race with the gate rather than showing a generic error", () => {
    render(
      <GenerationResults
        state={{ kind: "blocked" }}
        options={OPTIONS}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText(/blocked again/)).toBeTruthy();
  });

  it("names the wait on a rate limit", () => {
    render(
      <GenerationResults
        state={{ kind: "rate_limited", retryAfterSeconds: 42 }}
        options={OPTIONS}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText(/42s/)).toBeTruthy();
  });

  it("renders every successful variant with its archetype label", () => {
    render(
      <GenerationResults
        state={{
          kind: "done",
          run: RUN,
          envelope: {} as GenerationResponse["envelope"],
          variants: [VARIANT],
          failures: [],
          retrying: null,
          retryError: null,
        }}
        options={OPTIONS}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("1 variant generated")).toBeTruthy();
    expect(screen.getByText("Heist Caper")).toBeTruthy();
    expect(screen.getByText("The Last Vault")).toBeTruthy();
  });

  it("shows a failed slot with its reason and a working retry action", () => {
    const onRetry = vi.fn();
    render(
      <GenerationResults
        state={{
          kind: "done",
          run: RUN,
          envelope: {} as GenerationResponse["envelope"],
          variants: [],
          failures: [
            {
              archetype_id: "heist_caper",
              variant_index: 0,
              reason: "the model returned unusable output twice",
              error_type: "unusable_output",
            },
          ],
          retrying: null,
          retryError: null,
        }}
        options={OPTIONS}
        onRetry={onRetry}
      />,
    );

    expect(
      screen.getByText("the model returned unusable output twice"),
    ).toBeTruthy();

    screen.getByRole("button", { name: "Generate a replacement" }).click();
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows the retry's own failure beside the slot it was for", () => {
    render(
      <GenerationResults
        state={{
          kind: "done",
          run: RUN,
          envelope: {} as GenerationResponse["envelope"],
          variants: [],
          failures: [
            {
              archetype_id: "heist_caper",
              variant_index: 0,
              reason: "the model returned unusable output twice",
              error_type: "unusable_output",
            },
          ],
          retrying: null,
          retryError: {
            archetypeId: "heist_caper",
            message: "You have reached the generation limit for now.",
          },
        }}
        options={OPTIONS}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByText("You have reached the generation limit for now."),
    ).toBeTruthy();
  });
});
