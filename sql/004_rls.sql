-- 004_rls.sql — Row Level Security + key-gated ingestion function.

-- Enable RLS everywhere.
alter table analytics.organizations enable row level security;
alter table analytics.api_keys        enable row level security;
alter table analytics.users           enable row level security;
alter table analytics.events          enable row level security;
alter table analytics.subscriptions   enable row level security;
alter table analytics.org_members     enable row level security;
alter table experiments.experiments   enable row level security;
alter table experiments.variants      enable row level security;
alter table experiments.assignments   enable row level security;
alter table experiments.metrics       enable row level security;

-- Org ids visible to the current authenticated user.
create or replace function analytics.my_orgs()
returns setof uuid
language sql stable security definer set search_path = public as
$$
  select organization_id from analytics.org_members where user_id = auth.uid();
$$;

-- Members can see their own membership and everything in their orgs.
create policy org_members_select on analytics.org_members
  for select using (user_id = auth.uid() or organization_id in (select analytics.my_orgs()));

create policy orgs_select on analytics.organizations
  for select using (id in (select analytics.my_orgs()));

create policy users_select on analytics.users
  for select using (organization_id in (select analytics.my_orgs()));

create policy events_select on analytics.events
  for select using (organization_id in (select analytics.my_orgs()));

create policy subs_select on analytics.subscriptions
  for select using (organization_id in (select analytics.my_orgs()));

create policy experiments_select on experiments.experiments
  for select using (organization_id in (select analytics.my_orgs()));

create policy variants_select on experiments.variants
  for select using (
    experiment_id in (
      select id from experiments.experiments where organization_id in (select analytics.my_orgs())
    )
  );

create policy assignments_select on experiments.assignments
  for select using (
    experiment_id in (
      select id from experiments.experiments where organization_id in (select analytics.my_orgs())
    )
  );

create policy metrics_select on experiments.metrics
  for select using (
    experiment_id in (
      select id from experiments.experiments where organization_id in (select analytics.my_orgs())
    )
  );

-- api_keys has no policies: with RLS on, default is deny for everyone.
-- Plaintext keys never live in the DB — only the SHA-256 hash.

-- Key-gated ingestion: a security definer function validates the hashed API key
-- and writes on behalf of the client. RLS is bypassed by design, gated by the key.
create or replace function analytics.ingest_event(
  p_key_hash    text,
  p_external_id text,
  p_event_name  text,
  p_properties  jsonb default '{}'::jsonb,
  p_event_time  timestamptz default now()
) returns bigint
language plpgsql security definer set search_path = analytics, public as
$$
declare
  v_org   uuid;
  v_user  bigint;
  v_event bigint;
begin
  select organization_id into v_org
  from api_keys where key_hash = p_key_hash;
  if v_org is null then
    raise exception 'invalid api key';
  end if;

  insert into users (organization_id, external_id, properties)
  values (v_org, p_external_id, coalesce(p_properties, '{}'::jsonb))
  on conflict (organization_id, external_id)
  do update set properties = users.properties || excluded.properties
  returning id into v_user;

  insert into events (organization_id, user_id, event_name, properties, event_time)
  values (v_org, v_user, p_event_name, coalesce(p_properties, '{}'::jsonb), p_event_time)
  returning id into v_event;

  return v_event;
end;
$$;

-- Grants: anon/authenticated can read (RLS filters) and call ingestion.
grant usage on schema analytics  to anon, authenticated;
grant usage on schema experiments to anon, authenticated;

grant select on analytics.organizations,
                    analytics.users,
                    analytics.events,
                    analytics.subscriptions,
                    analytics.org_members,
                    analytics.v_events,
                    analytics.v_subscriptions,
                    analytics.v_funnel,
                    analytics.v_retention_raw,
                    analytics.v_cohort_sizes,
                    analytics.v_mrr,
                    analytics.v_conversion_channel,
                    analytics.v_dau
  to anon, authenticated;

grant select on experiments.experiments,
                    experiments.variants,
                    experiments.assignments,
                    experiments.metrics,
                    experiments.v_results
  to anon, authenticated;

grant execute on function analytics.ingest_event(text, text, text, jsonb, timestamptz)
  to anon, authenticated;
