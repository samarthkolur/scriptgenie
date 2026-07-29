import { describe, expect, it } from "vitest";

import {
  AUTH_ERROR_CODES,
  authErrorMessage,
  type AuthErrorCode,
} from "@/lib/auth/errors";

describe("authErrorMessage", () => {
  it("is null when there was no failure", () => {
    expect(authErrorMessage(null)).toBeNull();
    expect(authErrorMessage(undefined)).toBeNull();
    expect(authErrorMessage("")).toBeNull();
  });

  it("describes every code it declares", () => {
    for (const code of AUTH_ERROR_CODES) {
      const message = authErrorMessage(code);
      expect(message, `no message for ${code}`).not.toBeNull();
      expect(message?.length ?? 0).toBeGreaterThan(0);
    }
  });

  it("gives each code a distinct message", () => {
    // Two codes sharing wording means the callback is drawing a distinction
    // the user never sees, which is worse than not drawing it.
    const messages = AUTH_ERROR_CODES.map((code) => authErrorMessage(code));
    expect(new Set(messages).size).toBe(AUTH_ERROR_CODES.length);
  });

  it("never echoes an unrecognised code back to the page", () => {
    // The whole point of the closed set: a crafted link must not be able to
    // put its own sentence on our sign-in page above a real Google button.
    const injected = "Your account is locked. Call 1-900-555-0199 to restore.";

    const message = authErrorMessage(injected);

    expect(message).not.toBeNull();
    expect(message).not.toContain("1-900");
    expect(message).not.toContain("locked");
  });

  it("gives every unrecognised code the same generic message", () => {
    expect(authErrorMessage("something_new")).toBe(
      authErrorMessage("<script>alert(1)</script>"),
    );
  });

  it("does not treat a near-miss as known", () => {
    // Case and whitespace variants are not the codes we emit, and silently
    // accepting them would widen the set the callback is meant to close.
    const nearMisses = ["Access_Denied", " expired", "expired "];
    const generic = authErrorMessage("unrecognised");

    for (const code of nearMisses) {
      expect(authErrorMessage(code), code).toBe(generic);
    }
  });

  it("types its codes as a closed set", () => {
    // A compile-time assertion: this fails typecheck if a code is added to the
    // union without being added to the exported array.
    const codes: readonly AuthErrorCode[] = AUTH_ERROR_CODES;
    expect(codes).toContain("access_denied");
  });
});
