import type { Metadata } from "next";

import { ErrorState } from "@/components/features/shell/error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getProfile, type Profile } from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";

export const metadata: Metadata = { title: "Account" };

/**
 * The account page, and the end-to-end proof that auth works.
 *
 * It does not read the profile from the Supabase session, which would only
 * show that a cookie exists. It calls the API, which verifies the access token
 * against the project's JWKS and then reads the row under that same token, so
 * the database's row level security decides what comes back. A profile
 * rendered here means every link in that chain agrees on who you are.
 */
export default async function AccountPage() {
  let profile: Profile;
  try {
    profile = await getProfile();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    // A failure here is not a broken page — it is a specific, explainable
    // outcome (a lapsed session, an unmigrated database), so it is rendered
    // rather than thrown into the error boundary.
    return (
      <ErrorState
        title="Your account could not be loaded"
        description={error.problem.detail}
        digest={error.problem.requestId}
      />
    );
  }

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Your account</h1>
        <p className="text-sm text-muted-foreground">
          Your browser session, the API&rsquo;s token verification and the
          database&rsquo;s row level security all agree on who you are.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-[10rem_1fr]">
            <Row label="Name" value={profile.display_name ?? "Not provided"} />
            <Row label="Email" value={profile.email} />
            <Row label="Member since" value={formatDate(profile.created_at)} />
          </dl>
        </CardContent>
      </Card>
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
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm break-words">{value}</dd>
    </>
  );
}

function formatDate(value: string): string {
  // `en-GB` and UTC are fixed rather than left to the runtime's locale: a date
  // formatted on the server with one locale and re-rendered on the client with
  // another is a hydration mismatch, and it is one that only appears for users
  // whose machine disagrees with the server.
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(value));
}
