const LAYERS = [
  {
    name: "Conflict detection",
    detail:
      "Deterministic rules over a curated knowledge base identify which of your constraints are in tension, and why, before anything is generated.",
  },
  {
    name: "Scope parameterisation",
    detail:
      "Your budget tier becomes hard numeric bounds — location count, speaking cast, VFX ceiling, period setting — and your rating becomes content thresholds.",
  },
  {
    name: "Variant generation",
    detail:
      "Each variant is assigned a different narrative archetype before generation, so the variants differ structurally rather than cosmetically.",
  },
] as const;

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-10 px-6 py-16">
      <header className="space-y-4">
        <p className="font-mono text-xs uppercase tracking-widest text-neutral-500">
          Constraint-Aware Script Ideation Engine
        </p>
        <h1 className="text-4xl font-semibold tracking-tight">ScriptGenie</h1>
        <p className="text-lg text-neutral-600 dark:text-neutral-400">
          Plot variants that are producible, not merely plausible. Genre,
          audience rating, production budget and territory censorship are
          enforced as constraints — not suggested as prompt text.
        </p>
      </header>

      <ol className="space-y-6">
        {LAYERS.map((layer, index) => (
          <li key={layer.name} className="flex gap-4">
            <span className="font-mono text-sm tabular-nums text-neutral-400">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="space-y-1">
              <h2 className="font-medium">{layer.name}</h2>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                {layer.detail}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <footer className="border-t border-neutral-200 pt-6 text-sm text-neutral-500 dark:border-neutral-800">
        A pre-development ideation tool. It produces beat-level plot concepts,
        not screenplays.
      </footer>
    </main>
  );
}
