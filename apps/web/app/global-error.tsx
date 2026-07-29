"use client";

/**
 * The last-resort boundary: a failure in the root layout itself.
 *
 * This replaces the entire document, which is why it renders its own `<html>`
 * and `<body>` — at this point the root layout is the thing that failed, so
 * nothing it would have provided can be relied on. That also rules out the
 * shared `ErrorState` component and the theme provider: both live inside the
 * tree that is not rendering. The styling is therefore inline and minimal on
 * purpose, and legible in both colour schemes without JavaScript.
 *
 * In practice this should never be reached. Reaching it means the layout, the
 * font loading or the providers threw, and the honest thing to show is a page
 * that needs nothing from any of them.
 */
export default function GlobalError({
  error,
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
          colorScheme: "light dark",
          padding: "1.5rem",
        }}
      >
        <main role="alert" style={{ maxWidth: "28rem", textAlign: "center" }}>
          <h1
            style={{
              fontSize: "1.125rem",
              fontWeight: 600,
              margin: "0 0 0.75rem",
            }}
          >
            ScriptGenie could not start
          </h1>
          <p
            style={{ fontSize: "0.875rem", opacity: 0.75, margin: "0 0 1rem" }}
          >
            The application failed to load. Nothing was saved or changed.
          </p>
          {error.digest !== undefined && (
            <p
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "0.75rem",
                opacity: 0.6,
                margin: "0 0 1.25rem",
              }}
            >
              Reference: {error.digest}
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            style={{
              font: "inherit",
              fontSize: "0.875rem",
              padding: "0.5rem 1rem",
              borderRadius: "0.5rem",
              border: "1px solid currentColor",
              background: "transparent",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </main>
      </body>
    </html>
  );
}
