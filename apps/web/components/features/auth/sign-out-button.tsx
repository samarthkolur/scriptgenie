"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { browserClient } from "@/lib/supabase/client";

type Props = {
  readonly className?: string;
};

/**
 * Signs the user out everywhere the browser can reach.
 *
 * `scope: "global"` revokes the refresh token server-side rather than only
 * clearing local storage. Without it, "sign out" on a shared machine leaves a
 * refresh token that other tabs — and anyone who reopens the browser — can
 * still exchange for a fresh session.
 *
 * `router.refresh()` after signing out is not optional. Server Components are
 * cached per navigation, so without it the page keeps rendering the signed-in
 * shell until something else triggers a re-fetch, and the user is told they are
 * still signed in when they are not.
 */
export function SignOutButton({ className }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    await browserClient().auth.signOut({ scope: "global" });
    router.replace("/");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={signOut}
      disabled={busy}
      className={
        className ??
        "rounded-md px-3 py-1.5 text-sm text-neutral-600 transition hover:bg-neutral-100 hover:text-neutral-900 disabled:opacity-60 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
      }
    >
      {busy ? "Signing out…" : "Sign out"}
    </button>
  );
}
