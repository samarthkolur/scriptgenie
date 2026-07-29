/**
 * The failures the sign-in page is allowed to describe, and why the set is
 * closed.
 *
 * Everything the sign-in page knows about a failed attempt arrives in the
 * query string, which is attacker-controlled. Rendering that text is safe from
 * script injection — React escapes it — but it is not safe from the user, who
 * has no way to tell our words from an attacker's. A link to
 * `…/sign-in?error=Your+account+is+locked.+Call+1-900-…` produces that sentence
 * on the real product, on the real domain, above a real Google button.
 *
 * So the URL carries a *code* and this module owns the prose. An unrecognised
 * code gets the generic message rather than being echoed, which means a code we
 * have never seen degrades to something honest instead of becoming a channel
 * for arbitrary text.
 *
 * `access_denied` is Google's own code for "the user pressed Cancel"; the rest
 * are ours, set by `app/auth/callback/route.ts`.
 */

export const AUTH_ERROR_CODES = [
  "access_denied",
  "incomplete",
  "expired",
  "provider_error",
] as const;

export type AuthErrorCode = (typeof AUTH_ERROR_CODES)[number];

/** The query parameter carrying the failure code back to the sign-in page. */
export const AUTH_ERROR_PARAM = "error";

const MESSAGES: Record<AuthErrorCode, string> = {
  access_denied:
    "Sign-in was cancelled before Google confirmed your account. You can try again.",
  incomplete:
    "That sign-in link was incomplete, so there was nothing to confirm. Please start again.",
  expired:
    "That sign-in link has expired or was already used. Sign-in links work once, and only for a few minutes.",
  provider_error:
    "Google could not confirm your account just now. This is usually temporary.",
};

const GENERIC =
  "Sign-in could not be completed. Please try again, and if it keeps happening, try again in a few minutes.";

function isKnown(code: string): code is AuthErrorCode {
  return (AUTH_ERROR_CODES as readonly string[]).includes(code);
}

/**
 * The message for a failure code, or `null` when there was no failure.
 *
 * `null` rather than an empty string so the caller branches on presence rather
 * than on truthiness, which keeps "no error" distinct from "an error we chose
 * not to describe".
 */
export function authErrorMessage(
  code: string | null | undefined,
): string | null {
  if (typeof code !== "string" || code === "") return null;
  return isKnown(code) ? MESSAGES[code] : GENERIC;
}
