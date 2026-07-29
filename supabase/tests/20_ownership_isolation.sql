-- Two users, one database, and no path between them.
--
-- The acceptance criterion for this stage is that a select as user A returns
-- zero rows from user B's projects. That is the first assertion here; the rest
-- close the ways an application could still leak across the boundary — writing
-- a row under someone else's name, hanging a child off someone else's parent,
-- or reaching a variant through a run that is not yours.

begin;

-- Fixtures are created as the owning role, which bypasses RLS. That is the
-- point: the rows genuinely exist, so the assertions below are about what the
-- policies hide, not about what was never inserted.
insert into auth.users (id, email, raw_user_meta_data)
values
  ('11111111-1111-4111-8111-111111111111', 'ada@example.test',
   '{"full_name": "Ada", "avatar_url": "https://example.test/ada.png"}'::jsonb),
  ('22222222-2222-4222-8222-222222222222', 'grace@example.test',
   '{"name": "Grace"}'::jsonb);

insert into public.projects (id, owner_id, title)
values
  ('aaaaaaaa-0000-4000-8000-000000000001',
   '11111111-1111-4111-8111-111111111111', 'Ada: cabin horror comedy'),
  ('bbbbbbbb-0000-4000-8000-000000000001',
   '22222222-2222-4222-8222-222222222222', 'Grace: submarine thriller');

insert into public.constraint_bundles (
  id, project_id, owner_id, genre_primary, genre_secondary,
  audience_min_age, audience_max_age, rating_system, rating_classification,
  budget_tier_id, territory_ids
)
values (
  'bbbbbbbb-0000-4000-8000-000000000002',
  'bbbbbbbb-0000-4000-8000-000000000001',
  '22222222-2222-4222-8222-222222222222',
  'thriller', null, 16, 45, 'mpa', 'pg_13', 'micro', array['us']
);

-- ------------------------------------------------------- the stated criterion

do $$
begin
  perform test.become('11111111-1111-4111-8111-111111111111');

  perform test.equals(
    (select count(*)::int from public.projects
      where owner_id = '22222222-2222-4222-8222-222222222222'),
    0,
    'user A selecting user B''s projects by owner_id returns zero rows'
  );

  perform test.equals(
    (select count(*)::int from public.projects),
    1,
    'an unfiltered select returns only user A''s own project'
  );

  perform test.equals(
    (select count(*)::int from public.projects
      where id = 'bbbbbbbb-0000-4000-8000-000000000001'),
    0,
    'knowing user B''s project id does not make it readable'
  );

  perform test.equals(
    (select count(*)::int from public.constraint_bundles),
    0,
    'user B''s constraint bundle is invisible to user A'
  );

  perform test.become_owner();
end
$$;

-- ------------------------------------------------------------ writing as A

do $$
declare
  new_project uuid;
begin
  perform test.become('11111111-1111-4111-8111-111111111111');

  perform test.ok(
    test.is_rejected($stmt$
      insert into public.projects (owner_id, title)
      values ('22222222-2222-4222-8222-222222222222', 'filed under Grace')
    $stmt$),
    'user A cannot insert a project owned by user B'
  );

  perform test.ok(
    test.is_rejected($stmt$
      insert into public.constraint_bundles (
        project_id, owner_id, genre_primary, audience_min_age, audience_max_age,
        rating_system, rating_classification, budget_tier_id, territory_ids
      ) values (
        'bbbbbbbb-0000-4000-8000-000000000001',
        '11111111-1111-4111-8111-111111111111',
        'horror', 15, 40, 'mpa', 'r', 'micro', array['us']
      )
    $stmt$),
    'user A cannot attach a bundle to user B''s project even under their own name'
  );

  -- The composite foreign key is what refuses this one, before RLS is reached:
  -- there is no (id, owner_id) pair matching B's project and A's user.
  perform test.ok(
    test.is_rejected($stmt$
      update public.projects
      set owner_id = '22222222-2222-4222-8222-222222222222'
      where owner_id = '11111111-1111-4111-8111-111111111111'
    $stmt$),
    'user A cannot hand their own project to user B'
  );

  -- A legitimate write still works. Without this the assertions above would
  -- also pass against a policy that simply denied everything.
  insert into public.projects (owner_id, title)
  values ('11111111-1111-4111-8111-111111111111', 'Ada: second project')
  returning id into new_project;

  perform test.ok(new_project is not null, 'user A can create their own project');

  perform test.equals(
    (select count(*)::int from public.projects), 2,
    'user A now sees exactly their own two projects'
  );

  perform test.become_owner();
end
$$;

-- ------------------------------------------------------------ deletes as B

do $$
begin
  perform test.become('22222222-2222-4222-8222-222222222222');

  delete from public.projects where owner_id = '11111111-1111-4111-8111-111111111111';

  perform test.become_owner();

  perform test.equals(
    (select count(*)::int from public.projects
      where owner_id = '11111111-1111-4111-8111-111111111111'),
    2,
    'a delete aimed at another user''s rows removes nothing'
  );
end
$$;

-- ------------------------------------------------- server-written accounting

do $$
begin
  perform test.become('11111111-1111-4111-8111-111111111111');

  perform test.ok(
    test.is_rejected($stmt$
      insert into public.usage_events (owner_id, event_type, model, prompt_tokens)
      values ('11111111-1111-4111-8111-111111111111', 'generation', 'openai/gpt-oss-120b', 0)
    $stmt$),
    'a client cannot write its own usage accounting'
  );

  perform test.ok(
    test.is_rejected($stmt$
      insert into public.kb_versions (version, rule_count) values ('9.9.9', 0)
    $stmt$),
    'a client cannot invent a knowledge base version'
  );

  perform test.become_owner();
end
$$;

-- ----------------------------------------------------- reference data is read

insert into public.kb_versions (version, rule_count, notes)
values ('0.1.1', 27, 'Phase 1 rule set');

do $$
begin
  perform test.become('11111111-1111-4111-8111-111111111111');
  perform test.equals(
    (select rule_count from public.kb_versions where version = '0.1.1'),
    27,
    'every authenticated user reads the shared knowledge base versions'
  );
  perform test.become_owner();
end
$$;

-- --------------------------------------------------------- unauthenticated

-- `anon` is refused before RLS is consulted, because it holds no grant on the
-- user tables at all. Two independent barriers, and this asserts the outer one:
-- a policy mistake alone cannot expose these tables to a signed-out visitor.
do $$
begin
  set local role anon;
  perform test.ok(
    test.is_rejected('select count(*) from public.projects'),
    'an anonymous session is refused the projects table outright'
  );
  perform test.ok(
    test.is_rejected('select count(*) from public.plot_variants'),
    'an anonymous session is refused generated variants outright'
  );
  perform test.equals(
    (select count(*)::int from public.kb_versions), 1,
    'an anonymous session may still read knowledge base versions'
  );
  reset role;
end
$$;

rollback;
