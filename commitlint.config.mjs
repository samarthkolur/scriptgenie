/**
 * Conventional Commits enforcement.
 *
 * Every commit in this repository must be machine-parseable so that the
 * changelog can be generated from history and so that scope is obvious in
 * review. See CLAUDE.md section 6.
 */
export default {
  extends: ["@commitlint/config-conventional"],
  // Dependabot writes its own messages and offers no way to reformat them: the
  // body carries release notes and compare links that run well past 100
  // characters, and a grouped update's subject runs past 72. Those commits are
  // machine-generated and uniform, so nothing is lost by exempting them, and
  // the alternative — relaxing the limits for everyone — would weaken the rule
  // where it actually does work. Matched on Dependabot's sign-off trailer
  // rather than on the "chore(deps)" prefix, which humans also use and which
  // would hand every dependency commit a free pass. commitlint hands the
  // predicate only the message, never the author, so a hand-written trailer
  // would also be exempt; that is a deliberate forgery rather than an
  // accident, and CI's authorship gate is the control for that.
  ignores: [
    (message) =>
      /^Signed-off-by: dependabot\[bot\] <support@github\.com>$/m.test(message),
  ],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
      ],
    ],
    "scope-enum": [
      2,
      "always",
      [
        "web",
        "api",
        "kb",
        "db",
        "auth",
        "engines",
        "ui",
        "ci",
        "security",
        "docs",
        "deps",
        "release",
      ],
    ],
    "scope-empty": [0],
    // Forbid Title Case and shouting, but not acronyms: this domain is full of
    // them (MPA, BBFC, CBFC, FSK, VFX, JWT, API) and lower-casing them makes
    // subjects harder to read, not more consistent.
    "subject-case": [2, "never", ["pascal-case", "start-case", "upper-case"]],
    "subject-full-stop": [2, "never", "."],
    "header-max-length": [2, "always", 72],
    "body-max-line-length": [2, "always", 100],
  },
};
