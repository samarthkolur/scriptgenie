import { AlertCircleIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { SignInWithGoogle } from "@/components/features/auth/sign-in-with-google";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AUTH_ERROR_PARAM, authErrorMessage } from "@/lib/auth/errors";
import { DEFAULT_SIGNED_IN_PATH, safeReturnPath } from "@/lib/auth/redirects";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to ScriptGenie with your Google account.",
};

type Props = {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SignInPage({ searchParams }: Props) {
  const params = await searchParams;
  const next = safeReturnPath(first(params.next));
  // The URL carries a code; the wording is ours. See `lib/auth/errors.ts`.
  const error = authErrorMessage(first(params[AUTH_ERROR_PARAM]));

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-6 px-6 py-16">
      <Link
        href="/"
        className="rounded-sm font-mono text-xs tracking-widest text-muted-foreground uppercase transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        ScriptGenie
      </Link>

      {error !== null && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Sign-in did not complete</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Sign in</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Your projects, constraint bundles and generated variants are private
            to your account.
          </p>

          <SignInWithGoogle
            {...(next !== DEFAULT_SIGNED_IN_PATH ? { returnTo: next } : {})}
          />

          <p className="text-xs text-muted-foreground">
            ScriptGenie reads only your name, email address and profile picture
            from Google, and uses them to identify your account. Nothing is
            posted on your behalf.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

/**
 * Next.js gives a repeated query parameter as an array. Taking the first is the
 * conservative reading: `?next=/app&next=https://evil.example` must not resolve
 * to the attacker's value, and `safeReturnPath` would reject it anyway.
 */
function first(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}
