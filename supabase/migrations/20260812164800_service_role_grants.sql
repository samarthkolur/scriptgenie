-- Explicit `service_role` grants for the one write it is trusted with.
--
-- The previous migration states every other role's privileges explicitly and
-- says why: "so the file is a complete account of who may touch what." This
-- migration is the omission that statement was written to prevent.
--
-- BYPASSRLS lets `service_role` skip the policies above, but a bypassed policy
-- is not a grant — Postgres still checks schema USAGE and table-level
-- privileges first, and a role with neither is refused before RLS is ever
-- consulted. Supabase's hosted platform provisions this automatically for a
-- project created through its normal flow, which is why the gap was easy to
-- miss: every environment this schema had been deployed to already had it.
-- Confirmed live against a project where that provisioning was absent: with
-- only the previous migration applied, `service_role` got
-- `42501 permission denied for schema public` on both a read and the one
-- insert it exists to make. It is stated here for the same reason the
-- previous migration states anon and authenticated's grants rather than
-- trusting a default: a schema that depends on privileges no file here grants
-- is not a complete account of who may touch what.
--
-- Scoped to exactly what `SupabaseClient.as_service()` does and nothing more:
-- one insert-only grant on `usage_events`. Not `select`, matching the
-- "deliberately insert-only" contract in `app/db/supabase.py` — a service role
-- that could also read would be a second path to every user's spend, on top of
-- the one `usage_events_select_own` already grants its owner.

grant usage on schema public to service_role;

grant insert on public.usage_events to service_role;
