-- Runs once on a fresh local database (docker-entrypoint-initdb.d) and in tests.
-- The app connects as dl360_app: not a superuser and cannot bypass RLS (spec R1).
-- Tables are created by migrations running as the owner (the role executing this script).
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dl360_app') THEN
    CREATE ROLE dl360_app LOGIN PASSWORD 'dl360_app' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO dl360_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dl360_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO dl360_app;
