import { TerminalIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * The local sign-in shortcut, rendered only when `lib/auth/dev-login.ts` says
 * the route exists.
 *
 * A plain form posting to a route handler, with no `"use client"` and no
 * JavaScript of its own. The shortcut has to work on the first paint of a cold
 * dev server, which is exactly when a hydration error would stop a button that
 * needed to be interactive first.
 *
 * The wording says "development only" on the control itself rather than in a
 * comment. Anyone who ever sees this outside their own machine is looking at a
 * misconfiguration, and the control should be the thing that tells them.
 */
export function DevSignIn() {
  return (
    <form method="post" action="/auth/dev-login" className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-border" />
        <span className="font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
          Development only
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <Button type="submit" variant="secondary" className="w-full">
        <TerminalIcon className="size-4" aria-hidden="true" />
        Sign in as the local test account
      </Button>

      <p className="text-xs text-muted-foreground">
        Signs in as a real Supabase user with a password, so the API still
        verifies the token and row level security still applies. This button
        does not exist in a production build.
      </p>
    </form>
  );
}
