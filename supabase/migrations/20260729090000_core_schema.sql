-- ScriptGenie (CASIE) core schema.
--
-- Migrations are forward-only: this file is never edited once it has been
-- applied anywhere. A correction ships as a later migration, because editing an
-- applied migration makes two databases claiming the same version structurally
-- different, and nothing downstream can then tell them apart.
--
-- Two decisions run through the whole file.
--
-- *Ownership is denormalised onto every user table.* `plot_variants` could
-- reach its owner through `generation_runs` -> `projects`, but an RLS policy
-- that joins is a policy whose cost grows with the table and whose correctness
-- depends on the join staying right through every future migration. A local
-- `owner_id` makes every policy the same single comparison.
--
-- *That denormalised column is pinned by composite foreign keys.* Each parent
-- carries `unique (id, owner_id)` and each child references `(parent_id,
-- owner_id)`. A row therefore cannot name one user's parent while claiming a
-- different owner: it is refused by the constraint, not by application code
-- that has to remember to check. RLS then only has to prove `owner_id =
-- auth.uid()`, and the graph below it is already consistent by construction.
--
-- Constraint payloads are stored as JSONB rather than shredded into columns.
-- The authoritative shapes are the Pydantic domain models in `app/domain`, and a
-- second, drifting statement of them in DDL would be a source of disagreement
-- about what a conflict report is. What is shredded into columns is exactly what
-- the database must filter, sort or enforce on.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- helpers

-- Kept in `public` rather than a private schema so that `supabase db diff`
-- tracks it like any other object.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

comment on function public.set_updated_at() is
  'Stamps updated_at on UPDATE. Applied by trigger so the value cannot be omitted or backdated by a client.';

-- ---------------------------------------------------------------- profiles

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.profiles is
  'One row per authenticated user, created by trigger on auth.users insert.';

-- The profile row is created by a trigger rather than by the application on
-- first request. A user who signs in and never reaches the API would otherwise
-- have no profile, and every later insert referencing it would fail with a
-- foreign key error that says nothing about the real cause.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name, avatar_url)
  values (
    new.id,
    new.email,
    coalesce(
      new.raw_user_meta_data ->> 'full_name',
      new.raw_user_meta_data ->> 'name',
      split_part(new.email, '@', 1)
    ),
    new.raw_user_meta_data ->> 'avatar_url'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

comment on function public.handle_new_user() is
  'Creates the public.profiles row for a new auth.users row. SECURITY DEFINER because auth.users inserts run as the auth admin, which has no rights on public.profiles; search_path is pinned so the definer right cannot be redirected to an attacker-supplied schema.';

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- projects

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  title text not null check (length(btrim(title)) between 1 and 200),
  description text check (length(description) <= 2000),
  status text not null default 'draft'
    check (status in ('draft', 'resolving', 'generating', 'complete', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Referenced by every child's composite foreign key. Redundant with the
  -- primary key for uniqueness; its job is to be a referenceable target.
  constraint projects_id_owner_key unique (id, owner_id)
);

comment on column public.projects.status is
  'Lifecycle marker for the UI. Not a lock: generation eligibility is decided by the conflict report, never by this column.';

-- ---------------------------------------------------------- constraint_bundles

-- The writer's inputs, shredded into columns because the library filters on
-- genre, tier and rating, and because a malformed bundle must be rejected by
-- the database and not only by the API that happened to write it.
create table public.constraint_bundles (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  owner_id uuid not null,
  genre_primary text not null check (genre_primary ~ '^[a-z][a-z0-9_]*$'),
  genre_secondary text check (genre_secondary ~ '^[a-z][a-z0-9_]*$'),
  audience_min_age smallint not null check (audience_min_age between 0 and 120),
  audience_max_age smallint not null check (audience_max_age between 0 and 120),
  rating_system text not null check (rating_system ~ '^[a-z][a-z0-9_]*$'),
  rating_classification text not null check (rating_classification ~ '^[a-z][a-z0-9_]*$'),
  budget_tier_id text not null check (budget_tier_id ~ '^[a-z][a-z0-9_]*$'),
  territory_ids text[] not null check (cardinality(territory_ids) >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint audience_band_ordered check (audience_max_age >= audience_min_age),
  constraint secondary_genre_differs check (genre_secondary is distinct from genre_primary),
  constraint constraint_bundles_id_owner_key unique (id, owner_id),
  constraint constraint_bundles_project_fkey
    foreign key (project_id, owner_id)
    references public.projects (id, owner_id) on delete cascade
);

-- ------------------------------------------------------------ conflict_reports

create table public.conflict_reports (
  id uuid primary key default gen_random_uuid(),
  bundle_id uuid not null,
  project_id uuid not null,
  owner_id uuid not null,
  kb_version text not null,
  rules_evaluated integer not null default 0 check (rules_evaluated >= 0),
  conflicts jsonb not null default '[]'::jsonb check (jsonb_typeof(conflicts) = 'array'),
  hard_count integer not null default 0 check (hard_count >= 0),
  soft_count integer not null default 0 check (soft_count >= 0),
  advisory_count integer not null default 0 check (advisory_count >= 0),
  created_at timestamptz not null default now(),
  constraint conflict_reports_id_owner_key unique (id, owner_id),
  constraint conflict_reports_bundle_fkey
    foreign key (bundle_id, owner_id)
    references public.constraint_bundles (id, owner_id) on delete cascade,
  constraint conflict_reports_project_fkey
    foreign key (project_id, owner_id)
    references public.projects (id, owner_id) on delete cascade
);

comment on column public.conflict_reports.kb_version is
  'The knowledge base version that produced this verdict. A report without it cannot be explained once the knowledge base moves on.';

comment on column public.conflict_reports.hard_count is
  'Severity counts are stored rather than derived on read: the generation endpoint gates on "any unresolved HARD", and that question must not require unpacking a JSONB array on every request.';

-- ---------------------------------------------------------------- resolutions

create table public.resolutions (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null,
  project_id uuid not null,
  owner_id uuid not null,
  rule_id text not null check (rule_id ~ '^[a-z][a-z0-9_]*$'),
  resolution_id text not null check (resolution_id ~ '^[a-z][a-z0-9_]*$'),
  delta jsonb not null default '{}'::jsonb check (jsonb_typeof(delta) = 'object'),
  created_at timestamptz not null default now(),
  -- One answer per conflict per report. A second answer is an update, not an
  -- additional choice, and without this the audit trail would record two
  -- contradictory decisions with no way to tell which one was applied.
  constraint one_choice_per_rule unique (report_id, rule_id),
  constraint resolutions_report_fkey
    foreign key (report_id, owner_id)
    references public.conflict_reports (id, owner_id) on delete cascade,
  constraint resolutions_project_fkey
    foreign key (project_id, owner_id)
    references public.projects (id, owner_id) on delete cascade
);

-- ------------------------------------------------------------- scope_envelopes

create table public.scope_envelopes (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null,
  project_id uuid not null,
  owner_id uuid not null,
  kb_version text not null,
  envelope jsonb not null check (jsonb_typeof(envelope) = 'object'),
  created_at timestamptz not null default now(),
  constraint scope_envelopes_id_owner_key unique (id, owner_id),
  constraint scope_envelopes_report_fkey
    foreign key (report_id, owner_id)
    references public.conflict_reports (id, owner_id) on delete cascade,
  constraint scope_envelopes_project_fkey
    foreign key (project_id, owner_id)
    references public.projects (id, owner_id) on delete cascade
);

comment on table public.scope_envelopes is
  'The parameterised bounds handed to generation. Stored because a variant is only defensible against the envelope it was actually generated for, and re-deriving it later would use whatever the knowledge base says today.';

-- ------------------------------------------------------------- generation_runs

create table public.generation_runs (
  id uuid primary key default gen_random_uuid(),
  envelope_id uuid not null,
  project_id uuid not null,
  owner_id uuid not null,
  status text not null default 'running'
    check (status in ('running', 'complete', 'partial', 'failed')),
  requested_count smallint not null check (requested_count between 1 and 10),
  generated_count smallint not null default 0 check (generated_count >= 0),
  failed_count smallint not null default 0 check (failed_count >= 0),
  seed integer not null default 0,
  model text not null,
  prompt_version text not null,
  kb_version text not null,
  elapsed_ms double precision check (elapsed_ms >= 0),
  failures jsonb not null default '[]'::jsonb check (jsonb_typeof(failures) = 'array'),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint generation_runs_id_owner_key unique (id, owner_id),
  constraint generation_runs_envelope_fkey
    foreign key (envelope_id, owner_id)
    references public.scope_envelopes (id, owner_id) on delete cascade,
  constraint generation_runs_project_fkey
    foreign key (project_id, owner_id)
    references public.projects (id, owner_id) on delete cascade
);

comment on column public.generation_runs.failures is
  'Per-variant failure reasons. A partially successful batch is a normal outcome, and the caller is owed the reason for what it did not get.';

-- --------------------------------------------------------------- plot_variants

create table public.plot_variants (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  project_id uuid not null,
  owner_id uuid not null,
  variant_index smallint not null check (variant_index >= 0),
  archetype_id text not null check (archetype_id ~ '^[a-z][a-z0-9_]*$'),
  title text not null check (length(btrim(title)) >= 1),
  logline text not null check (length(btrim(logline)) >= 1),
  beats jsonb not null check (jsonb_typeof(beats) = 'array' and jsonb_array_length(beats) >= 1),
  locations text[] not null default '{}',
  named_characters text[] not null default '{}',
  relaxations text[] not null default '{}',
  satisfaction jsonb not null default '{}'::jsonb check (jsonb_typeof(satisfaction) = 'object'),
  verdicts jsonb not null default '{}'::jsonb check (jsonb_typeof(verdicts) = 'object'),
  surfaceable boolean not null default false,
  favourite boolean not null default false,
  notes text check (length(notes) <= 4000),
  provenance jsonb not null default '{}'::jsonb check (jsonb_typeof(provenance) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint one_variant_per_index_per_run unique (run_id, variant_index),
  constraint plot_variants_id_owner_key unique (id, owner_id),
  constraint plot_variants_run_fkey
    foreign key (run_id, owner_id)
    references public.generation_runs (id, owner_id) on delete cascade,
  constraint plot_variants_project_fkey
    foreign key (project_id, owner_id)
    references public.projects (id, owner_id) on delete cascade
);

comment on column public.plot_variants.surfaceable is
  'Whether every verification axis returned PASS. Stored as the verifier decided it, so a UI cannot re-derive it more generously; FLAGGED and NEEDS_REVIEW both make it false.';

-- ------------------------------------------------------------ variant_feedback

create table public.variant_feedback (
  id uuid primary key default gen_random_uuid(),
  variant_id uuid not null,
  owner_id uuid not null,
  rating smallint check (rating between 1 and 5),
  notes text check (length(notes) <= 4000),
  -- The false-positive channel. Research risk 1 is that the rule set flags
  -- tensions that working writers do not recognise; without a first-class way
  -- to say so, that evidence never reaches the knowledge base.
  false_positive_rule_id text check (false_positive_rule_id ~ '^[a-z][a-z0-9_]*$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint feedback_says_something check (
    rating is not null or notes is not null or false_positive_rule_id is not null
  ),
  constraint variant_feedback_variant_fkey
    foreign key (variant_id, owner_id)
    references public.plot_variants (id, owner_id) on delete cascade
);

-- ---------------------------------------------------------------- kb_versions

-- Reference data, not user data: every authenticated user reads the same rows
-- and nobody writes them through the API. It carries no owner_id, and its
-- policies say exactly that rather than leaving the table unprotected.
create table public.kb_versions (
  version text primary key,
  rule_count integer not null check (rule_count >= 0),
  released_at timestamptz not null default now(),
  notes text
);

-- --------------------------------------------------------------- usage_events

-- Written by the API under the service role and never by a client, so its
-- parents are plain single-column references: the composite pinning above
-- exists to stop clients lying about ownership, and no client writes here.
create table public.usage_events (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  project_id uuid references public.projects (id) on delete set null,
  run_id uuid references public.generation_runs (id) on delete set null,
  event_type text not null check (event_type in ('generation', 'verification')),
  model text not null,
  prompt_tokens integer not null default 0 check (prompt_tokens >= 0),
  completion_tokens integer not null default 0 check (completion_tokens >= 0),
  cost_usd numeric(12, 6) check (cost_usd >= 0),
  created_at timestamptz not null default now()
);

comment on column public.usage_events.cost_usd is
  'Nullable on purpose. A model with no published price yields no estimate, and a zero would be summed into a total that reads as free.';

comment on column public.usage_events.project_id is
  'ON DELETE SET NULL, not CASCADE: deleting a project must not erase the record that its generation spent tokens.';

-- ------------------------------------------------------------------ triggers

create trigger set_updated_at_profiles
  before update on public.profiles
  for each row execute function public.set_updated_at();

create trigger set_updated_at_projects
  before update on public.projects
  for each row execute function public.set_updated_at();

create trigger set_updated_at_constraint_bundles
  before update on public.constraint_bundles
  for each row execute function public.set_updated_at();

create trigger set_updated_at_plot_variants
  before update on public.plot_variants
  for each row execute function public.set_updated_at();

create trigger set_updated_at_variant_feedback
  before update on public.variant_feedback
  for each row execute function public.set_updated_at();

-- ------------------------------------------------------------------- indexes

-- Every child table is read as "everything in this project, newest first", and
-- every table is filtered by owner before anything else because RLS adds that
-- predicate whether the query mentions it or not.
create index projects_owner_created_idx
  on public.projects (owner_id, created_at desc);
create index projects_owner_status_idx
  on public.projects (owner_id, status);

create index constraint_bundles_project_created_idx
  on public.constraint_bundles (project_id, created_at desc);
create index constraint_bundles_owner_idx
  on public.constraint_bundles (owner_id);

create index conflict_reports_project_created_idx
  on public.conflict_reports (project_id, created_at desc);
create index conflict_reports_owner_idx
  on public.conflict_reports (owner_id);
create index conflict_reports_bundle_idx
  on public.conflict_reports (bundle_id);

create index resolutions_report_idx
  on public.resolutions (report_id);
create index resolutions_owner_idx
  on public.resolutions (owner_id);

create index scope_envelopes_project_created_idx
  on public.scope_envelopes (project_id, created_at desc);
create index scope_envelopes_owner_idx
  on public.scope_envelopes (owner_id);
create index scope_envelopes_report_idx
  on public.scope_envelopes (report_id);

create index generation_runs_project_created_idx
  on public.generation_runs (project_id, created_at desc);
-- The rate limiter counts a user's runs inside a rolling window, so owner and
-- time are the whole predicate.
create index generation_runs_owner_created_idx
  on public.generation_runs (owner_id, created_at desc);
create index generation_runs_envelope_idx
  on public.generation_runs (envelope_id);

create index plot_variants_run_index_idx
  on public.plot_variants (run_id, variant_index);
create index plot_variants_project_created_idx
  on public.plot_variants (project_id, created_at desc);
create index plot_variants_owner_idx
  on public.plot_variants (owner_id);

create index variant_feedback_variant_idx
  on public.variant_feedback (variant_id);
create index variant_feedback_owner_created_idx
  on public.variant_feedback (owner_id, created_at desc);
-- Partial: the false-positive review reads only the rows that name a rule, and
-- those are a small minority of feedback.
create index variant_feedback_false_positive_idx
  on public.variant_feedback (false_positive_rule_id)
  where false_positive_rule_id is not null;

create index usage_events_owner_created_idx
  on public.usage_events (owner_id, created_at desc);
create index usage_events_run_idx
  on public.usage_events (run_id);
