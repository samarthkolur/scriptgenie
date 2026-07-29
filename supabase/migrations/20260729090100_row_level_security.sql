-- Row level security for every table in `public`.
--
-- RLS is the last line that holds when application code is wrong. The API in
-- `apps/api` calls PostgREST with the *caller's* JWT rather than the service
-- role for everything a user owns, so a repository that forgets its `owner_id`
-- filter returns nothing instead of returning somebody else's work. That only
-- holds if the policies below are complete, which is why the tests in
-- `supabase/tests/` assert `rowsecurity` across `pg_tables` rather than
-- checking the tables someone remembered to list.
--
-- Three shapes of table, and each says which it is:
--
-- 1. *Owned* tables. `owner_id = auth.uid()` on read, and the same as a WITH
--    CHECK on write, so a row can be neither read nor created for anyone else.
--    The composite foreign keys in the previous migration already pin
--    `owner_id` to the parent's, so this single comparison is sufficient.
-- 2. *Reference* data (`kb_versions`). Readable by every authenticated session,
--    writable by nobody: there is no write policy, which denies writes to every
--    role that does not bypass RLS.
-- 3. *Server-written* data (`usage_events`). Readable by its owner so a user can
--    see their own spend, and written only by the service role. No insert
--    policy exists, so a client cannot forge or suppress an accounting row.
--
-- `(select auth.uid())` rather than a bare `auth.uid()`: the subquery form is
-- evaluated once as an initplan instead of once per row, which is the
-- difference between a policy that scales and one that does not.

-- ----------------------------------------------------------------- enable

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.constraint_bundles enable row level security;
alter table public.conflict_reports enable row level security;
alter table public.resolutions enable row level security;
alter table public.scope_envelopes enable row level security;
alter table public.generation_runs enable row level security;
alter table public.plot_variants enable row level security;
alter table public.variant_feedback enable row level security;
alter table public.kb_versions enable row level security;
alter table public.usage_events enable row level security;

-- ----------------------------------------------------------------- grants

-- Stated explicitly rather than inherited from default privileges, so the file
-- is a complete account of who may touch what. A policy grants nothing on its
-- own: without the GRANT the role is refused before RLS is consulted, and
-- without the policy the GRANT returns zero rows.
grant usage on schema public to anon, authenticated;

grant select, insert, update, delete on
  public.projects,
  public.constraint_bundles,
  public.conflict_reports,
  public.resolutions,
  public.scope_envelopes,
  public.generation_runs,
  public.plot_variants,
  public.variant_feedback
to authenticated;

-- A profile is created by trigger and deleted with the auth user. The client
-- may read it and rename itself, and nothing more.
grant select, update on public.profiles to authenticated;

grant select on public.kb_versions to anon, authenticated;
grant select on public.usage_events to authenticated;

-- ---------------------------------------------------------------- profiles

create policy profiles_select_own on public.profiles
  for select to authenticated
  using (id = (select auth.uid()));

create policy profiles_update_own on public.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

-- ---------------------------------------------------------------- projects

create policy projects_select_own on public.projects
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy projects_insert_own on public.projects
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy projects_update_own on public.projects
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy projects_delete_own on public.projects
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ---------------------------------------------------------- constraint_bundles

create policy constraint_bundles_select_own on public.constraint_bundles
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy constraint_bundles_insert_own on public.constraint_bundles
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy constraint_bundles_update_own on public.constraint_bundles
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy constraint_bundles_delete_own on public.constraint_bundles
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ------------------------------------------------------------ conflict_reports

create policy conflict_reports_select_own on public.conflict_reports
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy conflict_reports_insert_own on public.conflict_reports
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy conflict_reports_update_own on public.conflict_reports
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy conflict_reports_delete_own on public.conflict_reports
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ---------------------------------------------------------------- resolutions

create policy resolutions_select_own on public.resolutions
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy resolutions_insert_own on public.resolutions
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy resolutions_update_own on public.resolutions
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy resolutions_delete_own on public.resolutions
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ------------------------------------------------------------- scope_envelopes

create policy scope_envelopes_select_own on public.scope_envelopes
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy scope_envelopes_insert_own on public.scope_envelopes
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy scope_envelopes_update_own on public.scope_envelopes
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy scope_envelopes_delete_own on public.scope_envelopes
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ------------------------------------------------------------- generation_runs

create policy generation_runs_select_own on public.generation_runs
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy generation_runs_insert_own on public.generation_runs
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy generation_runs_update_own on public.generation_runs
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy generation_runs_delete_own on public.generation_runs
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- --------------------------------------------------------------- plot_variants

create policy plot_variants_select_own on public.plot_variants
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy plot_variants_insert_own on public.plot_variants
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy plot_variants_update_own on public.plot_variants
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy plot_variants_delete_own on public.plot_variants
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ------------------------------------------------------------ variant_feedback

create policy variant_feedback_select_own on public.variant_feedback
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy variant_feedback_insert_own on public.variant_feedback
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy variant_feedback_update_own on public.variant_feedback
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy variant_feedback_delete_own on public.variant_feedback
  for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ---------------------------------------------------------------- kb_versions

-- Read-only reference data. Deliberately no insert, update or delete policy:
-- the knowledge base ships with the repository, and a row here is a record of
-- what was released, not something a session may edit.
create policy kb_versions_select_all on public.kb_versions
  for select to anon, authenticated
  using (true);

-- --------------------------------------------------------------- usage_events

-- Readable by the user it bills, written only under the service role. A client
-- that could insert here could understate its own spend, and one that could
-- delete could erase the evidence of a rate limit it exceeded.
create policy usage_events_select_own on public.usage_events
  for select to authenticated
  using (owner_id = (select auth.uid()));
