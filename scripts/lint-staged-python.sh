#!/usr/bin/env bash
#
# Formats and lints staged Python files with ruff, from the API workspace so
# that pyproject.toml configuration applies. Invoked by lint-staged with the
# staged file paths as arguments (absolute, but relative paths also work).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"

[ "$#" -eq 0 ] && exit 0

# Resolve every argument to an absolute path before changing directory.
files=()
for file in "$@"; do
  case "$file" in
    /*) files+=("$file") ;;
    *) files+=("$REPO_ROOT/$file") ;;
  esac
done

cd "$API_DIR"

uv run ruff format "${files[@]}"
uv run ruff check --fix "${files[@]}"
