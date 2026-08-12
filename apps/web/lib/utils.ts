import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** An id's label from a KB options list, falling back to the id itself. */
export function labelFor(
  id: string,
  from: readonly { readonly id: string; readonly label: string }[],
): string {
  return from.find((item) => item.id === id)?.label ?? id;
}

/** A title as a filename stem: lowercase, hyphenated, nothing a filesystem would reject. */
export function slugify(title: string): string {
  const slug = title
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, "-")
    .replaceAll(/^-+|-+$/g, "");
  return slug === "" ? "export" : slug;
}
