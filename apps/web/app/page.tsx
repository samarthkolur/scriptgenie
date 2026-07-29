import { InfoIcon } from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

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
        <p className="font-mono text-xs tracking-widest text-muted-foreground uppercase">
          Constraint-Aware Script Ideation Engine
        </p>
        <h1 className="text-4xl font-semibold tracking-tight">ScriptGenie</h1>
        <p className="text-lg text-muted-foreground">
          Plot variants that are producible, not merely plausible. Genre,
          audience rating, production budget and territory censorship are
          enforced as constraints — not suggested as prompt text.
        </p>
      </header>

      <div>
        <Button asChild size="lg">
          <Link href="/sign-in">Continue with Google</Link>
        </Button>
      </div>

      <ol className="space-y-6">
        {LAYERS.map((layer, index) => (
          <li key={layer.name} className="flex gap-4">
            <span className="font-mono text-sm text-muted-foreground tabular-nums">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="space-y-1">
              <h2 className="font-medium">{layer.name}</h2>
              <p className="text-sm text-muted-foreground">{layer.detail}</p>
            </div>
          </li>
        ))}
      </ol>

      {/* The scope statement is a callout rather than a footnote deliberately.
          The research risk here is a reader assuming this drafts scripts and
          judging the output as a failed screenplay; saying so once, quietly,
          at the bottom of the page is how that assumption survives.

          `AlertTitle` renders a div, not a heading, which keeps the three
          layer names above as the page's only second-level headings. */}
      <Alert>
        <InfoIcon />
        <AlertTitle>What this is, and what it is not</AlertTitle>
        <AlertDescription>
          ScriptGenie is a pre-development ideation tool. It produces beat-level
          plot concepts, not screenplays — no dialogue, no scene text, no
          formatted pages. The output is a starting point for a writers&rsquo;
          room, and every variant carries the constraints it was held to so you
          can check the reasoning rather than trust it.
        </AlertDescription>
      </Alert>
    </main>
  );
}
