import { redirect } from "next/navigation";

import { SessionSync } from "@/components/features/auth/session-sync";
import { AppHeader } from "@/components/features/shell/app-header";
import { currentUser } from "@/lib/supabase/server";
import { avatarUrlFrom, displayNameFrom } from "@/lib/user-display";

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

  return (
    <div className="flex min-h-full flex-1 flex-col">
      {/* Renders nothing. It re-runs this layout when the session ends in
          another tab, at which point the redirect above takes effect. */}
      <SessionSync userId={user.id} />
      <AppHeader
        displayName={displayNameFrom(user)}
        email={user.email ?? null}
        avatarUrl={avatarUrlFrom(user)}
      />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        {children}
      </main>
    </div>
  );
}
