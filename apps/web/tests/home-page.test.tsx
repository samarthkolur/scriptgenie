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
});
