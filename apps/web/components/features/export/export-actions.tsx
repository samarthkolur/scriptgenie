"use client";

import { DownloadIcon, PrinterIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ExportBundle } from "@/lib/api-client";

type Props = {
  readonly bundle: ExportBundle;
  readonly filenameBase: string;
};

/**
 * Markdown, JSON and PDF, from the one document the API rendered.
 *
 * Markdown and JSON download exactly what `GET /export` returned — no
 * re-rendering on this side that could drift from it. PDF is the browser's
 * own print-to-PDF over the page below, which is real, not a placeholder:
 * every modern browser's print dialog can save to a file, so this needs no
 * server-side renderer or client PDF library to produce an actual PDF. It
 * does mean a "Save as PDF" click rather than a one-shot download, which is
 * the honest trade for not shipping a second, heavier rendering pipeline
 * purely to reproduce what the browser already does natively.
 *
 * `print:hidden` so the controls themselves never appear in the output they
 * produce.
 */
export function ExportActions({ bundle, filenameBase }: Props) {
  function downloadMarkdown() {
    download(`${filenameBase}.md`, bundle.markdown, "text/markdown");
  }

  function downloadJson() {
    download(
      `${filenameBase}.json`,
      JSON.stringify(bundle, null, 2),
      "application/json",
    );
  }

  return (
    <div className="flex flex-wrap gap-2 print:hidden">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={downloadMarkdown}
      >
        <DownloadIcon className="size-3.5" aria-hidden="true" />
        Download Markdown
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={downloadJson}>
        <DownloadIcon className="size-3.5" aria-hidden="true" />
        Download JSON
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => window.print()}
      >
        <PrinterIcon className="size-3.5" aria-hidden="true" />
        Print / Save as PDF
      </Button>
    </div>
  );
}

function download(filename: string, contents: string, mimeType: string): void {
  const blob = new Blob([contents], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
