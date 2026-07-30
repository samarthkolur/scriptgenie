/**
 * The local sign-in shortcut, and the three things that keep it local.
 *
 * Driving the wizard and the conflict panel by hand needs a signed-in session,
 * and completing a Google round trip for every reload is a tax on the one kind
 * of testing that finds what the test suite cannot. This is the shortcut.
 *
 * **It is not a bypass of authentication, and could not usefully be one.**
 * Every screen worth testing is API-backed — `/v1/kb/options` fills the wizard,
 * the bundle draft survives the reload, `/conflicts/detect` fills the panel —
 * and each of those calls carries a Supabase-issued JWT that FastAPI verifies
 * against the project JWKS before Postgres applies row level security to it. A
 * forged session would render a signed-in shell in which nothing loaded. So
 * this signs in as a *real* Supabase user with a password instead: a second
 * credential path, not a hole in the first. The token is genuine, RLS applies
 * exactly as it does for a Google user, and nothing anywhere is mocked.
 *
 * Three independent conditions have to hold, and any one of them failing makes
 * the route return 404:
 *
 * 1. `NODE_ENV` is exactly `development`. `next build` and `next start` both
 *    set `production`, so no deployed build can reach this — not the Vercel
 *    app, and not a local production build either. This is a build-time
 *    constant rather than configuration, which is what makes it the condition
 *    that cannot be turned back on by editing a dashboard.
 * 2. `DEV_LOGIN_EMAIL` is set.
 * 3. `DEV_LOGIN_PASSWORD` is set.
 *
 * Neither variable is `NEXT_PUBLIC_`, so neither is inlined into the browser
 * bundle; in a Client Component both would read as `undefined`.
 */

export type DevLoginEnv = {
  readonly NODE_ENV?: string | undefined;
  readonly DEV_LOGIN_EMAIL?: string | undefined;
  readonly DEV_LOGIN_PASSWORD?: string | undefined;
};

export type DevLoginCredentials = {
  readonly email: string;
  readonly password: string;
};

/**
 * Read literally rather than through a loop.
 *
 * Next.js substitutes `process.env.X` textually, so the key has to appear in
 * the source for the value to survive the build — the same reason `lib/env.ts`
 * writes its variables out one by one.
 */
function processEnv(): DevLoginEnv {
  return {
    NODE_ENV: process.env.NODE_ENV,
    DEV_LOGIN_EMAIL: process.env.DEV_LOGIN_EMAIL,
    DEV_LOGIN_PASSWORD: process.env.DEV_LOGIN_PASSWORD,
  };
}

/**
 * The credentials to sign in with, or `null` when the shortcut does not exist.
 *
 * `null` rather than a thrown error: "this deployment has no dev login" is the
 * normal, correct state everywhere but one developer's laptop, and it is not a
 * fault to be reported.
 */
export function devLoginCredentials(
  env: DevLoginEnv = processEnv(),
): DevLoginCredentials | null {
  // Deliberately an equality test against `development`, not an inequality
  // against `production`. An unset or misspelled NODE_ENV must fail closed.
  if (env.NODE_ENV !== "development") return null;

  const email = (env.DEV_LOGIN_EMAIL ?? "").trim();
  const password = env.DEV_LOGIN_PASSWORD ?? "";
  if (email === "" || password === "") return null;

  return { email, password };
}

/** Whether to offer the shortcut on the sign-in page. */
export function isDevLoginAvailable(env: DevLoginEnv = processEnv()): boolean {
  return devLoginCredentials(env) !== null;
}
