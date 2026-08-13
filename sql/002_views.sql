-- 002_views.sql — analytics pushed into SQL views.
-- `security_invoker = on` makes every view respect the RLS of its base tables.

-- Events denormalized to the client's external user_id (what the dashboard expects).
create or replace view analytics.v_events with (security_invoker = on) as
select u.external_id as user_id,
       e.event_name,
       e.event_time,
       e.event_time::date as event_date
from analytics.events e
join analytics.users u on u.id = e.user_id and u.organization_id = e.organization_id;

-- Subscriptions with external user_id.
create or replace view analytics.v_subscriptions with (security_invoker = on) as
select u.external_id as user_id,
       s.plan,
       s.mrr,
       s.start_date,
       s.churn_date
from analytics.subscriptions s
join analytics.users u on u.id = s.user_id and u.organization_id = s.organization_id;

-- Activation funnel: distinct users per step.
create or replace view analytics.v_funnel with (security_invoker = on) as
select e.event_name as step,
       count(distinct e.user_id) as users
from analytics.events e
group by e.event_name;

-- Cohort retention raw: cohort month, months-since-signup, distinct active users.
create or replace view analytics.v_retention_raw with (security_invoker = on) as
select date_trunc('month', u.created_at)::date as cohort_month,
       (extract(year from e.event_time) * 12 + extract(month from e.event_time))
         - (extract(year from u.created_at) * 12 + extract(month from u.created_at)) as months_since,
       count(distinct e.user_id) as active_users
from analytics.users u
join analytics.events e on e.user_id = u.id and e.organization_id = u.organization_id
where e.event_name = 'active'
group by 1, 2;

-- Cohort sizes (denominator for retention %).
create or replace view analytics.v_cohort_sizes with (security_invoker = on) as
select date_trunc('month', created_at)::date as cohort_month,
       count(*) as size
from analytics.users
group by 1;

-- Monthly MRR by plan (period derived from actual data).
create or replace view analytics.v_mrr with (security_invoker = on) as
with months as (
  select date_trunc('month', gs)::date as m
  from generate_series(
    (select min(date_trunc('month', start_date::timestamp)) from analytics.subscriptions),
    (select max(date_trunc('month', coalesce(churn_date, current_date)::timestamp)) from analytics.subscriptions),
    interval '1 month'
  ) gs
)
select to_char(m.m, 'YYYY-MM') as month,
       coalesce(sum(s.mrr) filter (where s.plan = 'pro'), 0)        as pro,
       coalesce(sum(s.mrr) filter (where s.plan = 'business'), 0)   as business,
       coalesce(sum(s.mrr) filter (where s.plan = 'enterprise'), 0) as enterprise,
       coalesce(sum(s.mrr), 0)                                       as mrr
from months m
join analytics.subscriptions s
  on date_trunc('month', s.start_date) <= m.m
 and (s.churn_date is null or date_trunc('month', s.churn_date) > m.m)
group by m.m
order by m.m;

-- Signup → paid conversion by acquisition channel.
create or replace view analytics.v_conversion_channel with (security_invoker = on) as
with paid as (
  select distinct user_id from analytics.events where event_name = 'subscribe'
)
select u.properties->>'channel' as channel,
       count(*) as users,
       count(p.user_id) as paid,
       round(count(p.user_id)::numeric / nullif(count(*), 0), 4) as conversion
from analytics.users u
left join paid p on p.user_id = u.id
group by 1;

-- Daily active users.
create or replace view analytics.v_dau with (security_invoker = on) as
select e.event_time::date as day,
       count(distinct e.user_id) as dau
from analytics.events e
where e.event_name = 'active'
group by 1
order by 1;
