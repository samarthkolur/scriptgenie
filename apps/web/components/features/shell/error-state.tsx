"use client";

import { RotateCcwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

type Props = {
  readonly title: string;
  readonly description: string;
  /** Next.js supplies this on caught render errors. */
  readonly digest?: string | undefined;
  readonly onRetry?: (() => void) | undefined;
};

/**
 * What a user sees when something failed and there is nothing they did wrong.
 *
 * The `digest` is deliberately shown. Next.js replaces a server error's real
 * message with an opaque hash in production — that is correct, because an
 * exception message can contain a connection string or another user's data —
 * but a user who cannot quote *anything* leaves support with no way to find
 * the failure. The digest is the safe half of that trade.
 *
 * `role="alert"` so the failure is announced rather than silently replacing
 * the page for anyone using a screen reader.
 */
export function ErrorState({ title, description, digest, onRetry }: Props) {
  return (
    <div
      role="alert"
      className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-4 px-6 py-16 text-center"
    >
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      <p className="text-sm text-muted-foreground">{description}</p>

      {digest !== undefined && (
        <p className="font-mono text-xs text-muted-foreground">
          Reference: <span className="select-all">{digest}</span>
        </p>
      )}

      {onRetry !== undefined && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
          <RotateCcwIcon className="size-4" aria-hidden="true" />
          Try again
        </Button>
      )}
    </div>
  );
}
