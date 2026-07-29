"use client";

import { useState } from "react";

import { browserClient } from "@/lib/supabase/client";

type Props = {
  /** Where to land after signing in. Filtered server-side by the callback. */
  readonly returnTo?: string;
  readonly className?: string;
};

/**
 * The Google sign-in button.
 *
 * `redirectTo` points at `/auth/callback`, not at the destination page: the
 * PKCE code has to be exchanged for a session by a route handler before any
 * page can see a signed-in user, and the intended destination rides along as a
 * query parameter for the callback to validate.
 *
 * The busy state matters more than it looks. The OAuth round trip leaves the
 * page, and between the click and the navigation there is a window in which
 * nothing appears to happen; without feedback users click again, which starts
 * a second flow and can invalidate the first one's code.
 */
export function SignInWithGoogle({ returnTo, className }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn() {
    setBusy(true);
    setError(null);
    const callback = new URL("/auth/callback", window.location.origin);
    if (returnTo !== undefined) callback.searchParams.set("next", returnTo);

    const { error: failure } = await browserClient().auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: callback.toString(),
        // Google returns a refresh token only when explicitly asked, and only
        // on the first consent. Without it the session cannot outlive its
        // first hour.
        queryParams: { access_type: "offline", prompt: "consent" },
      },
    });

    if (failure !== null) {
      setBusy(false);
      setError(
        "Sign-in could not be started. Check your connection and try again.",
      );
    }
    // On success the browser navigates to Google; `busy` stays true so the
    // button cannot be pressed again while that is in flight.
  }

  return (
    <div className={className}>
      <button
        type="button"
        onClick={signIn}
        disabled={busy}
        className="inline-flex w-full items-center justify-center gap-3 rounded-md border border-neutral-300 bg-white px-4 py-2.5 text-sm font-medium text-neutral-900 transition hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:hover:bg-neutral-800"
      >
        <GoogleMark />
        {busy ? "Redirecting to Google…" : "Continue with Google"}
      </button>
      {error !== null && (
        <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}

/** Google's mark, inline so the button renders before any network request. */
function GoogleMark() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 18 18">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}
