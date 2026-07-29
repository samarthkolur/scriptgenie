import type { KbOptions } from "@/lib/api-client";

/**
 * A budget tier's scope, in the words a producer would use.
 *
 * The knowledge base stores these as identifiers — `dialogue_driven`,
 * `any_with_allocation` — which are precise and unreadable. The build plan
 * asks for a plain-English scope preview on the tier picker specifically so
 * the writer is choosing between consequences rather than between price bands
 * they then have to translate themselves.
 *
 * Anything unmapped falls back to the identifier with its underscores removed
 * rather than being dropped. A tier that gained a scope parameter should read
 * slightly awkwardly, not silently understate what it constrains.
 */

type Tier = KbOptions["budget_tiers"][number];

const VFX: Record<string, string> = {
  none: "no effects work",
  practical_only: "practical effects only",
  limited_digital: "some digital effects",
  unrestricted: "any effects work",
};

const PERIOD: Record<string, string> = {
  contemporary_only: "present day only",
  contemporary_or_recent: "present day or recent past",
  any_with_allocation: "any period, if budgeted for",
  any: "any period",
};

const ACTION: Record<string, string> = {
  dialogue_driven: "dialogue-driven",
  limited_practical: "small practical action",
  moderate_set_pieces: "moderate set pieces",
  unrestricted: "any action",
};

const ECONOMY: Record<string, string> = {
  high: "every scene must earn its place",
  moderate: "scenes should work hard",
  standard: "conventional scene economy",
  relaxed: "room to breathe",
};

function humanise(value: unknown): string {
  return typeof value === "string" ? value.replaceAll("_", " ") : String(value);
}

function lookup(table: Record<string, string>, value: unknown): string {
  if (typeof value !== "string") return humanise(value);
  return table[value] ?? humanise(value);
}

function countPhrase(value: unknown, singular: string, plural: string): string {
  if (value === null || value === undefined) return `unlimited ${plural}`;
  return `up to ${String(value)} ${value === 1 ? singular : plural}`;
}

/** Short phrases describing what this tier permits, in reading order. */
export function scopePhrases(tier: Tier): readonly string[] {
  const scope = tier.scope as Record<string, unknown>;
  return [
    countPhrase(scope.max_locations, "location", "locations"),
    countPhrase(scope.max_named_characters, "speaking part", "speaking parts"),
    lookup(VFX, scope.vfx_complexity),
    lookup(PERIOD, scope.period_setting),
    lookup(ACTION, scope.action_complexity),
    lookup(ECONOMY, scope.narrative_economy),
  ];
}

/** The tier's dollar band, or an open-ended one for the top tier. */
export function budgetBand(tier: Tier): string {
  const money = (value: number) =>
    value >= 1_000_000
      ? `$${(value / 1_000_000).toFixed(value % 1_000_000 === 0 ? 0 : 1)}M`
      : `$${(value / 1000).toFixed(0)}k`;

  if (tier.max_usd === null) return `${money(tier.min_usd)} and above`;
  return `${money(tier.min_usd)} – ${money(tier.max_usd)}`;
}
