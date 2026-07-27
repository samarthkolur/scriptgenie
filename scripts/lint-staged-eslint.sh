#!/usr/bin/env bash
#
# Lints staged web files with eslint, from the web workspace so that its flat
# config and plugin resolution apply. eslint is a dependency of @scriptgenie/web
# and is deliberately not installed at the repository root.
#
# Invoked by lint-staged with the staged file paths as arguments.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$REPO_ROOT/apps/web"

[ "$#" -eq 0 ] && exit 0

files=()
for file in "$@"; do
  case "$file" in
    /*) files+=("$file") ;;
    *) files+=("$REPO_ROOT/$file") ;;
  esac
done

cd "$WEB_DIR"
pnpm exec eslint --fix --no-warn-ignored "${files[@]}"
