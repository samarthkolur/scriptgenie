import Markdown from "react-markdown";
import type { Components } from "react-markdown";

const COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="font-heading text-2xl font-semibold tracking-tight">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-8 font-heading text-lg font-medium">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-4 text-base font-medium">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="text-sm leading-relaxed text-foreground">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc space-y-1 pl-5 text-sm">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal space-y-1 pl-5 text-sm">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-medium">{children}</strong>,
  hr: () => <hr className="my-6 border-border" />,
};

/**
 * The exported document, rendered from the same Markdown the API produced.
 *
 * `export_service.render_markdown`'s own docstring is the reason this exists
 * rather than a second, hand-built rendering of the project/bundle/conflicts
 * shapes: two renderings of one document are two things that can disagree,
 * and this component's whole job is to be the one place that cannot.
 */
export function ExportDocument({ markdown }: { readonly markdown: string }) {
  return (
    <div className="space-y-3">
      <Markdown components={COMPONENTS}>{markdown}</Markdown>
    </div>
  );
}
