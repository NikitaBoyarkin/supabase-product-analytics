-- 003_experiments.sql — A/B experiment schema.

create schema if not exists experiments;

create table if not exists experiments.experiments (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references analytics.organizations(id) on delete cascade,
  name            text not null,
  hypothesis      text,
  status          text not null default 'running',   -- running | paused | concluded
  started_at      timestamptz not null default now(),
  ended_at        timestamptz
);

create table if not exists experiments.variants (
  id              uuid primary key default gen_random_uuid(),
  experiment_id   uuid not null references experiments.experiments(id) on delete cascade,
  key             text not null,
  traffic_weight  numeric not null default 1,
  unique (experiment_id, key)
);

create table if not exists experiments.assignments (
  id            bigint generated always as identity primary key,
  experiment_id uuid not null references experiments.experiments(id) on delete cascade,
  user_id       bigint not null,          -- analytics.users.id
  variant_id    uuid not null references experiments.variants(id) on delete cascade,
  assigned_at   timestamptz not null default now(),
  unique (experiment_id, user_id)
);

create table if not exists experiments.metrics (
  id            bigint generated always as identity primary key,
  experiment_id uuid not null references experiments.experiments(id) on delete cascade,
  assignment_id bigint not null references experiments.assignments(id) on delete cascade,
  metric_name   text not null,            -- e.g. 'conversion'
  value         numeric not null default 0
);

create index if not exists idx_metrics_exp on experiments.metrics (experiment_id);

-- Per-variant result summary computed in SQL.
create or replace view experiments.v_results with (security_invoker = on) as
select x.id   as experiment_id,
       x.name as experiment,
       x.status,
       v.key  as variant,
       count(distinct a.id) as assigned,
       count(distinct m.assignment_id) filter (where m.metric_name = 'conversion' and m.value > 0) as converted,
       round(
         count(distinct m.assignment_id) filter (where m.metric_name = 'conversion' and m.value > 0)::numeric
         / nullif(count(distinct a.id), 0), 4
       ) as conversion
from experiments.experiments x
join experiments.variants v on v.experiment_id = x.id
left join experiments.assignments a on a.variant_id = v.id
left join experiments.metrics m on m.assignment_id = a.id
group by x.id, x.name, x.status, v.key;
