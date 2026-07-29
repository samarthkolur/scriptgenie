import { Skeleton } from "@/components/ui/skeleton";

/**
 * Loading placeholders shaped like the content they stand in for.
 *
 * A spinner says "wait"; a skeleton says "wait, and here is roughly what is
 * coming". More practically, matching the real layout keeps the page from
 * jumping when the content lands, which is what a layout-shift score measures
 * and what makes a page feel unstable to use.
 *
 * Each block is marked `aria-hidden` and wrapped in a live region that
 * announces the wait once. Otherwise a screen reader either reads nothing at
 * all, or reads a dozen empty boxes.
 */

export function LoadingRegion({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true">{children}</div>
    </div>
  );
}

/** The account page: a heading, a line of prose, and a short definition list. */
export function ProfileSkeleton() {
  return (
    <LoadingRegion label="Loading your account">
      <div className="space-y-8">
        <div className="space-y-3">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-full max-w-xl" />
        </div>
        <div className="space-y-4">
          {[0, 1, 2].map((row) => (
            <div key={row} className="flex gap-8">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-56" />
            </div>
          ))}
        </div>
      </div>
    </LoadingRegion>
  );
}

/** The project library: a heading and a stack of cards. */
export function ProjectListSkeleton({ rows = 3 }: { readonly rows?: number }) {
  return (
    <LoadingRegion label="Loading your projects">
      <div className="space-y-8">
        <Skeleton className="h-7 w-40" />
        <div className="space-y-3">
          {Array.from({ length: rows }, (_, index) => (
            <div key={index} className="space-y-2 rounded-lg border p-4">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </div>
      </div>
    </LoadingRegion>
  );
}
