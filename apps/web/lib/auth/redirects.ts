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
