"use server";

import { revalidatePath } from "next/cache";

import { createProject } from "@/lib/api-client";
import { ApiError } from "@/lib/api/problem";

export type CreateProjectResult =
  | { readonly ok: true; readonly projectId: string }
  | { readonly ok: false; readonly error: string };

/**
 * Create a project and hand back its id.
 *
 * The caller navigates rather than this action redirecting. `redirect()` throws
 * a control-flow signal that a client `try` would swallow, and the form needs
 * to distinguish "created, go there" from "the title was rejected" — which is
 * a message beside the field, not a navigation.
 */
export async function createProjectAction(
  title: string,
  description: string,
): Promise<CreateProjectResult> {
  const trimmed = title.trim();
  if (trimmed === "") {
    return { ok: false, error: "Give the project a title." };
  }

  try {
    const project = await createProject({
      title: trimmed,
      description: description.trim() === "" ? null : description.trim(),
    });
    revalidatePath("/app");
    return { ok: true, projectId: project.id };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, error: error.problem.detail };
    }
    return {
      ok: false,
      error: "The project could not be created. Try again.",
    };
  }
}
