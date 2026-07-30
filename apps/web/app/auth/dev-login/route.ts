import { NextResponse, type NextRequest } from "next/server";

import { AUTH_ERROR_PARAM } from "@/lib/auth/errors";
import { devLoginCredentials } from "@/lib/auth/dev-login";
import { ensureDemoProject } from "@/lib/auth/dev-seed";
import { DEFAULT_SIGNED_IN_PATH } from "@/lib/auth/redirects";
import { serverClient } from "@/lib/supabase/server";

/**
 * The local sign-in shortcut. See `lib/auth/dev-login.ts` for what gates it.
 *
 * `POST` rather than `GET`, so the shortcut cannot be triggered by a link, an
 * image tag or a prefetch — a route that signs someone in on navigation is one
 * a stray `<img src>` can fire.
 *
 * The destination is the constant `DEFAULT_SIGNED_IN_PATH` and is not taken
 * from the request. `/auth/callback` accepts a `next` because Google's round
 * trip has to carry the user's original destination across it; nothing carries
 * anything across this one, so accepting a destination here would add an open
 * redirect to buy nothing.
 */
export async function POST(request: NextRequest) {
  const credentials = devLoginCredentials();
  if (credentials === null) {
    // 404, not 403. A route that answers "forbidden" has confirmed it exists,
    // and in every deployed build the honest answer is that it does not.
    return new NextResponse(null, { status: 404 });
  }

  const { origin } = request.nextUrl;
  const supabase = await serverClient();
  const { data, error } = await supabase.auth.signInWithPassword(credentials);

  if (error !== null || data.session === null) {
    const url = new URL("/sign-in", origin);
    url.searchParams.set(AUTH_ERROR_PARAM, "dev_login_failed");
    return NextResponse.redirect(url, 303);
  }

  // The token from the response rather than one read back out of the cookie
  // jar: the cookies were only just written on this very request, and reading
  // them back to prove it would be testing Next.js rather than signing in.
  await ensureDemoProject(data.session.access_token);

  // 303 turns the browser's follow-up into a GET. A 307 would replay the POST
  // against the destination.
  return NextResponse.redirect(new URL(DEFAULT_SIGNED_IN_PATH, origin), 303);
}
