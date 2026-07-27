#!/usr/bin/env bash
#
# Rejects AI-agent attribution in commit metadata.
#
# CLAUDE.md section 6 requires every commit to be authored by the repository
# owner alone, with no Co-Authored-By trailers and no AI tool credited as an
# author or contributor.
#
# The check is deliberately split in two, because "who is credited" and "what
# the message talks about" are different things:
#
#   1. Identity fields (author and committer name and email) must not name an
#      AI tool at all.
#   2. The message body must not carry an attribution *trailer*. Trailers are
#      line-anchored `Key: value` lines, so a commit that describes the rule in
#      prose is fine while a commit that actually credits an agent is not.
#
# Usage: check-authorship.sh [<base-ref> <head-ref>]
#        defaults to the whole history when no range is given.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

if [ "$#" -eq 2 ]; then
  RANGE="$1..$2"
else
  RANGE="$(git rev-list --max-parents=0 HEAD | head -1)..HEAD"
fi

# AI tools and vendors that must never appear as an author or contributor.
AGENT_NAMES='Anthropic|Claude|DeepSeek|Copilot|ChatGPT|OpenAI|Gemini|Cursor|Codeium|Devin'

# Attribution trailers, anchored to the start of a line.
TRAILER_PATTERN="^[[:space:]]*(Co-Authored-By|Co-authored-by|Assisted-by|Generated-by|Authored-by)[[:space:]]*:"

# Marketing footers that credit a tool for the change.
FOOTER_PATTERN="^[[:space:]]*(🤖[[:space:]]*)?(Generated with|Created with|Written by|Co-created with)[[:space:]]"

# `CLAUDE.md` is this repository's operating manual and is cited by name in
# commit bodies legitimately.
ALLOWED_LITERALS='CLAUDE\.md'

failures=0

report() {
  if [ "$failures" -eq 0 ]; then
    echo "check-authorship: forbidden attribution found"
    echo
    failures=1
  fi
  echo "  commit $(git log -1 --format='%h %s' "$1")"
  printf '%s\n' "$2" | sed 's/^/    /'
  echo
}

while IFS= read -r sha; do
  [ -z "$sha" ] && continue

  identity="$(git log -1 --format='author: %an <%ae>%ncommitter: %cn <%ce>' "$sha")"
  body="$(git log -1 --format='%B' "$sha" | sed -E "s/${ALLOWED_LITERALS}//g")"

  if hit=$(printf '%s\n' "$identity" | grep -Ei "$AGENT_NAMES"); then
    report "$sha" "$hit"
  fi

  if hit=$(printf '%s\n' "$body" | grep -E "$TRAILER_PATTERN"); then
    report "$sha" "$hit"
  fi

  if hit=$(printf '%s\n' "$body" | grep -Ei "$FOOTER_PATTERN"); then
    report "$sha" "$hit"
  fi
done < <(git rev-list "$RANGE" 2>/dev/null)

if [ "$failures" -eq 1 ]; then
  cat <<'MESSAGE'
Every commit must be authored by Samarth D Kolur <samarthdkolur1@gmail.com>
and must not credit any AI tool or agent as an author or contributor.

Rewrite the offending commits:

  git rebase -i <base>        # reword the messages
  git commit --amend --author="Samarth D Kolur <samarthdkolur1@gmail.com>"

See CLAUDE.md section 6.
MESSAGE
  exit 1
fi

echo "check-authorship: clean ($RANGE)"
exit 0
