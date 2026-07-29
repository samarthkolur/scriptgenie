"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";

let cached: SupabaseClient | undefined;

/**
 * The browser's Supabase client.
 *
 * Memoised because `createBrowserClient` attaches an auth state listener and a
 * token refresh timer. A second instance would refresh the same session on its
 * own schedule, and the two would race to write the session cookie — the
 * classic cause of a user being signed out at random.
 */
export function browserClient(): SupabaseClient {
  cached ??= createBrowserClient(supabaseUrl(), supabaseAnonKey());
  return cached;
}
