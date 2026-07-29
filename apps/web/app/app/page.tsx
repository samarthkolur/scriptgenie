import type { Metadata } from "next";
import Link from "next/link";

import { ErrorState } from "@/components/features/shell/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listProjects, type ProjectList } from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";

export const metadata: Metadata = { title: "Projects" };

/**
 * The project library.
 *
 * Reads through the typed API client, so the shapes here come from
 * `types/api.ts` and cannot drift from what the server returns without CI
 * noticing.
 *
 * The empty state is a real empty state, not a placeholder: a first-time user
 * arrives here and is told what a project is for, rather than being shown a
 * blank panel or a promise that the feature exists elsewhere.
 */
export default async function ProjectsPage() {
  let library: ProjectList;
  try {
    library = await listProjects({ limit: 20 });
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
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <p className="text-sm text-muted-foreground">
          Each project holds one set of constraints, the tensions detected
          between them, and the plot variants generated inside the bounds they
          produce.
        </p>
      </header>

      {library.projects.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="space-y-3">
          {library.projects.map((project) => (
            <li key={project.id}>
              <Card className="transition-colors hover:border-foreground/20">
                <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
                  <CardTitle className="text-base">
                    <Link
                      href={`/app/projects/${project.id}`}
                      className="rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {project.title}
                    </Link>
                  </CardTitle>
                  <Badge variant="secondary" className="shrink-0 capitalize">
                    {project.status}
                  </Badge>
                </CardHeader>
                {project.description !== null && project.description !== "" && (
                  <CardContent>
                    <p className="line-clamp-2 text-sm text-muted-foreground">
                      {project.description}
                    </p>
                  </CardContent>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <Card className="border-dashed">
      <CardContent className="space-y-3 py-10 text-center">
        <p className="text-sm font-medium">No projects yet</p>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          A project starts with what you already know about the film: its genre,
          the audience and rating you are aiming at, the budget tier you are
          working in, and where it will be released. ScriptGenie turns those
          into hard bounds before it generates anything.
        </p>
      </CardContent>
    </Card>
  );
}
