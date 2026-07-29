# Supabase

The database half of ScriptGenie: schema, row level security, and the SQL tests
that prove both.

```
supabase/
├── migrations/          forward-only DDL, applied in filename order
├── tests/               SQL tests, run in filename order
│   └── harness/         the Supabase platform shim and assertion helpers
└── README.md
```

## Running the tests

```bash
pnpm test:db                                      # throwaway postgres in docker
DATABASE_URL=postgres://... pnpm test:db          # or an empty database you supply
```

The script creates the database fresh every time. That is the point: a
migration that only applies to an already-migrated database would pass against
a reused one and fail on the day it is deployed.

The same script runs in CI (the **Database** job) against a `postgres:16-alpine`
service container.

## The harness is not a migration

`tests/harness/00_supabase_shim.sql` creates `auth.users`, `auth.uid()` and the
`anon` / `authenticated` / `service_role` roles, because a stock PostgreSQL
image has none of them and the migrations reference all of them. It is never
applied to a real project, where Supabase provides these already.

The definitions in the shim are Supabase's own, copied rather than approximated.
If `auth.uid()` behaved differently here, a passing RLS test would prove nothing
about the deployed database — the only way this harness could be actively
harmful.

## Applying to a real project

Migrations are ordinary SQL and need no tooling beyond `psql`:

```bash
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/<file>.sql
```

With the Supabase CLI installed, `supabase db push` applies anything the linked
project has not seen, tracking applied versions in `supabase_migrations`.

Migrations are **forward-only**. A file that has been applied anywhere is never
edited; a correction ships as a later migration. Editing an applied file makes
two databases that report the same version structurally different, and nothing
downstream can then tell them apart.

## What the policies assume

Every user table carries `owner_id`, and every policy is the single comparison
`owner_id = (select auth.uid())`. That is only safe because the parent/child
graph is pinned by composite foreign keys — each parent has `unique (id,
owner_id)` and each child references `(parent_id, owner_id)` — so a row cannot
name one user's parent while claiming another owner. The two mechanisms are
tested together in `tests/20_ownership_isolation.sql`.

Three tables are deliberately not owner-writable:

| Table          | Who reads                  | Who writes                         |
| -------------- | -------------------------- | ---------------------------------- |
| `profiles`     | its own user               | the `on_auth_user_created` trigger |
| `kb_versions`  | everyone, signed in or not | nobody through the API             |
| `usage_events` | the user it bills          | the API under the service role     |

A client that could insert into `usage_events` could understate its own spend,
and one that could delete could erase the evidence of a rate limit it exceeded.
