import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("names the product", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "ScriptGenie" }),
    ).toBeDefined();
  });

  it("describes all three architectural layers in order", () => {
    render(<HomePage />);

    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);

    expect(headings).toEqual([
      "Conflict detection",
      "Scope parameterisation",
      "Variant generation",
    ]);
  });

  it("states the ideation-not-screenplay scope", () => {
    render(<HomePage />);

    expect(
      screen.getByText(/not screenplays/i, { exact: false }),
    ).toBeDefined();
  });

  it("makes the scope statement an announced callout, not a footnote", () => {
    render(<HomePage />);

    // Research doc Risk 3: a reader who assumes this drafts scripts judges the
    // output as a failed screenplay. The correction has to be prominent, and
    // it has to reach a screen reader as more than body text.
    const callout = screen.getByRole("alert");

    expect(callout.textContent).toMatch(/not screenplays/i);
    expect(callout.textContent).toMatch(/pre-development/i);
  });

  it("offers a route into the product", () => {
    render(<HomePage />);

    const cta = screen.getByRole("link", { name: /continue with google/i });

    // Straight to /sign-in rather than starting OAuth from here: the landing
    // page is a Server Component, and the flow needs the sign-in page to carry
    // the return path and any failure code.
    expect(cta.getAttribute("href")).toBe("/sign-in");
  });
});
