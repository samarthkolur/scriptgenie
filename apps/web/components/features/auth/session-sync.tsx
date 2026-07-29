"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { browserClient } from "@/lib/supabase/client";

type Props = {
  /** The user the server rendered this tree for, or `null` if nobody. */
  readonly userId: string | null;
};

/**
 * Whether the server's view of who is signed in has gone stale.
 *
 * Deliberately compares identity rather than switching on the Supabase event
 * name. The events are not a reliable guide to whether the rendered page is
 * now wrong: `TOKEN_REFRESHED` fires roughly hourly and changes nothing the
 * server rendered, while `INITIAL_SESSION` can arrive on a restored tab whose
 * markup was rendered for a user who has since signed out elsewhere. What
 * actually matters is whether the person the HTML was built for is still the
 * person holding the session.
 *
 * Exported and pure so the rule can be tested without a router or a Supabase
 * client, the same way `isActive` and `safeReturnPath` are.
 */
export function shouldResync(
  serverUserId: string | null,
  browserUserId: string | null,
): boolean {
  return serverUserId !== browserUserId;
}

/**
 * Keeps server-rendered markup honest about who is signed in.
 *
 * Server Components render once per navigation and are then cached, so a
 * session that ends *after* a page was rendered leaves that page asserting a
 * signed-in user indefinitely. That is the "sign-out clears it everywhere"
 * problem: signing out in one tab revokes the refresh token globally, but
 * every other open tab keeps showing the account menu until something happens
 * to re-fetch. `router.refresh()` re-runs the Server Components against the
 * current cookies, and `app/app/layout.tsx` redirects when it finds nobody.
 *
 * Renders nothing. It exists for the subscription.
 */
export function SessionSync({ userId }: Props) {
  const router = useRouter();
  const serverUserId = useRef(userId);
  const handled = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    // The server has just re-rendered with this identity, so whatever mismatch
    // we may have acted on is answered, and the next one is worth acting on.
    serverUserId.current = userId;
    handled.current = undefined;
  }, [userId]);

  useEffect(() => {
    const { data } = browserClient().auth.onAuthStateChange(
      (_event, session) => {
        const browserUserId = session?.user.id ?? null;
        if (!shouldResync(serverUserId.current, browserUserId)) return;

        // Refresh at most once per observed identity. If the server disagrees
        // with the browser and keeps disagreeing — a cookie the server still
        // accepts, say — refreshing on every event would spin the page.
        if (handled.current === browserUserId) return;
        handled.current = browserUserId;

        router.refresh();
      },
    );

    return () => {
      data.subscription.unsubscribe();
    };
  }, [router]);

  return null;
}
