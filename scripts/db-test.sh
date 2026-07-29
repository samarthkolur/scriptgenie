#!/usr/bin/env bash
#
# Applies every migration to an empty database and runs the SQL tests against it.
#
# Two things are proved here, and the second only follows from the first:
#
#   1. the migrations apply cleanly, in filename order, onto a database that has
#      never seen them;
#   2. the row level security policies actually isolate two users.
#
# The database is created fresh on every run. Reusing one would let a migration
# that only works against an already-migrated database pass here and fail on the
# day it is deployed, which is exactly the failure this script exists to catch.
#
# Usage:
#   scripts/db-test.sh                 # start a throwaway postgres in docker
#   DATABASE_URL=postgres://...        # or run against a database you supply
#
# The supplied database must be empty and the connecting role must be able to
# create roles and schemas: the harness builds the parts of the Supabase
# platform schema (auth.users, auth.uid(), the anon/authenticated roles) that a
# stock PostgreSQL image does not have.

set -euo pipefail

cd "$(dirname "$0")/.."

readonly IMAGE="postgres:16-alpine"
readonly CONTAINER="scriptgenie-db-test"
readonly PORT="${DB_TEST_PORT:-55433}"

log() { printf '\033[1m==>\033[0m %s\n' "$*"; }

started_container=0

cleanup() {
  if [ "$started_container" -eq 1 ]; then
    docker rm --force "$CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [ -z "${DATABASE_URL:-}" ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "db-test: no DATABASE_URL set and docker is not installed." >&2
    echo "         Set DATABASE_URL to an empty database, or install docker." >&2
    exit 1
  fi

  log "starting $IMAGE on port $PORT"
  docker rm --force "$CONTAINER" >/dev/null 2>&1 || true
  docker run --detach --name "$CONTAINER" \
    --env POSTGRES_PASSWORD=postgres \
    --env POSTGRES_DB=scriptgenie_test \
    --publish "127.0.0.1:$PORT:5432" \
    "$IMAGE" >/dev/null
  started_container=1

  DATABASE_URL="postgres://postgres:postgres@127.0.0.1:$PORT/scriptgenie_test"

  # Readiness is a completed query over the published port, not `pg_isready`.
  # The postgres image starts a temporary server to run its init scripts and
  # then restarts; `pg_isready` answers yes during that window, and the first
  # real statement then loses its connection mid-run.
  log "waiting for the database to accept connections"
  ready=0
  for _ in $(seq 1 60); do
    if psql "$DATABASE_URL" --quiet --no-psqlrc --command 'select 1' >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.5
  done
  if [ "$ready" -eq 0 ]; then
    echo "db-test: the database did not become ready in 30s" >&2
    docker logs "$CONTAINER" >&2
    exit 1
  fi
fi

# Every psql invocation stops on the first error and treats a failed statement
# as a failed run. Without ON_ERROR_STOP, psql reports the error and carries on,
# and the script would exit 0 with a broken schema.
psql_run() {
  psql "$DATABASE_URL" \
    --quiet --no-psqlrc \
    --set ON_ERROR_STOP=1 \
    --file "$1"
}

log "installing the Supabase platform shim"
psql_run supabase/tests/harness/00_supabase_shim.sql

log "applying migrations"
shopt -s nullglob
migrations=(supabase/migrations/*.sql)
shopt -u nullglob
if [ ${#migrations[@]} -eq 0 ]; then
  echo "db-test: no migrations found in supabase/migrations/" >&2
  exit 1
fi
for migration in "${migrations[@]}"; do
  printf '    %s\n' "$(basename "$migration")"
  psql_run "$migration"
done

log "installing assertion helpers"
psql_run supabase/tests/harness/01_assert.sql

log "running tests"
shopt -s nullglob
tests=(supabase/tests/*.sql)
shopt -u nullglob
if [ ${#tests[@]} -eq 0 ]; then
  echo "db-test: no tests found in supabase/tests/" >&2
  exit 1
fi

failures=0
for test_file in "${tests[@]}"; do
  name="$(basename "$test_file")"
  printf '\n  \033[1m%s\033[0m\n' "$name"
  if output=$(psql_run "$test_file" 2>&1); then
    # psql prefixes every notice with the file and line that raised it; the
    # assertion text after "NOTICE:" is the part worth reading.
    printf '%s\n' "$output" | sed -n 's/^.*NOTICE:  /    /p'
  else
    failures=$((failures + 1))
    printf '%s\n' "$output" | sed 's/^/    /'
  fi
done

echo
if [ "$failures" -ne 0 ]; then
  log "$failures test file(s) failed"
  exit 1
fi

log "all SQL tests passed"
