import { describe, expect, it } from "vitest";

import {
  avatarUrlFrom,
  displayNameFrom,
  initials,
  type UserLike,
} from "@/lib/user-display";

/**
 * `user_metadata` is provider-controlled and typed as `unknown`. Every case
 * here is a shape a real identity provider actually returns, plus the ones an
 * attacker could return.
 */
describe("displayNameFrom", () => {
  it("prefers the Google full_name claim", () => {
    const user: UserLike = {
      email: "ada@example.test",
      user_metadata: { full_name: "Ada Lovelace", name: "ada" },
    };
    expect(displayNameFrom(user)).toBe("Ada Lovelace");
  });

  it("falls back to the name claim", () => {
    expect(
      displayNameFrom({
        email: "g@example.test",
        user_metadata: { name: "Grace" },
      }),
    ).toBe("Grace");
  });

  it("falls back to the email local part, not the whole address", () => {
    // A header is not the place to publish someone's email to whoever is
    // looking over their shoulder.
    expect(displayNameFrom({ email: "katherine@example.test" })).toBe(
      "katherine",
    );
  });

  it("never renders an empty string", () => {
    // An empty name produces an invisible menu trigger with no way to sign out.
    expect(displayNameFrom({ email: null, user_metadata: {} })).toBe(
      "Your account",
    );
    expect(displayNameFrom(null)).toBe("Your account");
    expect(displayNameFrom(undefined)).toBe("Your account");
  });

  it("ignores whitespace-only and non-string claims", () => {
    expect(
      displayNameFrom({
        email: "ada@example.test",
        user_metadata: { full_name: "   ", name: 42 },
      }),
    ).toBe("ada");
  });

  it("trims a padded claim", () => {
    expect(displayNameFrom({ user_metadata: { full_name: "  Ada  " } })).toBe(
      "Ada",
    );
  });

  it("survives null metadata", () => {
    expect(displayNameFrom({ email: "a@b.test", user_metadata: null })).toBe(
      "a",
    );
  });
});

describe("avatarUrlFrom", () => {
  it("reads the Google avatar claim", () => {
    expect(
      avatarUrlFrom({
        user_metadata: { avatar_url: "https://cdn.example/a.png" },
      }),
    ).toBe("https://cdn.example/a.png");
  });

  it("falls back to the picture claim", () => {
    expect(
      avatarUrlFrom({
        user_metadata: { picture: "https://cdn.example/p.png" },
      }),
    ).toBe("https://cdn.example/p.png");
  });

  it.each([
    ["javascript:alert(1)", "a javascript URL in a src is script execution"],
    ["data:text/html;base64,PHNjcmlwdD4=", "a data URL can carry markup"],
    ["http://cdn.example/a.png", "plain http would be a mixed-content request"],
    ["//cdn.example/a.png", "protocol-relative inherits the page scheme"],
    ["/local/path.png", "a relative path is not a provider avatar"],
  ])("refuses %s (%s)", (url) => {
    // user_metadata is provider-controlled and lands in a `src`.
    expect(avatarUrlFrom({ user_metadata: { avatar_url: url } })).toBeNull();
  });

  it("returns null when there is no picture at all", () => {
    expect(avatarUrlFrom({ user_metadata: {} })).toBeNull();
    expect(avatarUrlFrom(null)).toBeNull();
  });
});

describe("initials", () => {
  it("takes first and last for a full name", () => {
    expect(initials("Ada Lovelace")).toBe("AL");
  });

  it("takes one letter for a single name", () => {
    expect(initials("Ada")).toBe("A");
  });

  it("skips middle names", () => {
    expect(initials("Katherine Coleman Goble Johnson")).toBe("KJ");
  });

  it("collapses irregular whitespace", () => {
    expect(initials("  Ada   Lovelace  ")).toBe("AL");
  });

  it("never returns an empty badge", () => {
    expect(initials("")).toBe("?");
    expect(initials("   ")).toBe("?");
  });

  it("does not split a surrogate pair", () => {
    // Indexing with [0] would return half of an astral character and render
    // as a replacement glyph.
    expect(initials("🎬 Studio")).toBe("🎬S");
  });
});
