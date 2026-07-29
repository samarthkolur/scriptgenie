"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const OPTIONS = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
  { value: "system", label: "System", Icon: MonitorIcon },
] as const;

/** Never changes after mount, so the subscribe callback has nothing to do. */
const noopSubscribe = () => () => {};

/**
 * `false` while server-rendering, `true` once hydrated.
 *
 * `useSyncExternalStore` rather than the usual `useState` + `useEffect` pair.
 * It is the API built for exactly this — a value that legitimately differs
 * between the server and client snapshots — so React is told about the
 * difference instead of being corrected after the fact by a state update in an
 * effect, which schedules a second render and which `react-hooks` now flags.
 */
function useHasMounted(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

/**
 * Light / dark / system, as a menu rather than a two-state switch.
 *
 * "System" has to be reachable. A toggle that flips between light and dark
 * gives no way back to following the OS once it has been touched, and someone
 * who switches their machine to dark at sunset then finds this app alone
 * staying light.
 *
 * The mount guard is not cosmetic. The theme is only known on the client —
 * the server cannot read `prefers-color-scheme` or `localStorage` — so
 * rendering the resolved icon during SSR would emit markup that hydration
 * contradicts. Until mount it renders the same neutral icon on both sides.
 */
export function ThemeToggle({ className }: { readonly className?: string }) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const mounted = useHasMounted();

  const ActiveIcon = !mounted
    ? MonitorIcon
    : resolvedTheme === "dark"
      ? MoonIcon
      : SunIcon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={className}
          // Always announces the control, never the current value: the value
          // is only known after mount, and a label that changes on hydration
          // is read twice by a screen reader.
          aria-label="Change colour theme"
        >
          <ActiveIcon className="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {OPTIONS.map(({ value, label, Icon }) => (
          <DropdownMenuItem
            key={value}
            onSelect={() => setTheme(value)}
            // Communicates the selection to assistive technology rather than
            // by the tick alone, which is visual only.
            aria-current={mounted && theme === value ? "true" : undefined}
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
            {mounted && theme === value && (
              <span className="ml-auto text-xs text-muted-foreground">
                Active
              </span>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
