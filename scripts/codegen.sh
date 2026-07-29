#!/usr/bin/env bash
#
# Regenerates the API contract and the TypeScript types built from it.
#
#   apps/api/app/**          (the routers and their pydantic models)
#     -> apps/api/openapi.json
#       -> apps/web/types/api.ts
#
# Both outputs are committed. That is deliberate: the OpenAPI document is the
# contract between two applications written in two languages, and committing it
# makes a change to the API a reviewable diff instead of a build that starts
# failing in the other app a week later.
#
# Neither file is ever edited by hand. `--check` runs in CI and fails if
# regeneration produces a diff, which catches exactly the case where somebody
# changed a route and did not regenerate — leaving the web app compiling
# happily against types the server no longer honours.

set -euo pipefail

cd "$(dirname "$0")/.."

readonly OPENAPI="apps/api/openapi.json"
readonly TYPES="apps/web/types/api.ts"

check_mode=0
if [ "${1:-}" = "--check" ]; then
  check_mode=1
fi

log() { printf '\033[1m==>\033[0m %s\n' "$*"; }

log "generating $OPENAPI"
(cd apps/api && uv run python -m scripts.export_openapi >/dev/null)

log "generating $TYPES"
# Run from apps/web: `openapi-typescript` is a devDependency of that workspace
# package, and `pnpm exec` only resolves binaries from the package it is run in.
root="$PWD"
(cd apps/web && pnpm exec openapi-typescript "$root/$OPENAPI" -o "$root/$TYPES" >/dev/null)

# The generator's output is not Prettier-formatted, and `pnpm format:check`
# covers this path. Formatting here keeps the two gates from disagreeing about
# a file neither of them owns.
pnpm exec prettier --write "$TYPES" "$OPENAPI" --log-level warn

if [ "$check_mode" -eq 1 ]; then
  # `git diff` says nothing about a file git is not tracking, so a deleted or
  # never-committed artefact would pass this check vacuously. Assert both are
  # tracked before asking whether they changed.
  for artefact in "$OPENAPI" "$TYPES"; do
    if ! git ls-files --error-unmatch "$artefact" >/dev/null 2>&1; then
      echo "codegen: $artefact is not committed. Run 'pnpm codegen' and commit it." >&2
      exit 1
    fi
  done

  if ! git diff --quiet -- "$OPENAPI" "$TYPES"; then
    echo
    echo "codegen: the committed API contract is stale." >&2
    echo >&2
    git --no-pager diff --stat -- "$OPENAPI" "$TYPES" >&2
    echo >&2
    echo "Run 'pnpm codegen' and commit the result." >&2
    exit 1
  fi
  log "the committed contract matches the code"
else
  log "done — commit $OPENAPI and $TYPES with the change that caused them"
fi
