#!/usr/bin/env bash
#
# Environment-file guard.
#
# Two failure modes this catches that a generic secret scanner does not:
#
#   1. An environment or key file being tracked by git at all. Even when it
#      currently holds nothing sensitive, tracking it guarantees that the next
#      person to fill it in leaks their credentials.
#   2. A committed *.example file that contains a real-looking value rather
#      than an empty placeholder — the most common way a working key reaches
#      a public repository.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

failures=0

# ---------------------------------------------------------------- 1. tracked
tracked_forbidden=$(git ls-files | grep -E '(^|/)(\.env(\..*)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|id_rsa|id_ed25519)$' \
  | grep -Ev '\.example$' || true)

if [ -n "$tracked_forbidden" ]; then
  echo "env-guard: environment or key files are tracked by git"
  echo "$tracked_forbidden" | sed 's/^/    /'
  echo
  echo "  Remove them from the index and rotate anything they contained:"
  echo "    git rm --cached <file>"
  echo
  failures=1
fi

# ---------------------------------------------------------------- 2. examples
# A placeholder is empty, or an obvious stand-in. Anything else in an example
# file is treated as a real value.
while IFS= read -r example; do
  [ -z "$example" ] && continue
  while IFS= read -r line; do
    # Skip comments and blank lines.
    case "$line" in ''|'#'*) continue ;; esac
    # Only consider KEY=VALUE lines.
    case "$line" in *'='*) ;; *) continue ;; esac

    value="${line#*=}"
    # Trim surrounding whitespace and quotes.
    value="$(printf '%s' "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")"

    [ -z "$value" ] && continue

    # Accepted placeholder shapes and documented non-secret defaults.
    if printf '%s' "$value" | grep -Eq \
      '^(<.*>|your-.*|YOUR_.*|changeme|CHANGEME|xxx+|X+|\.\.\.|https?://localhost.*|https?://127\.0\.0\.1.*|development|test|production|DEBUG|INFO|WARNING|ERROR|true|false|[0-9]+)$'; then
      continue
    fi
    # Comma-separated localhost origin lists are legitimate defaults.
    if printf '%s' "$value" | grep -Eq '^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?(,https?://(localhost|127\.0\.0\.1)(:[0-9]+)?)*$'; then
      continue
    fi

    if [ "$failures" -eq 0 ]; then
      echo "env-guard: example files must not contain real values"
      echo
    fi
    failures=1
    echo "    $example: ${line%%=*} has a non-placeholder value"
  done <"$example"
done < <(git ls-files | grep -E '\.example$' || true)

if [ "$failures" -eq 1 ]; then
  echo
  echo "See CLAUDE.md section 7."
  exit 1
fi

echo "env-guard: clean"
exit 0
