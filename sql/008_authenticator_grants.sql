-- 008_authenticator_grants.sql
-- PostgREST connects as the `authenticator` role (then SET ROLE anon/authenticated).
-- On a fresh project the `authenticator` has no USAGE on the custom schemas, so the
-- PostgREST schema cache is built without them even after `api.schemas` is updated.
-- Grant USAGE so the cache can include analytics + experiments objects.

grant usage on schema analytics   to authenticator;
grant usage on schema experiments to authenticator;

notify pgrst, 'reload config';
notify pgrst, 'reload schema';