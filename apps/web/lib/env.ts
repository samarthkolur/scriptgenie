/**
 * Environment variables, read once and validated at the point of use.
 *
 * Next.js inlines `NEXT_PUBLIC_*` at build time by textual substitution, so
 * `process.env[name]` does not work — the key has to appear literally in the
 * source. That is why these are written out rather than looked up in a loop,
 * and why a helper that takes a variable name would silently return undefined
 * in a production build while working perfectly in development.
 *
 * A missing value throws rather than defaulting. A Supabase client built
 * against `undefined` does not fail at construction; it fails later, on a
 * request, with an error that names neither the variable nor the file.
 */

export class MissingEnvError extends Error {
  constructor(name: string) {
    super(
      `${name} is not set. Copy apps/web/.env.example to .env.local and fill it in ` +
        `from your Supabase project's API settings.`,
    );
    this.name = "MissingEnvError";
  }
}

function required(name: string, value: string | undefined): string {
  if (value === undefined || value.trim() === "") {
    throw new MissingEnvError(name);
  }
  return value;
}

export function supabaseUrl(): string {
  return required(
    "NEXT_PUBLIC_SUPABASE_URL",
    process.env.NEXT_PUBLIC_SUPABASE_URL,
  );
}

/**
 * The anon key is public by design: it identifies the project, and every row it
 * can reach is reachable only through the row level security policies in
 * `supabase/migrations`. It is not a secret and must never be confused with the
 * service role key, which is one and never appears in this app.
 */
export function supabaseAnonKey(): string {
  return required(
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
}

export function apiBaseUrl(): string {
  return required(
    "NEXT_PUBLIC_API_BASE_URL",
    process.env.NEXT_PUBLIC_API_BASE_URL,
  );
}
