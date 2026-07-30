import { describe, expect, it } from "vitest";

import {
  devLoginCredentials,
  isDevLoginAvailable,
  type DevLoginEnv,
} from "@/lib/auth/dev-login";
import { AUTH_ERROR_CODES, authErrorMessage } from "@/lib/auth/errors";

const FILLED_IN: DevLoginEnv = {
  NODE_ENV: "development",
  DEV_LOGIN_EMAIL: "local-tester@example.invalid",
  DEV_LOGIN_PASSWORD: "a-password-only-this-machine-has",
};

describe("devLoginCredentials", () => {
  it("returns the credentials when development and both variables are set", () => {
    expect(devLoginCredentials(FILLED_IN)).toEqual({
      email: "local-tester@example.invalid",
      password: "a-password-only-this-machine-has",
    });
  });

  it("refuses in production even with both variables set", () => {
    // The condition this repo actually relies on. `next build` and `next start`
    // both set production, so a deployed app cannot reach the route however
    // the environment is configured.
    expect(
      devLoginCredentials({ ...FILLED_IN, NODE_ENV: "production" }),
    ).toBeNull();
  });

  it("fails closed on any NODE_ENV that is not exactly development", () => {
    // An equality test, not `!== "production"`. An unset or misspelled value
    // must not be read as permission.
    for (const NODE_ENV of [
      undefined,
      "",
      "Development",
      "dev",
      "test",
      "staging",
    ]) {
      expect(devLoginCredentials({ ...FILLED_IN, NODE_ENV })).toBeNull();
    }
  });

  it("refuses when either variable is missing or blank", () => {
    expect(
      devLoginCredentials({ ...FILLED_IN, DEV_LOGIN_EMAIL: undefined }),
    ).toBeNull();
    expect(
      devLoginCredentials({ ...FILLED_IN, DEV_LOGIN_PASSWORD: undefined }),
    ).toBeNull();
    expect(
      devLoginCredentials({ ...FILLED_IN, DEV_LOGIN_EMAIL: "" }),
    ).toBeNull();
    expect(
      devLoginCredentials({ ...FILLED_IN, DEV_LOGIN_PASSWORD: "" }),
    ).toBeNull();
    // Whitespace is not a value. A variable left as `DEV_LOGIN_EMAIL= ` in a
    // .env file must not enable the route.
    expect(
      devLoginCredentials({ ...FILLED_IN, DEV_LOGIN_EMAIL: "   " }),
    ).toBeNull();
  });

  it("does not trim the password", () => {
    // Leading or trailing space may be part of it, and silently removing one
    // would produce a sign-in failure with no visible cause.
    expect(
      devLoginCredentials({ ...FILLED_IN, DEV_LOGIN_PASSWORD: " pad " })
        ?.password,
    ).toBe(" pad ");
  });

  it("agrees with isDevLoginAvailable", () => {
    expect(isDevLoginAvailable(FILLED_IN)).toBe(true);
    expect(isDevLoginAvailable({ ...FILLED_IN, NODE_ENV: "production" })).toBe(
      false,
    );
  });
});

describe("dev_login_failed", () => {
  it("is in the closed set, so its wording is ours and not the URL's", () => {
    expect(AUTH_ERROR_CODES).toContain("dev_login_failed");
    const message = authErrorMessage("dev_login_failed");
    expect(message).toContain("DEV_LOGIN_EMAIL");
  });
});
