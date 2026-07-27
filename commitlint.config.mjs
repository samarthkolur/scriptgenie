/**
 * Conventional Commits enforcement.
 *
 * Every commit in this repository must be machine-parseable so that the
 * changelog can be generated from history and so that scope is obvious in
 * review. See CLAUDE.md section 6.
 */
export default {
  extends: ["@commitlint/config-conventional"],
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
