import type { Metadata } from "next";

import { EmptyState } from "@/components/features/projects/empty-state";
import { NewProjectDialog } from "@/components/features/projects/new-project-dialog";
import { ProjectLibraryList } from "@/components/features/projects/project-library-list";
import { ErrorState } from "@/components/features/shell/error-state";
import { listProjects, type ProjectList } from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";

export const metadata: Metadata = { title: "Projects" };

/**
 * The project library.
 *
 * Reads through the typed API client, so the shapes here come from
 * `types/api.ts` and cannot drift from what the server returns without CI
 * noticing. Fetched at the API's own page-size ceiling (100) rather than a
 * smaller default, because `ProjectLibraryList`'s search is over what this
 * page already holds — a search box that could only see the newest twenty
 * projects would be a search box that lied about how thorough it was.
 */
export default async function ProjectsPage() {
  let library: ProjectList;
  try {
    library = await listProjects({ limit: 100 });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <ErrorState
        title="Your projects could not be loaded"
        description={error.problem.detail}
        digest={error.problem.requestId}
      />
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Each project holds one set of constraints, the tensions detected
            between them, and the plot variants generated inside the bounds they
            produce.
          </p>
        </div>
        <NewProjectDialog />
      </header>

      {library.projects.length === 0 ? (
        <EmptyState />
      ) : (
        <ProjectLibraryList projects={library.projects} />
      )}
    </div>
  );
}
