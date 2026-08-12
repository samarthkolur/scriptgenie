import { describe, expect, it } from "vitest";

import {
  DEFAULT_SIGNED_IN_PATH,
  safeReturnPath,
  signInPathFor,
  strandedAuthResponse,
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

/**
 * Supabase substitutes the Site URL when `redirect_to` is not on the project's
 * allow-list, and does it silently. The observed failure is a real sign-in that
 * returns to `http://localhost:3000/?code=…` and leaves the user on the landing
 * page, still signed out, with no error anywhere.
 */
describe("strandedAuthResponse", () => {
  const at = (pathname: string, query: string) =>
    strandedAuthResponse(pathname, new URLSearchParams(query));

  it("forwards an authorisation code delivered to the site root", () => {
    expect(at("/", "code=abc123")).toBe("/auth/callback?code=abc123");
  });

  it("carries every parameter across, not just the code", () => {
    const forwarded = at("/", "code=abc123&next=%2Fapp%2Fprojects%2F42");

    expect(forwarded).not.toBeNull();
    const params = new URLSearchParams(forwarded!.split("?")[1]);
    expect(params.get("code")).toBe("abc123");
    // `/auth/callback` re-filters this through `safeReturnPath`; forwarding it
    // unchanged is what lets it do so.
    expect(params.get("next")).toBe("/app/projects/42");
  });

  it("forwards a provider error so the user reads a real message", () => {
    expect(at("/", "error=access_denied")).toBe(
      "/auth/callback?error=access_denied",
    );
  });

  it("leaves an ordinary visit to the landing page alone", () => {
    expect(at("/", "")).toBeNull();
    expect(at("/", "utm_source=twitter")).toBeNull();
  });

  it.each([
    ["/app", "a signed-in route"],
    ["/sign-in", "the sign-in page"],
    ["/auth/callback", "the callback itself, which would loop"],
    ["/app/projects/42", "a nested route"],
  ])("ignores %s with a code on it (%s)", (pathname) => {
    expect(at(pathname, "code=abc123")).toBeNull();
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
