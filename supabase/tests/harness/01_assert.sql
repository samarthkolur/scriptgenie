-- Assertion helpers for the SQL tests.
--
-- Deliberately not pgTAP. pgTAP is an extension the production database does
-- not have and does not want, and adding a dependency to the database under
-- test in order to test it is how a test starts describing something other
-- than what ships. `raise exception` aborts the transaction, psql's
-- ON_ERROR_STOP aborts the run, and the runner's exit code is the result.

create schema if not exists test;

-- The assertions run *while impersonating* `authenticated`, so that role has to
-- be able to reach the helpers. It gets nothing but the helpers: the schema
-- holds no tables and its functions only assert.
grant usage on schema test to public;

create or replace function test.ok(condition boolean, description text)
returns void
language plpgsql
as $$
begin
  if condition is null or not condition then
    raise exception 'FAIL: %', description;
  end if;
  raise notice 'ok   %', description;
end;
$$;

create or replace function test.equals(actual anyelement, expected anyelement, description text)
returns void
language plpgsql
as $$
begin
  if actual is distinct from expected then
    raise exception 'FAIL: % (expected %, got %)', description, expected, actual;
  end if;
  raise notice 'ok   %', description;
end;
$$;

-- Adopt a user's session exactly as PostgREST does: the role first, then the
-- claims the request carried. Anything that reads `auth.uid()` after this sees
-- that user and nothing else.
create or replace function test.become(user_id uuid)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    json_build_object('sub', user_id::text, 'role', 'authenticated')::text,
    true
  );
  set local role authenticated;
end;
$$;

-- Drop back to the owning role so the next fixture can be inserted.
create or replace function test.become_owner()
returns void
language plpgsql
as $$
begin
  reset role;
  perform set_config('request.jwt.claims', '', true);
end;
$$;

-- Run a statement as the current session role and report whether the database
-- refused it. Used for the negative cases, where the test is only meaningful if
-- the refusal is proven rather than assumed.
create or replace function test.is_rejected(statement text)
returns boolean
language plpgsql
as $$
begin
  execute statement;
  return false;
exception
  -- Every way the database has of saying no. Listed rather than caught with a
  -- bare `when others` so that a statement failing for an unrelated reason —
  -- a typo in the test, a renamed column — surfaces as an error instead of
  -- being counted as a successful refusal.
  when insufficient_privilege
    or check_violation
    or foreign_key_violation
    or not_null_violation
    or unique_violation
    or exclusion_violation
    or invalid_text_representation then
    return true;
end;
$$;
