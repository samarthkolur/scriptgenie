"use client";

import { ThemeProvider } from "next-themes";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Every client-side provider the app needs, in one place.
 *
 * Kept as a single client component so `app/layout.tsx` stays a Server
 * Component. Marking the layout `"use client"` to host a provider would drag
 * the entire tree into the client bundle, including pages that render no
 * interactive markup at all.
 *
 * `disableTransitionOnChange` matters more than it sounds: without it, every
 * element carrying a colour transition animates when the theme flips, so a
 * theme change becomes a half-second smear across the whole page rather than
 * an instant switch.
 */
export function Providers({
  children,
}: {
  readonly children: React.ReactNode;
}) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <TooltipProvider delayDuration={200}>
        {children}
        {/* Sonner renders into a portal, so its position in the tree does not
            affect layout. It is last so its toasts stack above everything. */}
        <Toaster />
      </TooltipProvider>
    </ThemeProvider>
  );
}
