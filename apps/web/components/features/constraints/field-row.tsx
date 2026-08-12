"use client";

import { HelpCircleIcon } from "lucide-react";

import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { FIELD_HELP, type FieldName } from "@/lib/constraints/field-help";

type Props = {
  readonly name: FieldName;
  readonly htmlFor?: string;
  readonly error?: string | undefined;
  readonly children: React.ReactNode;
};

/**
 * A labelled field with its explanation attached.
 *
 * The help is reachable two ways on purpose. The tooltip is for a pointer, and
 * the same text is rendered as a description tied to the control by
 * `aria-describedby`, so a screen reader reads it without having to discover a
 * hover target — a tooltip alone conveys the explanation to sighted mouse
 * users and to nobody else.
 *
 * The trigger is a real `button` with an accessible name rather than an icon
 * with a title attribute, so it is reachable by keyboard and announced as
 * something that can be opened.
 */
export function FieldRow({ name, htmlFor, error, children }: Props) {
  const { label, help } = FIELD_HELP[name];
  const describedBy = `${name}-help`;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <Label htmlFor={htmlFor}>{label}</Label>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`What does ${label} affect?`}
              className="rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <HelpCircleIcon className="size-3.5" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{help}</TooltipContent>
        </Tooltip>
      </div>

      {children}

      <p id={describedBy} className="text-xs text-muted-foreground">
        {help}
      </p>

      {error !== undefined && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
