-- 007_expose_schemas_clean.sql — same as 006 but with a comma-separated value
-- without spaces (PostgREST parses pgrst.db_schemas by commas; some versions
-- don't trim whitespace, so a space-containing list silently exposes nothing).

alter role authenticator set pgrst.db_schemas = 'public,analytics,experiments';
notify pgrst, 'reload config';
notify pgrst, 'reload schema';