#!/usr/bin/env bash
#
# Fails if placeholder, stub or mock artefacts appear in application code.
#
# CLAUDE.md forbids mock data, dummy implementations and unfinished stubs
# outside test directories: every stage must ship real, working functionality.
# This script is the mechanical enforcement of that rule and runs in `verify`,
# in the pre-push hook and as a required CI job.
#
# Test doubles are legitimate and expected — inside tests only.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

# Patterns that indicate unfinished or faked work.
PATTERNS=(
  'TODO'
  'FIXME'
  'XXX:'
  'HACK:'
  'NotImplementedError'
  'MOCK_'
  'DUMMY_'
  'lorem ipsum'
  'Lorem ipsum'
  'Coming soon'
  'coming soon'
  'placeholder data'
  'PLACEHOLDER'
)

# Application code only. Tests, generated artefacts and the documents that
# describe this very rule are excluded.
SEARCH_PATHS=(apps packages scripts supabase)

EXCLUDES=(
  ':!*/tests/*'
  ':!*/test/*'
  ':!*/__tests__/*'
  ':!*.test.ts'
  ':!*.test.tsx'
  ':!*.spec.ts'
  ':!*.spec.tsx'
  ':!*/node_modules/*'
  ':!*/.venv/*'
  ':!*/.next/*'
  ':!*.lock'
  ':!*lock.yaml'
  ':!*lock.json'
  ':!scripts/no-placeholders.sh'
)

existing_paths=()
for path in "${SEARCH_PATHS[@]}"; do
  [ -d "$path" ] && existing_paths+=("$path")
done

if [ ${#existing_paths[@]} -eq 0 ]; then
  echo "no-placeholders: no application directories to scan yet"
  exit 0
fi

found=0
for pattern in "${PATTERNS[@]}"; do
  if matches=$(git grep -n --fixed-strings "$pattern" -- "${existing_paths[@]}" "${EXCLUDES[@]}" 2>/dev/null); then
    if [ -n "$matches" ]; then
      if [ "$found" -eq 0 ]; then
        echo "no-placeholders: forbidden placeholder markers found in application code"
        echo
        found=1
      fi
      echo "  pattern: $pattern"
      echo "$matches" | sed 's/^/    /'
      echo
    fi
  fi
done

if [ "$found" -eq 1 ]; then
  cat <<'MESSAGE'
Application code must ship real, working functionality.

  - Unfinished work?   Build it in this stage, or move the stage.
  - Need a fake?       Put it in a tests/ directory; never import it from
                       application code.
  - Empty UI state?    Render a real empty state, not "Coming soon".

See CLAUDE.md, section 4: "No mock data, no placeholders, no dummy
implementations".
MESSAGE
  exit 1
fi

echo "no-placeholders: clean"
exit 0
