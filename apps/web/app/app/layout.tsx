import Link from "next/link";
import { redirect } from "next/navigation";

import { SignOutButton } from "@/components/features/auth/sign-out-button";
import { currentUser } from "@/lib/supabase/server";

/**
 * The signed-in shell.
 *
 * `proxy.ts` already redirects an unauthenticated visitor away from `/app/*`,
 * and this checks again. That is not belt-and-braces for its own sake: the
 * proxy runs on the edge and is bypassed for any route excluded from its
 * matcher, and matchers get edited. A layout that renders user data should
 * establish for itself that there is a user.
 */
export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const user = await currentUser();
  if (user === null) redirect("/sign-in");

  const metadata = user.user_metadata as Record<string, unknown>;
  const displayName =
    stringOrUndefined(metadata.full_name) ??
    stringOrUndefined(metadata.name) ??
    user.email ??
    "Your account";

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <Link
            href="/app"
            className="font-mono text-xs tracking-widest text-neutral-500 uppercase hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            ScriptGenie
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm text-neutral-600 dark:text-neutral-400">
              {displayName}
            </span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
        {children}
      </main>
    </div>
  );
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}
