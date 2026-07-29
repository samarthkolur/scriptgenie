"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/features/shell/error-state";

/**
 * The route-level error boundary.
 *
 * Catches anything thrown while rendering a page or its Server Components, and
 * replaces that segment rather than the whole document — the header and the
 * user menu keep working, so a failed page is a failed page rather than a
 * broken app.
 *
 * `reset()` re-renders the segment. That is genuinely useful here, because the
 * most common cause is a transient API failure: the same render with the same
 * inputs will often succeed on the second attempt.
 */
export default function RouteError({
  error,
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  useEffect(() => {
    // Kept until Stage 7.2 replaces it with Sentry. Logging the digest rather
    // than the message: in production the message is already redacted, and the
    // digest is what ties this to the server-side log line.
    console.error("route error", { digest: error.digest });
  }, [error]);

  return (
    <ErrorState
      title="Something went wrong"
      description="This page could not be loaded. Your work has not been lost — nothing was saved or changed by this failure."
      digest={error.digest}
      onRetry={reset}
    />
  );
}
