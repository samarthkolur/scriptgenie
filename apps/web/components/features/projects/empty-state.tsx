import { NewProjectDialog } from "@/components/features/projects/new-project-dialog";
import { Card, CardContent } from "@/components/ui/card";

/**
 * A first-time user arrives here and is told what a project is for, rather
 * than being shown a blank panel or a promise that the feature exists
 * elsewhere.
 */
export function EmptyState() {
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
        <div className="flex justify-center pt-2">
          <NewProjectDialog />
        </div>
      </CardContent>
    </Card>
  );
}
