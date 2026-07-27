#!/usr/bin/env bash
#
# Secret scanning wrapper.
#
# Runs gitleaks over the working tree and the full commit history. Used by
# `pnpm verify` and by the pre-push hook. CI runs gitleaks directly through
# its official action, so this script only has to be convenient locally.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

if ! command -v gitleaks >/dev/null 2>&1; then
  cat <<'MESSAGE'
secret-scan: gitleaks is not installed.

Install it before committing:

  # Linux / macOS via release binary
  curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_linux_x64.tar.gz \
    | tar -xz -C ~/.local/bin gitleaks

  # or: brew install gitleaks

Secret scanning is not optional. CI enforces it on every pull request.
MESSAGE
  exit 1
fi

echo "secret-scan: scanning working tree"
gitleaks detect --source . --no-git --redact --exit-code 1 || exit 1

echo "secret-scan: scanning commit history"
gitleaks detect --source . --redact --exit-code 1 || exit 1

echo "secret-scan: clean"
