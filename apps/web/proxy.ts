import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { signInPathFor } from "@/lib/auth/redirects";
import { supabaseAnonKey, supabaseUrl } from "@/lib/env";

/** Route prefixes that require a signed-in user. */
const PROTECTED_PREFIXES = ["/app"] as const;

/**
 * Refreshes the Supabase session on every request, and guards `/app`.
 *
 * Next.js 16 renamed this convention from `middleware.ts` to `proxy.ts`; the
 * old name still works and warns on every build. The behaviour is unchanged.
 *
 * Two jobs, and the refresh is the one that is easy to skip and impossible to
 * do anywhere else. Server Components cannot write cookies, so a token that
 * expires mid-visit can only be renewed here. Without this a user
 * is signed out roughly one hour after signing in, at whatever moment they
 * happen to be doing something.
 *
 * The cookie handling below looks redundant and is not. `createServerClient`
 * may rotate the session while answering `getUser()`, and the new cookies have
 * to land on *both* the request (so anything later in this pass sees them) and
 * the response (so the browser keeps them). Building the response before the
 * call and mutating it after is what makes that possible.
 */
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(toSet) {
        for (const { name, value } of toSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of toSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // `getUser()` rather than `getSession()`: the session cookie is
  // client-supplied, and a guard that trusts it is a guard that can be
  // forged by editing a cookie. This call verifies the token with Supabase.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname, search } = request.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );

  if (isProtected && user === null) {
    const signIn = request.nextUrl.clone();
    const target = signInPathFor(`${pathname}${search}`);
    signIn.search = "";
    const [path, query] = target.split("?");
    signIn.pathname = path ?? "/sign-in";
    if (query !== undefined) signIn.search = `?${query}`;
    return NextResponse.redirect(signIn);
  }

  // A signed-in user has no business on the sign-in page, and leaving them
  // there produces a screen whose only button starts an OAuth round trip that
  // returns them to the same screen.
  if (pathname === "/sign-in" && user !== null) {
    const home = request.nextUrl.clone();
    home.pathname = "/app";
    home.search = "";
    return NextResponse.redirect(home);
  }

  return response;
}

export const config = {
  /**
   * Everything except static assets and the image optimiser. The session
   * refresh has to run on ordinary page requests; running it on every icon
   * would add a Supabase round trip to each one.
   */
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
