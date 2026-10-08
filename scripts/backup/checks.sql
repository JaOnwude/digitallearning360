-- After a restore: tenant isolation must have come back with the data (spec R1, AC12).
\set ON_ERROR_STOP on
-- 1. Every table with a school_id column has RLS enabled AND forced.
SELECT 'RLS missing on: ' || string_agg(c.relname, ', ')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'school_id' AND NOT a.attisdropped
WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
HAVING count(*) > 0;
-- 2. The app's role sees no student or invoice without a school set.
SET ROLE dl360_app;
SELECT 'isolation broken: app role saw ' || n || ' rows without a school' FROM (
  SELECT (SELECT count(*) FROM students) + (SELECT count(*) FROM invoices) AS n) t WHERE n > 0;
RESET ROLE;
