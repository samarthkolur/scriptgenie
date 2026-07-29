"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/** The destinations that exist today. Phase 6 adds the project surfaces. */
export const NAV_ITEMS = [
  { href: "/app", label: "Projects", exact: true },
  { href: "/app/account", label: "Account", exact: false },
] as const;

/**
 * Whether a nav item should be marked as the current page.
 *
 * Exported and pure so the rule is testable without a router. `/app` needs an
 * exact match — every route in the app is nested under it, so a prefix test
 * would light up "Projects" on every page including Account.
 */
export function isActive(
  pathname: string,
  href: string,
  exact: boolean,
): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppNav({ className }: { readonly className?: string }) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className={cn("flex items-center gap-1", className)}
    >
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href, item.exact);
        return (
          <Link
            key={item.href}
            href={item.href}
            // The accessible signal for "you are here". Colour alone would
            // convey it to sighted users only, and this is the one piece of
            // state in the header that orients someone.
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              active
                ? "bg-muted font-medium text-foreground"
                : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
