import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectLibraryList } from "@/components/features/projects/project-library-list";
import type { Project } from "@/lib/api-client";

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    title: "Cabin horror comedy",
    description: "Five friends, one storm, no signal.",
    status: "draft",
    created_at: "2026-08-11T00:00:00Z",
    updated_at: "2026-08-11T00:00:00Z",
    ...overrides,
  } as Project;
}

describe("ProjectLibraryList", () => {
  it("shows every project when the search is empty", () => {
    render(
      <ProjectLibraryList
        projects={[
          project(),
          project({ id: "2", title: "Heist thriller", description: null }),
        ]}
      />,
    );

    expect(screen.getByText("Cabin horror comedy")).toBeTruthy();
    expect(screen.getByText("Heist thriller")).toBeTruthy();
  });

  it("filters by title", () => {
    render(
      <ProjectLibraryList
        projects={[
          project(),
          project({ id: "2", title: "Heist thriller", description: null }),
        ]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Search projects"), {
      target: { value: "heist" },
    });

    expect(screen.queryByText("Cabin horror comedy")).toBeNull();
    expect(screen.getByText("Heist thriller")).toBeTruthy();
  });

  it("filters by description too", () => {
    render(
      <ProjectLibraryList
        projects={[
          project(),
          project({ id: "2", title: "Heist thriller", description: null }),
        ]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Search projects"), {
      target: { value: "storm" },
    });

    expect(screen.getByText("Cabin horror comedy")).toBeTruthy();
    expect(screen.queryByText("Heist thriller")).toBeNull();
  });

  it("says plainly when nothing matches, rather than showing an empty list", () => {
    render(<ProjectLibraryList projects={[project()]} />);

    fireEvent.change(screen.getByLabelText("Search projects"), {
      target: { value: "nonexistent" },
    });

    expect(screen.getByText(/Nothing here matches/)).toBeTruthy();
  });
});
