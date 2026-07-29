import type { Metadata } from "next";
import Link from "next/link";

import { SignInWithGoogle } from "@/components/features/auth/sign-in-with-google";
import { safeReturnPath, DEFAULT_SIGNED_IN_PATH } from "@/lib/auth/redirects";

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
  const error = first(params.error);

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 px-6 py-16">
      <header className="space-y-3">
        <Link
          href="/"
          className="font-mono text-xs tracking-widest text-neutral-500 uppercase hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          ScriptGenie
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Your projects, constraint bundles and generated variants are private
          to your account.
        </p>
      </header>

      {error !== undefined && (
        <p
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
        >
          {error}
        </p>
      )}

      <SignInWithGoogle
        {...(next !== DEFAULT_SIGNED_IN_PATH ? { returnTo: next } : {})}
      />

      <p className="text-xs text-neutral-500">
        ScriptGenie reads only your name, email address and profile picture from
        Google, and uses them to identify your account. Nothing is posted on
        your behalf.
      </p>
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
