"use client";

import { LogOutIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { browserClient } from "@/lib/supabase/client";
import { initials } from "@/lib/user-display";

type Props = {
  readonly displayName: string;
  readonly email: string | null;
  readonly avatarUrl: string | null;
};

/**
 * The account menu in the app header.
 *
 * Signing out is the only action for now, and it is deliberately not a bare
 * button: putting it behind a menu means it cannot be hit by a mis-click on a
 * header the user was reaching past.
 */
export function UserMenu({ displayName, email, avatarUrl }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    // `scope: "global"` revokes the refresh token server-side rather than only
    // clearing local storage. Without it, "sign out" on a shared machine
    // leaves a token that reopening the browser can still exchange.
    const { error } = await browserClient().auth.signOut({ scope: "global" });

    if (error !== null) {
      setBusy(false);
      // Told, not silently left signed in. A user who believes they have
      // signed out on a shared machine and has not is the worst outcome here.
      toast.error("Could not sign out", {
        description:
          "Your session is still active. Check your connection and try again.",
      });
      return;
    }

    router.replace("/");
    // Server Components are cached per navigation, so without this the signed-in
    // shell keeps rendering until something else triggers a re-fetch.
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-2"
          aria-label={`Account menu for ${displayName}`}
        >
          <Avatar url={avatarUrl} name={displayName} />
          <span className="hidden max-w-[12rem] truncate sm:inline">
            {displayName}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate font-medium">{displayName}</span>
          {email !== null && (
            <span className="block truncate text-xs text-muted-foreground">
              {email}
            </span>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={busy} onSelect={signOut}>
          <LogOutIcon className="size-4" aria-hidden="true" />
          {busy ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * The provider's picture, or initials.
 *
 * A plain `<img>` rather than `next/image`: the host is Google's CDN and
 * varies by account, and allow-listing a remote pattern broad enough to cover
 * it would let any URL on that host be proxied through our optimiser.
 * `referrerPolicy` stops the request leaking which page the user is on.
 */
function Avatar({
  url,
  name,
}: {
  readonly url: string | null;
  readonly name: string;
}) {
  if (url === null) {
    return (
      <span
        aria-hidden="true"
        className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-[0.625rem] font-medium text-muted-foreground"
      >
        {initials(name)}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- see above
    <img
      src={url}
      alt=""
      aria-hidden="true"
      width={24}
      height={24}
      referrerPolicy="no-referrer"
      className="size-6 shrink-0 rounded-full object-cover"
    />
  );
}
