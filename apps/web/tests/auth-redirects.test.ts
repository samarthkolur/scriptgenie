import { describe, expect, it } from "vitest";

import {
  DEFAULT_SIGNED_IN_PATH,
  safeReturnPath,
  signInPathFor,
} from "@/lib/auth/redirects";

/**
 * The `next` parameter is attacker-controllable, and a sign-in flow that
 * honours it blindly is an open redirect: a link to
 * `…/sign-in?next=https://evil.example` produces a genuine sign-in on a genuine
 * domain that then hands the freshly-authenticated user to somebody else.
 *
 * Every case below is a real bypass of a naive `startsWith("/")` check.
 */
describe("safeReturnPath", () => {
  it("keeps a same-origin path", () => {
    expect(safeReturnPath("/app/projects/42")).toBe("/app/projects/42");
  });

  it("keeps a path with a query string", () => {
    expect(safeReturnPath("/app?tab=variants")).toBe("/app?tab=variants");
  });

  it.each([
    ["https://evil.example/harvest", "an absolute URL"],
    ["http://evil.example", "an absolute URL over http"],
    ["evil.example/path", "a bare host"],
    [
      "//evil.example",
      "protocol-relative: the browser resolves it to another host",
    ],
    ["/\\evil.example", "backslash form, which several browsers treat as //"],
    ["javascript:alert(1)", "a javascript URL"],
    [
      "/app\nLocation: https://evil.example",
      "a newline that could split a header",
    ],
    ["/app\r\nSet-Cookie: admin=1", "CRLF injection"],
    ["", "an empty value"],
  ])("refuses %s (%s)", (candidate) => {
    expect(safeReturnPath(candidate)).toBe(DEFAULT_SIGNED_IN_PATH);
  });

  it.each([[null], [undefined]])("falls back when absent (%s)", (candidate) => {
    expect(safeReturnPath(candidate)).toBe(DEFAULT_SIGNED_IN_PATH);
  });

  it("refuses to send a signed-in user back to sign-in", () => {
    expect(safeReturnPath("/sign-in")).toBe(DEFAULT_SIGNED_IN_PATH);
    expect(safeReturnPath("/sign-in?next=/app")).toBe(DEFAULT_SIGNED_IN_PATH);
  });

  it("refuses a non-string, whatever a caller passes", () => {
    expect(safeReturnPath(42 as unknown as string)).toBe(
      DEFAULT_SIGNED_IN_PATH,
    );
  });
});

describe("signInPathFor", () => {
  it("carries the intended destination", () => {
    expect(signInPathFor("/app/projects/42")).toBe(
      "/sign-in?next=%2Fapp%2Fprojects%2F42",
    );
  });

  it("omits the parameter when the destination is the default", () => {
    expect(signInPathFor("/app")).toBe("/sign-in");
  });

  it("does not carry an unsafe destination even when handed one", () => {
    expect(signInPathFor("https://evil.example")).toBe("/sign-in");
  });

  it("encodes a destination that contains a query string", () => {
    const path = signInPathFor("/app?tab=variants&sort=new");

    // Encoded, so the destination's own parameters cannot escape into the
    // sign-in URL's query and be read as `next`'s siblings.
    expect(path).toBe("/sign-in?next=%2Fapp%3Ftab%3Dvariants%26sort%3Dnew");
    expect(new URLSearchParams(path.split("?")[1]).get("next")).toBe(
      "/app?tab=variants&sort=new",
    );
  });
});
