/**
 * Where a user goes after signing in, and why it cannot simply be whatever the
 * URL says.
 *
 * The sign-in flow carries the page the user was trying to reach so they land
 * back on it rather than on a generic dashboard. That parameter is
 * attacker-controllable: a link to
 * `…/sign-in?next=https://evil.example/harvest` produces a real sign-in on a
 * real domain that then redirects the freshly-authenticated user off-site. This
 * is an open redirect, and it is the single most common vulnerability in a
 * "return to where you were" flow.
 *
 * The rule here is that only a same-origin *path* is ever honoured, decided by
 * inspecting the string rather than by parsing it as a URL — `URL` normalises
 * away several of the forms an attacker relies on.
 */

/** Where a signed-in user goes when nothing else is specified. */
export const DEFAULT_SIGNED_IN_PATH = "/app";

/** The query parameter carrying the intended destination through sign-in. */
export const RETURN_TO_PARAM = "next";

/**
 * `next` if it is a safe same-origin path, otherwise the default.
 *
 * Rejected, with the form each rule stops:
 *  - anything not starting with `/`      — `https://evil.example`, `evil.example`
 *  - anything starting with `//` or `/\` — protocol-relative, which browsers
 *                                          resolve to a different host
 *  - anything containing a control char  — CR/LF, which can split a header
 *  - the sign-in route itself            — a redirect loop
 */
export function safeReturnPath(next: string | null | undefined): string {
  if (typeof next !== "string" || next === "") return DEFAULT_SIGNED_IN_PATH;
  if (!next.startsWith("/")) return DEFAULT_SIGNED_IN_PATH;
  if (next.startsWith("//") || next.startsWith("/\\"))
    return DEFAULT_SIGNED_IN_PATH;
  if (/[\u0000-\u001f\u007f]/.test(next)) return DEFAULT_SIGNED_IN_PATH;
  if (next === "/sign-in" || next.startsWith("/sign-in?"))
    return DEFAULT_SIGNED_IN_PATH;
  return next;
}

/** The sign-in URL that returns the user to `from` once they are signed in. */
export function signInPathFor(from: string): string {
  const target = safeReturnPath(from);
  if (target === DEFAULT_SIGNED_IN_PATH) return "/sign-in";
  return `/sign-in?${RETURN_TO_PARAM}=${encodeURIComponent(target)}`;
}

/** Where the PKCE round trip is meant to land. */
export const AUTH_CALLBACK_PATH = "/auth/callback";

/**
 * The callback URL for an authorisation response that was delivered to the
 * landing page instead of to `/auth/callback`, or `null` when this is an
 * ordinary request.
 *
 * Supabase validates `redirect_to` against the project's **Redirect URLs**
 * allow-list, and when the value is not on it the parameter is discarded and
 * the Site URL is substituted silently — there is no error and no warning. On a
 * new project the Site URL is `http://localhost:3000` and the allow-list is
 * empty, so a correct sign-in request comes back to `/?code=…`. The landing
 * page has no idea what to do with a `code`, so the user reads a marketing page
 * while holding an unspent authorisation code and concludes sign-in is broken.
 *
 * Forwarding it grants nothing that was not already reachable. `/auth/callback`
 * is a public route that already accepts exactly these parameters from exactly
 * this source; the code is single-use, and spending it still requires the PKCE
 * verifier cookie that this origin set when the flow started. What this removes
 * is a dependency on one dashboard checkbox being right.
 *
 * Deliberately narrow — only the site root, and only when the query carries a
 * `code` or a provider `error`. Any other path with a `code` in it belongs to
 * whatever route owns that path.
 */
export function strandedAuthResponse(
  pathname: string,
  search: URLSearchParams,
): string | null {
  if (pathname !== "/") return null;
  if (!search.has("code") && !search.has("error")) return null;
  return `${AUTH_CALLBACK_PATH}?${search.toString()}`;
}
