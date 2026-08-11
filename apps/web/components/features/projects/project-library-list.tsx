"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { Project } from "@/lib/api-client";

type Props = {
  readonly projects: readonly Project[];
};

/**
 * The project list, searchable over what the page already has.
 *
 * A project's genre, tier and rating live on its constraint bundle rather
 * than on the project row itself — and a project can have zero bundles, or
 * several over its life — so filtering by them would need a join this list
 * does not do. Title and description search does not have that problem:
 * both live on the project, so the search here is real, not a stand-in for
 * the fuller filter.
 *
 * Only ever rendered with a non-empty `projects` — the caller shows
 * `EmptyState` instead when there is nothing yet, so this has no empty-input
 * branch of its own to duplicate that check.
 */
export function ProjectLibraryList({ projects }: Props) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") return projects;
    return projects.filter(
      (project) =>
        project.title.toLowerCase().includes(needle) ||
        (project.description ?? "").toLowerCase().includes(needle),
    );
  }, [projects, query]);

  return (
    <div className="space-y-4">
      <Input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search projects by title or description"
        aria-label="Search projects"
        className="max-w-sm"
      />

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing here matches “{query}”.
        </p>
      ) : (
        <ul className="space-y-3">
          {filtered.map((project) => (
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
