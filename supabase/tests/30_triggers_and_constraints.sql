-- The rules the database enforces on its own, with no application in the loop.
--
-- Everything here is a rule the API also checks. That is not duplication for
-- its own sake: the API is one of several things that will eventually write to
-- this database — a migration, a backfill script, a support query — and a rule
-- that only exists in Python is a rule those writers do not have.

begin;

-- ------------------------------------------------- profile creation on signup

do $$
declare
  profile public.profiles;
begin
  insert into auth.users (id, email, raw_user_meta_data)
  values ('33333333-3333-4333-8333-333333333333', 'alan@example.test',
          '{"full_name": "Alan Turing", "avatar_url": "https://example.test/alan.png"}'::jsonb);

  select * into profile from public.profiles
  where id = '33333333-3333-4333-8333-333333333333';

  perform test.ok(profile.id is not null, 'signing up creates a profile row');
  perform test.equals(profile.email, 'alan@example.test', 'the profile carries the auth email');
  perform test.equals(profile.display_name, 'Alan Turing',
    'display_name comes from the Google full_name claim');
  perform test.equals(profile.avatar_url, 'https://example.test/alan.png',
    'avatar_url comes from the Google avatar claim');
end
$$;

-- Google returns `name` where other providers return `full_name`, and a
-- provider that returns neither must still yield a usable display name rather
-- than a null the UI has to special-case.
do $$
begin
  insert into auth.users (id, email, raw_user_meta_data)
  values ('44444444-4444-4444-8444-444444444444', 'katherine@example.test',
          '{"name": "Katherine Johnson"}'::jsonb);
  perform test.equals(
    (select display_name from public.profiles
      where id = '44444444-4444-4444-8444-444444444444'),
    'Katherine Johnson',
    'display_name falls back to the name claim'
  );

  insert into auth.users (id, email) values
    ('55555555-5555-4555-8555-555555555555', 'margaret@example.test');
  perform test.equals(
    (select display_name from public.profiles
      where id = '55555555-5555-4555-8555-555555555555'),
    'margaret',
    'display_name falls back to the local part of the email'
  );
end
$$;

-- ---------------------------------------------------------- updated_at stamps

-- The property under test is that the *trigger* decides this column, not the
-- writer. It is deliberately not "the value increased": `now()` is fixed for
-- the life of a transaction, and these tests run inside one, so a strict
-- increase is unobservable here and asserting it would only be asserting that
-- the test committed.
do $$
declare
  project_id uuid;
  backdated constant timestamptz := timestamptz '2000-01-01 00:00:00+00';
  stamp timestamptz;
begin
  insert into public.projects (owner_id, title)
  values ('33333333-3333-4333-8333-333333333333', 'Turing: codebreaker drama')
  returning id into project_id;

  update public.projects
  set title = 'Turing: codebreaker drama, second pass',
      updated_at = backdated
  where id = project_id
  returning updated_at into stamp;

  perform test.ok(stamp <> backdated, 'a client-supplied updated_at is discarded');
  perform test.equals(stamp, now(), 'updated_at is stamped by the trigger at write time');
end
$$;

-- --------------------------------------------------------- domain constraints

do $$
declare
  owner uuid := '33333333-3333-4333-8333-333333333333';
  project uuid;
begin
  select id into project from public.projects where owner_id = owner limit 1;

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.constraint_bundles (
        project_id, owner_id, genre_primary, audience_min_age, audience_max_age,
        rating_system, rating_classification, budget_tier_id, territory_ids
      ) values (%L, %L, 'drama', 40, 18, 'mpa', 'r', 'low_indie', array['us'])
    $stmt$, project, owner)),
    'an audience band whose maximum is below its minimum is refused'
  );

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.constraint_bundles (
        project_id, owner_id, genre_primary, genre_secondary,
        audience_min_age, audience_max_age,
        rating_system, rating_classification, budget_tier_id, territory_ids
      ) values (%L, %L, 'drama', 'drama', 18, 40, 'mpa', 'r', 'low_indie', array['us'])
    $stmt$, project, owner)),
    'a secondary genre equal to the primary is refused'
  );

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.constraint_bundles (
        project_id, owner_id, genre_primary, audience_min_age, audience_max_age,
        rating_system, rating_classification, budget_tier_id, territory_ids
      ) values (%L, %L, 'drama', 18, 40, 'mpa', 'r', 'low_indie', array[]::text[])
    $stmt$, project, owner)),
    'a bundle releasing in no territory at all is refused'
  );

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.constraint_bundles (
        project_id, owner_id, genre_primary, audience_min_age, audience_max_age,
        rating_system, rating_classification, budget_tier_id, territory_ids
      ) values (%L, %L, 'Drama Thriller', 18, 40, 'mpa', 'r', 'low_indie', array['us'])
    $stmt$, project, owner)),
    'a genre id that could never match a knowledge base row is refused at write time'
  );

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.projects (owner_id, title, status) values (%L, 'Bad status', 'shipped')
    $stmt$, owner)),
    'a project status outside the declared lifecycle is refused'
  );

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.projects (owner_id, title) values (%L, '   ')
    $stmt$, owner)),
    'a whitespace-only project title is refused'
  );
end
$$;

-- -------------------------------------------------------- feedback must speak

do $$
declare
  owner uuid := '33333333-3333-4333-8333-333333333333';
  project uuid;
  bundle uuid;
  report uuid;
  envelope uuid;
  run uuid;
  variant uuid;
begin
  select id into project from public.projects where owner_id = owner limit 1;

  insert into public.constraint_bundles (
    project_id, owner_id, genre_primary, audience_min_age, audience_max_age,
    rating_system, rating_classification, budget_tier_id, territory_ids
  ) values (project, owner, 'drama', 18, 55, 'mpa', 'r', 'low_indie', array['us'])
  returning id into bundle;

  insert into public.conflict_reports (bundle_id, project_id, owner_id, kb_version, rules_evaluated)
  values (bundle, project, owner, '0.1.1', 27)
  returning id into report;

  insert into public.scope_envelopes (report_id, project_id, owner_id, kb_version, envelope)
  values (report, project, owner, '0.1.1', '{"scope": {"max_locations": 6}}'::jsonb)
  returning id into envelope;

  insert into public.generation_runs (
    envelope_id, project_id, owner_id, requested_count, model, prompt_version, kb_version
  ) values (envelope, project, owner, 5, 'openai/gpt-oss-120b', '1.0.0', '0.1.1')
  returning id into run;

  insert into public.plot_variants (
    run_id, project_id, owner_id, variant_index, archetype_id, title, logline, beats
  ) values (
    run, project, owner, 0, 'chamber_piece', 'Room 14',
    'Two codebreakers argue through one night.',
    '[{"index": 0, "function": "setup", "summary": "The room is locked."}]'::jsonb
  )
  returning id into variant;

  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.variant_feedback (variant_id, owner_id) values (%L, %L)
    $stmt$, variant, owner)),
    'feedback carrying neither a rating, a note nor a false-positive report is refused'
  );

  insert into public.variant_feedback (variant_id, owner_id, false_positive_rule_id)
  values (variant, owner, 'horror_comedy_tonal_pressure');

  perform test.equals(
    (select false_positive_rule_id from public.variant_feedback where variant_id = variant),
    'horror_comedy_tonal_pressure',
    'a false-positive report against a named rule is recorded'
  );

  -- Two variants cannot claim the same slot in one batch. Without this, a retry
  -- that partially succeeded would leave a run with two "variant 0"s and no way
  -- to say which the writer saw.
  perform test.ok(
    test.is_rejected(format($stmt$
      insert into public.plot_variants (
        run_id, project_id, owner_id, variant_index, archetype_id, title, logline, beats
      ) values (
        %L, %L, %L, 0, 'chamber_piece', 'Room 14 again', 'A duplicate slot.',
        '[{"index": 0, "function": "setup", "summary": "Again."}]'::jsonb
      )
    $stmt$, run, project, owner)),
    'a second variant at the same index in one run is refused'
  );

  -- Deleting the project must not erase the record that its generation spent
  -- tokens, which is why usage_events nulls the reference instead of cascading.
  insert into public.usage_events (owner_id, project_id, run_id, event_type, model, prompt_tokens, completion_tokens, cost_usd)
  values (owner, project, run, 'generation', 'openai/gpt-oss-120b', 1200, 900, 0.000720);

  delete from public.projects where id = project;

  perform test.equals(
    (select count(*)::int from public.usage_events where owner_id = owner), 1,
    'usage accounting survives the deletion of the project it billed'
  );
  perform test.equals(
    (select project_id from public.usage_events where owner_id = owner), null::uuid,
    'the deleted project reference is nulled rather than cascaded'
  );
  perform test.equals(
    (select count(*)::int from public.plot_variants where owner_id = owner), 0,
    'the variants of a deleted project are removed with it'
  );
end
$$;

rollback;
