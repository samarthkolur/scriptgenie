import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { SupabaseClient, User } from "@supabase/supabase-js";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";

/**
 * A Supabase client for Server Components, Route Handlers and Server Actions.
 *
 * Not memoised, unlike the browser client: each request carries its own
 * cookies, and a shared instance would serve one user's session to the next
 * request that arrived.
 *
 * The `setAll` swallow is deliberate and is the pattern Supabase documents.
 * Server Components cannot write cookies — Next.js has already begun streaming
 * the response by the time one would be set — so a refresh attempted from a
 * component has nowhere to store its result. `proxy.ts` refreshes the session
 * on every request precisely so this path never needs to.
 */
export async function serverClient(): Promise<SupabaseClient> {
  const store = await cookies();

  return createServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: {
      getAll() {
        return store.getAll();
      },
      setAll(toSet) {
        try {
          for (const { name, value, options } of toSet) {
            store.set(name, value, options);
          }
        } catch {
          // Called from a Server Component, where cookies are read-only.
          // Middleware owns the refresh, so nothing is lost by ignoring it.
        }
      },
    },
  });
}

/**
 * The signed-in user, or `null`.
 *
 * Always `getUser()` and never `getSession()`. `getSession()` returns whatever
 * the cookie claims, and a cookie is client-supplied data; `getUser()` asks
 * Supabase to verify the token before answering. Anything that gates access on
 * an unverified session is gating on something the user can edit.
 */
export async function currentUser(): Promise<User | null> {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}

/**
 * The verified access token to present to the API, or `null`.
 *
 * The session is only read *after* `getUser()` has verified it, so the token
 * handed onward is one Supabase has already confirmed rather than one a cookie
 * asserted.
 */
export async function accessToken(): Promise<string | null> {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user === null) return null;

  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}
