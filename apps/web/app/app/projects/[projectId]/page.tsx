import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProjectWorkspace } from "@/components/features/constraints/project-workspace";
import { ErrorState } from "@/components/features/shell/error-state";
import {
  getBundleDraft,
  getKbOptions,
  getProject,
  type BundleDraft,
  type KbOptions,
  type Project,
} from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";
import {
  DEFAULT_FORM_VALUES,
  fromBundle,
  type BundleFormValues,
} from "@/lib/constraints/schema";

type Props = {
  readonly params: Promise<{ readonly projectId: string }>;
};

export const metadata: Metadata = { title: "Constraints" };

/**
 * The project workspace: the constraint wizard and everything downstream of it.
 *
 * Three reads, and only one of them is allowed to fail benignly. The project
 * and the knowledge base are required — without either there is nothing to
 * render — but a project with no saved draft is the ordinary first visit, so a
 * 404 from the draft endpoint becomes the defaults rather than an error.
 */
export default async function ProjectPage({ params }: Props) {
  const { projectId } = await params;

  let project: Project;
  let options: KbOptions;
  try {
    [project, options] = await Promise.all([
      getProject(projectId),
      getKbOptions(),
    ]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.problem.status === 404) notFound();
    return (
      <ErrorState
        title="This project could not be opened"
        description={error.problem.detail}
        digest={error.problem.requestId}
      />
    );
  }

  const draft = await readDraft(projectId);
  const initialValues: BundleFormValues =
    draft === null ? DEFAULT_FORM_VALUES : fromBundle(draft.bundle);

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <Link
          href="/app"
          className="rounded-sm text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          ← All projects
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">
          {project.title}
        </h1>
        {project.description !== null && project.description !== "" && (
          <p className="text-sm text-muted-foreground">{project.description}</p>
        )}
      </header>

      <ProjectWorkspace
        projectId={project.id}
        options={options}
        initialValues={initialValues}
        hasSavedDraft={draft !== null}
      />
    </div>
  );
}

/**
 * The saved draft, or `null` when there is none.
 *
 * Only a 404 becomes `null`. Any other failure is re-raised, because "we could
 * not reach the API" and "this project has no constraints yet" must not render
 * the same way — the first would silently discard work the writer had already
 * done.
 */
async function readDraft(projectId: string): Promise<BundleDraft | null> {
  try {
    return await getBundleDraft(projectId);
  } catch (error) {
    if (error instanceof ApiError && error.problem.status === 404) return null;
    throw error;
  }
}
