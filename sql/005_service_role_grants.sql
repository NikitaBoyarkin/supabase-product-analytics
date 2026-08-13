-- 005_service_role_grants.sql
-- Service role (admin/seed) needs explicit grants on custom schemas.
-- RLS migrations (004) grant to anon/authenticated but NOT service_role —
-- without this, the seed script fails with `permission denied for schema X` (42501).

grant usage on schema analytics to service_role;
grant all on all tables in schema analytics to service_role;
grant all on all sequences in schema analytics to service_role;
grant all on all functions in schema analytics to service_role;

grant usage on schema experiments to service_role;
grant all on all tables in schema experiments to service_role;
grant all on all sequences in schema experiments to service_role;
grant all on all functions in schema experiments to service_role;
