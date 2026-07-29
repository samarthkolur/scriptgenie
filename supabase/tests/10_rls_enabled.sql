-- Every table in `public` is protected, and every protected table has policies.
--
-- Asserted by enumerating the catalogue rather than by listing the tables this
-- test knows about. A table added by a later migration without RLS fails here
-- on the day it is added; a test that checked a hand-written list would pass
-- and say nothing.

begin;

do $$
declare
  unprotected text[];
begin
  select coalesce(array_agg(tablename order by tablename), '{}')
    into unprotected
  from pg_tables
  where schemaname = 'public'
    and not rowsecurity;

  perform test.equals(
    unprotected,
    '{}'::text[],
    'every table in public has row level security enabled'
  );
end
$$;

do $$
declare
  policyless text[];
begin
  select coalesce(array_agg(t.tablename order by t.tablename), '{}')
    into policyless
  from pg_tables t
  where t.schemaname = 'public'
    and not exists (
      select 1 from pg_policies p
      where p.schemaname = t.schemaname and p.tablename = t.tablename
    );

  -- RLS with no policy denies everything, which is safe but is almost always a
  -- half-finished migration rather than an intention. Anything genuinely
  -- write-closed still carries its SELECT policy, so this stays empty.
  perform test.equals(
    policyless,
    '{}'::text[],
    'every table with RLS enabled also declares at least one policy'
  );
end
$$;

-- The eight tables a signed-in user creates and edits need all four commands.
-- Reference and accounting tables deliberately do not, and are excluded by name
-- with the reason stated rather than by the absence of a check.
do $$
declare
  owned text[] := array[
    'projects', 'constraint_bundles', 'conflict_reports', 'resolutions',
    'scope_envelopes', 'generation_runs', 'plot_variants', 'variant_feedback'
  ];
  table_name text;
  command text;
begin
  foreach table_name in array owned loop
    foreach command in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE'] loop
      perform test.ok(
        exists (
          select 1 from pg_policies
          where schemaname = 'public'
            and tablename = table_name
            and cmd = command
        ),
        format('%s has a %s policy', table_name, command)
      );
    end loop;
  end loop;
end
$$;

-- kb_versions is reference data and usage_events is written by the server. If
-- either ever gains a client write policy, that is a decision someone must
-- make deliberately, and this is where they will be told to.
do $$
begin
  perform test.equals(
    (select count(*)::int from pg_policies
      where schemaname = 'public' and tablename = 'kb_versions' and cmd <> 'SELECT'),
    0,
    'kb_versions exposes no write policy to any client role'
  );
  perform test.equals(
    (select count(*)::int from pg_policies
      where schemaname = 'public' and tablename = 'usage_events' and cmd <> 'SELECT'),
    0,
    'usage_events exposes no write policy to any client role'
  );
  perform test.equals(
    (select count(*)::int from pg_policies
      where schemaname = 'public' and tablename = 'profiles' and cmd in ('INSERT', 'DELETE')),
    0,
    'profiles cannot be created or deleted by a client; the auth trigger owns its lifecycle'
  );
end
$$;

rollback;
