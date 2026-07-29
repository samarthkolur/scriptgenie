-- Enough of Supabase's platform schema to run these migrations on a stock
-- PostgreSQL image.
--
-- This file is *not* a migration and is never applied to a real project. On
-- Supabase, `auth.users`, `auth.uid()` and the `anon` / `authenticated` /
-- `service_role` roles already exist; here they have to be created before the
-- migrations can reference them.
--
-- The definitions below are the ones Supabase publishes, not approximations
-- invented for the test. If `auth.uid()` behaved differently here from the way
-- it behaves in production, a passing RLS test would prove nothing about the
-- deployed database — which is the only failure mode this harness could have.

create extension if not exists "pgcrypto";

create schema if not exists auth;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end
$$;

create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Supabase's definition verbatim: read `sub` from the request-scoped JWT
-- claims, falling back to the older per-claim GUC. `true` on current_setting
-- suppresses the error when the setting is absent, which is how an
-- unauthenticated session yields NULL rather than failing the query.
create or replace function auth.uid()
returns uuid
language sql
stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

create or replace function auth.role()
returns text
language sql
stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;

create or replace function auth.email()
returns text
language sql
stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.email', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'email')
  )::text
$$;

grant usage on schema auth to anon, authenticated, service_role;
