import Link from "next/link";

import { AppNav } from "@/components/features/shell/app-nav";
import { ThemeToggle } from "@/components/features/shell/theme-toggle";
import { UserMenu } from "@/components/features/shell/user-menu";
import { Separator } from "@/components/ui/separator";

type Props = {
  readonly displayName: string;
  readonly email: string | null;
  readonly avatarUrl: string | null;
};

/**
 * The signed-in header.
 *
 * A Server Component holding two client islands (the nav needs the current
 * path, the menus need state). Everything else — the wordmark, the layout, the
 * separator — ships as markup with no JavaScript attached.
 */
export function AppHeader({ displayName, email, avatarUrl }: Props) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-6 py-3">
        <Link
          href="/app"
          className="rounded-sm font-mono text-xs tracking-widest uppercase transition-colors hover:text-foreground/70 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          ScriptGenie
        </Link>

        <Separator orientation="vertical" className="hidden h-5 sm:block" />

        <AppNav className="hidden sm:flex" />

        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <UserMenu
            displayName={displayName}
            email={email}
            avatarUrl={avatarUrl}
          />
        </div>
      </div>

      {/* Below the small breakpoint the nav moves to its own row rather than
          collapsing into a menu. There are two destinations; hiding two links
          behind a button costs a tap and saves nothing. */}
      <div className="border-t px-6 py-2 sm:hidden">
        <AppNav />
      </div>
    </header>
  );
}
