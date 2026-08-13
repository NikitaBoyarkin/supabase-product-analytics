-- 001_schema.sql — Product Analytics core schema.
-- Namespaced under `analytics` to keep the demo isolated from any legacy tables.

create schema if not exists analytics;

-- Tenant / workspace.
create table if not exists analytics.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

-- API keys: only the SHA-256 hash is stored, never the plaintext key.
create table if not exists analytics.api_keys (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references analytics.organizations(id) on delete cascade,
  key_hash        text not null unique,
  name            text,
  created_at      timestamptz not null default now()
);

-- Tracked end-users of the client product (NOT Supabase Auth users).
create table if not exists analytics.users (
  id              bigint generated always as identity primary key,
  organization_id uuid not null references analytics.organizations(id) on delete cascade,
  external_id     text not null,
  properties      jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  unique (organization_id, external_id)
);

-- Raw event stream.
create table if not exists analytics.events (
  id              bigint generated always as identity primary key,
  organization_id uuid not null references analytics.organizations(id) on delete cascade,
  user_id         bigint not null references analytics.users(id) on delete cascade,
  event_name      text not null,
  properties      jsonb not null default '{}'::jsonb,
  event_time      timestamptz not null default now()
);

create index if not exists idx_events_org_name_time on analytics.events (organization_id, event_name, event_time);
create index if not exists idx_events_org_user     on analytics.events (organization_id, user_id);

-- Paid subscriptions (revenue model).
create table if not exists analytics.subscriptions (
  id              bigint generated always as identity primary key,
  organization_id uuid not null references analytics.organizations(id) on delete cascade,
  user_id         bigint not null references analytics.users(id) on delete cascade,
  plan            text not null,
  mrr             numeric not null check (mrr >= 0),
  start_date      date not null,
  churn_date      date
);

create index if not exists idx_subs_org_start on analytics.subscriptions (organization_id, start_date);

-- Links Supabase Auth users to an organization; drives every RLS policy.
create table if not exists analytics.org_members (
  user_id         uuid not null references auth.users(id) on delete cascade,
  organization_id uuid not null references analytics.organizations(id) on delete cascade,
  role            text not null default 'member',
  primary key (user_id, organization_id)
);
