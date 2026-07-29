/**
 * Turning a Supabase user into something a header can render.
 *
 * The shape of `user_metadata` is decided by the identity provider, not by us.
 * Google returns `full_name` and `avatar_url`; other providers return `name`,
 * or `picture`, or nothing at all. None of it is guaranteed, and all of it is
 * `unknown` as far as TypeScript is concerned — so every read is narrowed
 * rather than asserted.
 *
 * The rule throughout is that there is always *something* to render. A header
 * that falls back to an empty string produces an invisible menu trigger, and a
 * missing avatar must degrade to initials rather than a broken image.
 */

/** The subset of a Supabase user this module reads. */
export type UserLike = {
  readonly email?: string | null;
  readonly user_metadata?: Record<string, unknown> | null;
};

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== ""
    ? value.trim()
    : undefined;
}

/**
 * The best available name, in the order the providers actually populate.
 *
 * The email local part is preferred over the whole address: a header is not
 * the place to publish someone's email to whoever is looking at their screen.
 */
export function displayNameFrom(user: UserLike | null | undefined): string {
  if (user === null || user === undefined) return "Your account";
  const metadata = user.user_metadata ?? {};

  return (
    text(metadata.full_name) ??
    text(metadata.name) ??
    text(user.email)?.split("@")[0] ??
    "Your account"
  );
}

/** The provider's picture, if it gave a usable one. */
export function avatarUrlFrom(
  user: UserLike | null | undefined,
): string | null {
  if (user === null || user === undefined) return null;
  const metadata = user.user_metadata ?? {};
  const url = text(metadata.avatar_url) ?? text(metadata.picture);
  if (url === undefined) return null;

  // Only ever an https image URL. `user_metadata` is provider-controlled and
  // ends up in a `src`, so a `javascript:` or `data:` value here would be an
  // injection vector rather than a broken picture.
  return url.startsWith("https://") ? url : null;
}

/**
 * One or two initials for the avatar fallback.
 *
 * Uses `Array.from` rather than indexing, so a name beginning with an emoji or
 * a non-BMP character yields that character instead of half of its surrogate
 * pair.
 */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";

  const firstPart = parts[0] ?? "";
  const lastPart = parts.length > 1 ? (parts[parts.length - 1] ?? "") : "";
  const first = Array.from(firstPart)[0] ?? "";
  const last = parts.length > 1 ? (Array.from(lastPart)[0] ?? "") : "";

  return (first + last).toUpperCase() || "?";
}
