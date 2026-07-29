import { NextResponse, type NextRequest } from "next/server";

import { AUTH_ERROR_PARAM, type AuthErrorCode } from "@/lib/auth/errors";
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
 * *Failures travel as codes, never as prose.* The provider's own
 * `error_description` is free text from outside our trust boundary, and
 * forwarding it would let a crafted link put an arbitrary sentence on our
 * sign-in page, above a real Google button. `lib/auth/errors.ts` owns the
 * wording; this route only decides which of its cases applies.
 *
 * *The exchange failure is distinguished from the absence of a code.* An
 * expired or replayed code is a different problem from a request that was
 * never part of a sign-in, and they need different messages.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const next = safeReturnPath(searchParams.get("next"));

  // Google sends `error=access_denied` when the user declines the consent
  // screen; anything else from the provider is a failure on its side. Either
  // way the description it offers is not repeated back to the user.
  const providerError = searchParams.get("error");
  if (providerError !== null) {
    return NextResponse.redirect(
      signInWithError(
        origin,
        providerError === "access_denied" ? "access_denied" : "provider_error",
      ),
    );
  }

  const code = searchParams.get("code");
  if (code === null) {
    return NextResponse.redirect(signInWithError(origin, "incomplete"));
  }

  const supabase = await serverClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error !== null) {
    return NextResponse.redirect(signInWithError(origin, "expired"));
  }

  return NextResponse.redirect(new URL(next, origin));
}

function signInWithError(origin: string, code: AuthErrorCode): URL {
  const url = new URL("/sign-in", origin);
  url.searchParams.set(AUTH_ERROR_PARAM, code);
  return url;
}
