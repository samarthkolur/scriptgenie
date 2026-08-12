import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ExportActions } from "@/components/features/export/export-actions";
import { ExportDocument } from "@/components/features/export/export-document";
import { ErrorState } from "@/components/features/shell/error-state";
import { exportProject, type ExportBundle } from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";
import { slugify } from "@/lib/utils";

type Props = {
  readonly params: Promise<{ readonly projectId: string }>;
};

export const metadata: Metadata = { title: "Export" };

/**
 * The project as one reproducible document: Markdown, JSON, or print-to-PDF.
 *
 * `exportProject` already carries every version behind the output — kb,
 * prompt, and each variant's own model — because `ExportBundle` is built once
 * on the server and both the JSON a caller downloads and the Markdown this
 * page renders come from that same call. There is no second export pipeline
 * to drift from the first.
 */
export default async function ExportPage({ params }: Props) {
  const { projectId } = await params;

  let bundle: ExportBundle;
  try {
    bundle = await exportProject(projectId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.problem.status === 404) notFound();
    return (
      <ErrorState
        title="This export could not be built"
        description={error.problem.detail}
        digest={error.problem.requestId}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 print:hidden">
        <Link
          href={`/app/projects/${projectId}`}
          className="rounded-sm text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          ← Back to workspace
        </Link>
      </div>

      <ExportActions
        bundle={bundle}
        filenameBase={slugify(bundle.project.title)}
      />

      <article className="max-w-2xl">
        <ExportDocument markdown={bundle.markdown} />
      </article>
    </div>
  );
}
