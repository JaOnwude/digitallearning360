-- Exact row count of every table in public, one "table|count" per line, sorted.
-- Run as a role that bypasses RLS (superuser, or Neon's owner role), or counts read 0.
SELECT c.relname || '|' || (xpath('/row/n/text()',
         query_to_xml(format('SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;
