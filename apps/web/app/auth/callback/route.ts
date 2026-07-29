import { NextResponse, type NextRequest } from "next/server";

import { safeReturnPath } from "@/lib/auth/redirects";
import { serverClient } from "@/lib/supabase/server";

/**
 * Where Google returns the user after they approve the sign-in.
 *
 * Supabase's PKCE flow hands back a one-time `code`; exchanging it for a
 * session is what sets the auth cookies, and until that happens the user is
 * not signed in no matter what the URL suggests.
 *
 * Three things are deliberate:
 *
 * *The destination is filtered.* `next` arrives in the URL and is therefore
 * attacker-controlled. `safeReturnPath` reduces it to a same-origin path, so
 * this route cannot be used to bounce a freshly-authenticated user to another
 * site. See `lib/auth/redirects.ts`.
 *
 * *Errors from the provider are surfaced, not swallowed.* A user who declines
 * the Google consent screen arrives here with `error=access_denied` and no
 * code. Redirecting them to the sign-in page with the reason beats a blank
 * screen or a generic failure.
 *
 * *The exchange failure is distinguished from the absence of a code.* An
 * expired or replayed code is a different problem from a request that was
 * never part of a sign-in, and they need different messages.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const next = safeReturnPath(searchParams.get("next"));

  const providerError =
    searchParams.get("error_description") ?? searchParams.get("error");
  if (providerError !== null) {
    return NextResponse.redirect(signInWithError(origin, providerError));
  }

  const code = searchParams.get("code");
  if (code === null) {
    return NextResponse.redirect(
      signInWithError(
        origin,
        "This sign-in link is incomplete. Please start again.",
      ),
    );
  }

  const supabase = await serverClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error !== null) {
    return NextResponse.redirect(
      signInWithError(
        origin,
        "This sign-in link has expired or was already used.",
      ),
    );
  }

  return NextResponse.redirect(new URL(next, origin));
}

function signInWithError(origin: string, reason: string): URL {
  const url = new URL("/sign-in", origin);
  url.searchParams.set("error", reason);
  return url;
}
