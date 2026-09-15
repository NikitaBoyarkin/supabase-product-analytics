-- 006_expose_schemas.sql — expose the analytics + experiments schemas via PostgREST.
-- A fresh Supabase project exposes only `public` (and graphql_public) by default.
-- The dashboard / Management API toggles `pgrst.db_schemas` on the `authenticator`
-- role; this migration does the same in SQL so a new project is reproducible from
-- migrations alone (no manual dashboard step).

alter role authenticator set pgrst.db_schemas = 'public, analytics, experiments';
notify pgrst, 'reload config';
notify pgrst, 'reload schema';
