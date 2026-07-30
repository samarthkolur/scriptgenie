import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  GenerateGate,
  ProjectWorkspace,
} from "@/components/features/constraints/project-workspace";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DETECT_DEBOUNCE_MS } from "@/hooks/use-conflict-report";
import type {
  ConflictReport,
  KbOptions,
  ResolveResponse,
} from "@/lib/api-client";
import { DEFAULT_FORM_VALUES } from "@/lib/constraints/schema";

/**
 * The two server actions the panels reach for.
 *
 * Mocked at the module boundary rather than at `fetch`, because a Server
 * Action cannot run in jsdom at all — what is under test here is the wiring
 * between the wizard, the gate and the two panels, and the API's own
 * behaviour is covered by the 621 tests on the other side of it.
 */
const actions = vi.hoisted(() => ({
  detect: vi.fn(),
  resolve: vi.fn(),
  save: vi.fn(),
}));

vi.mock("@/app/app/projects/[projectId]/actions", () => ({
  detectConflictsAction: actions.detect,
  resolveConflictsAction: actions.resolve,
  saveDraftAction: actions.save,
}));

const OPTIONS: KbOptions = {
  kb_version: "0.1.1",
  genres: [
    { id: "drama", label: "Drama", hybrid_friendly: [] },
    { id: "horror", label: "Horror", hybrid_friendly: ["comedy"] },
  ],
  budget_tiers: [
    {
      id: "mid_indie",
      label: "Mid independent",
      order: 2,
      min_usd: 2000000,
      max_usd: 20000000,
      guild_context: "SAG-AFTRA Modified Low",
      scope: {
        max_locations: 12,
        max_named_characters: 9,
        vfx_complexity: "limited_digital",
        period_setting: "contemporary_or_recent",
        action_complexity: "moderate_set_pieces",
        narrative_economy: "moderate",
      },
    },
  ],
  rating_systems: [
    {
      id: "mpa",
      label: "MPA",
      territory: "us",
      classifications: [
        { id: "pg_13", label: "PG-13", min_audience_age: 13 },
        { id: "r", label: "R", min_audience_age: 17 },
      ],
    },
  ],
  territories: [{ id: "us", label: "United States", rating_system: "mpa" }],
  archetypes: [],
} as unknown as KbOptions;

const CLAMP = {
  id: "clamp_to_rating",
  label: "Hold the content at what the certificate allows",
  description: "Lower the ceiling to the permitted level.",
  effect: {
    kind: "clamp_dimension_to_permitted",
    dimension: "horror_intensity",
  },
};

const HARD_REPORT: ConflictReport = {
  blocking: true,
  bundle: {} as ConflictReport["bundle"],
  conflicts: [
    {
      rule_id: "horror_exceeds_pg13",
      severity: "HARD",
      title: "Horror intensity exceeds PG-13",
      explanation: "Explicit horror cannot hold a PG-13 certificate.",
      resolutions: [CLAMP],
      evidence: { left: "4", right: "2", dimension: "horror_intensity" },
    },
  ],
  counts: { hard: 1, soft: 0, advisory: 0 },
  kb_version: "0.1.1",
  rules_evaluated: 27,
} as unknown as ConflictReport;

const RESOLVED: ResolveResponse = {
  kb_version: "0.1.1",
  original: {} as ResolveResponse["original"],
  bundle: {} as ResolveResponse["bundle"],
  choices: [
    { rule_id: "horror_exceeds_pg13", resolution_id: "clamp_to_rating" },
  ],
  deltas: [
    {
      rule_id: "horror_exceeds_pg13",
      resolution_id: "clamp_to_rating",
      effect_kind: "clamp_dimension_to_permitted",
      dimension: "horror_intensity",
      from_level: 4,
      to_level: 2,
    },
  ],
  envelope: {
    genre: { primary: "drama" },
    budget_tier_id: "mid_indie",
    scope: {
      max_locations: 4,
      max_named_characters: 6,
      vfx_complexity: "practical_only",
      period_setting: "contemporary_only",
      action_complexity: "dialogue_driven",
      narrative_economy: "high",
    },
    thresholds: {
      violence: 2,
      sexual_content: 1,
      language: 2,
      thematic_darkness: 2,
      drug_use: 0,
      horror_intensity: 2,
    },
    provenance: [
      { dimension: "horror_intensity", level: 2, authority: "MPA PG-13" },
    ],
    directives: [],
    guidance: [],
  },
  remaining_conflicts: [],
} as unknown as ResolveResponse;

function renderWorkspace() {
  // The real tree gets this from `components/providers.tsx`; the wizard's
  // field help is a tooltip and will not mount without it.
  render(
    <TooltipProvider>
      <ProjectWorkspace
        projectId="00000000-0000-0000-0000-000000000001"
        options={OPTIONS}
        initialValues={DEFAULT_FORM_VALUES}
        hasSavedDraft
      />
    </TooltipProvider>,
  );
}

/** Let the debounce elapse and the mocked actions settle. */
async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(DETECT_DEBOUNCE_MS + 10);
  });
}

function generateButton(): HTMLButtonElement {
  return screen.getByRole("button", {
    name: "Generate variants",
  }) as HTMLButtonElement;
}

/** Whatever the gate is currently saying, read through the button's own description. */
function gateReason(): string {
  const id = generateButton().getAttribute("aria-describedby");
  expect(id).not.toBeNull();
  return document.getElementById(id as string)?.textContent ?? "";
}

describe("ProjectWorkspace", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    actions.detect.mockResolvedValue({ ok: true, data: HARD_REPORT });
    actions.resolve.mockResolvedValue({ ok: false, blocked: true });
    actions.save.mockResolvedValue({
      ok: true,
      data: { updatedAt: "2026-07-30T00:00:00Z", cited: false },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("disables generation and says why while a HARD conflict stands", async () => {
    renderWorkspace();
    await settle();

    const button = generateButton();
    expect(button.disabled).toBe(true);

    // The explanation is tied to the button, not merely printed near it: a
    // screen-reader user told the control is unavailable is read the reason
    // with it rather than having to go looking.
    const describedBy = button.getAttribute("aria-describedby");
    expect(describedBy).not.toBeNull();
    expect(
      document.getElementById(describedBy as string)?.textContent,
    ).toContain("Horror intensity exceeds PG-13");
  });

  it("shows the tier's own ceiling while the envelope cannot be computed", async () => {
    renderWorkspace();
    await settle();

    expect(screen.getByText("Scope at this tier")).toBeTruthy();
    expect(screen.getByText("up to 12 locations")).toBeTruthy();
    expect(
      screen.getByText(/cannot be computed until the blocking conflicts/),
    ).toBeTruthy();
  });

  it("updates the scope preview the moment a resolution is selected", async () => {
    renderWorkspace();
    await settle();

    actions.resolve.mockResolvedValue({ ok: true, data: RESOLVED });
    fireEvent.click(screen.getByRole("radio", { name: /Hold the content/ }));
    await settle();

    // The tier said twelve; the envelope says four, because the certificate
    // and the resolution both bind and the parameteriser takes the strictest.
    expect(screen.getByText("Scope for generation")).toBeTruthy();
    expect(screen.getByText("up to 4 locations")).toBeTruthy();
    expect(screen.queryByText("up to 12 locations")).toBeNull();

    // And the ceiling names the board that imposed it.
    expect(screen.getByText("set by MPA PG-13")).toBeTruthy();
    expect(
      screen.getByText(/Horror intensity held at moderate, down from explicit/),
    ).toBeTruthy();
  });

  it("opens the gate once the chosen resolution settles the conflict", async () => {
    renderWorkspace();
    await settle();
    expect(gateReason()).toContain("blocked");

    fireEvent.click(screen.getByRole("radio", { name: /Hold the content/ }));
    await settle();

    expect(gateReason()).toContain("ready");
  });

  it("keeps the gate shut while the check is behind the answers", async () => {
    // Between an edit and its verdict there is no report for what is on
    // screen. Leaving the button live there would let a writer generate
    // against constraints nothing had judged.
    actions.detect.mockResolvedValue({ ok: true, data: HARD_REPORT });
    renderWorkspace();

    expect(generateButton().disabled).toBe(true);
    expect(gateReason()).toContain("Waiting on the constraint check");

    await settle();
    expect(generateButton().disabled).toBe(true);
  });

  it("drops resolutions when the answers they were about change", async () => {
    renderWorkspace();
    await settle();

    actions.resolve.mockResolvedValue({ ok: true, data: RESOLVED });
    fireEvent.click(screen.getByRole("radio", { name: /Hold the content/ }));
    await settle();
    expect(gateReason()).toContain("ready");

    // Changing an answer invalidates the report the choice was made against —
    // the API rejects a choice naming a rule that is not in the report it is
    // judging, so keeping it would guarantee a 422 on generate.
    fireEvent.click(screen.getByRole("button", { name: "Audience & rating" }));
    fireEvent.change(screen.getByLabelText("Youngest viewer"), {
      target: { value: "16" },
    });
    await settle();

    expect(gateReason()).toContain("blocked");
  });

  it("marks the draft unsaved as soon as an answer changes", async () => {
    renderWorkspace();
    await settle();
    expect(screen.getByText("Saved")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Audience & rating" }));
    fireEvent.change(screen.getByLabelText("Youngest viewer"), {
      target: { value: "16" },
    });
    await settle();

    expect(screen.getByText("Unsaved")).toBeTruthy();
  });
});

describe("GenerateGate", () => {
  it("stays disabled with no handler, and says that is why", () => {
    // Stage 6.2 ships the gate; generation is wired at 6.3. A live button with
    // nothing behind it would be the placeholder this repo forbids.
    render(<GenerateGate gate={{ allowed: true }} checking={false} />);
    const button = screen.getByRole("button", { name: "Generate variants" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(gateReason()).toContain("arrives at the next stage");
  });

  it("runs the handler only when the gate is open", () => {
    const onGenerate = vi.fn();
    const { rerender } = render(
      <GenerateGate
        gate={{ allowed: false, reason: "Generation is blocked: settle it." }}
        checking={false}
        onGenerate={onGenerate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Generate variants" }));
    expect(onGenerate).not.toHaveBeenCalled();
    expect(gateReason()).toContain("blocked");

    rerender(
      <GenerateGate
        gate={{ allowed: true }}
        checking={false}
        onGenerate={onGenerate}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate variants" }));
    expect(onGenerate).toHaveBeenCalledOnce();
    expect(
      screen
        .getByRole("button", { name: "Generate variants" })
        .getAttribute("aria-describedby"),
    ).toBeNull();
  });
});
