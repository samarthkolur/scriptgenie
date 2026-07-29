import type { Metadata } from "next";

import { apiFetch } from "@/lib/api/server";
import { ApiError } from "@/lib/api/problem";

export const metadata: Metadata = {
  title: "Your account",
};

type Profile = {
  readonly id: string;
  readonly email: string;
  readonly display_name: string | null;
  readonly avatar_url: string | null;
  readonly created_at: string;
};

/**
 * The first signed-in page, and the end-to-end proof of the auth stage.
 *
 * It does not read the profile from the Supabase session, which would only
 * show that a cookie exists. It calls the API, which verifies the access
 * token, and the API reads the row under that same token so the database's
 * row level security decides what comes back. A profile rendered here means
 * every link in that chain worked.
 */
export default async function AppHomePage() {
  let profile: Profile | null = null;
  let failure: string | null = null;

  try {
    profile = await apiFetch<Profile>("/v1/me");
  } catch (error) {
    if (error instanceof ApiError) {
      failure = error.problem.detail;
    } else {
      throw error;
    }
  }

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Your account</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Confirmed end to end: your browser session, the API&rsquo;s token
          verification and the database&rsquo;s row level security all agree on
          who you are.
        </p>
      </header>

      {failure !== null ? (
        <p
          role="alert"
          className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          {failure}
        </p>
      ) : (
        <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-[max-content_1fr]">
          <Row label="Name" value={profile?.display_name ?? "Not provided"} />
          <Row label="Email" value={profile?.email ?? ""} />
          <Row label="Member since" value={formatDate(profile?.created_at)} />
        </dl>
      )}
    </div>
  );
}

function Row({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}) {
  return (
    <>
      <dt className="text-sm text-neutral-500">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </>
  );
}

function formatDate(value: string | undefined): string {
  if (value === undefined) return "";
  // `en-GB` fixed rather than left to the server's locale: a server-rendered
  // date formatted with the machine's locale differs from the same date
  // re-rendered on the client, which React reports as a hydration mismatch.
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(value));
}
