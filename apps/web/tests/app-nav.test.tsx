import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  AppNav,
  isActive,
  NAV_ITEMS,
} from "@/components/features/shell/app-nav";

const mockPathname = vi.hoisted(() => ({ value: "/app" }));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname.value,
}));

describe("isActive", () => {
  it("matches /app only exactly", () => {
    // Every route is nested under /app, so a prefix test would light up
    // "Projects" on every page in the application including Account.
    expect(isActive("/app", "/app", true)).toBe(true);
    expect(isActive("/app/account", "/app", true)).toBe(false);
    expect(isActive("/app/projects/42", "/app", true)).toBe(false);
  });

  it("matches a section and everything under it", () => {
    expect(isActive("/app/account", "/app/account", false)).toBe(true);
    expect(isActive("/app/account/billing", "/app/account", false)).toBe(true);
  });

  it("does not match a sibling with a shared prefix", () => {
    // /app/accounts must not activate /app/account.
    expect(isActive("/app/accounts", "/app/account", false)).toBe(false);
  });
});

describe("AppNav", () => {
  it("renders every destination", () => {
    mockPathname.value = "/app";
    render(<AppNav />);

    for (const item of NAV_ITEMS) {
      expect(screen.getByRole("link", { name: item.label })).toBeDefined();
    }
  });

  it("marks exactly one item as the current page", () => {
    mockPathname.value = "/app/account";
    render(<AppNav />);

    const current = screen
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");

    expect(current).toHaveLength(1);
    expect(current[0]?.textContent).toBe("Account");
  });

  it("conveys the current page to assistive technology, not by colour alone", () => {
    mockPathname.value = "/app";
    render(<AppNav />);

    // aria-current is the accessible signal. Without it "you are here" exists
    // only as a background colour.
    expect(
      screen
        .getByRole("link", { name: "Projects" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("marks nothing when the path is outside the nav", () => {
    mockPathname.value = "/sign-in";
    render(<AppNav />);

    const current = screen
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");

    expect(current).toHaveLength(0);
  });

  it("names the landmark so it can be skipped to", () => {
    mockPathname.value = "/app";
    render(<AppNav />);

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeDefined();
  });
});
