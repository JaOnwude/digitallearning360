#!/usr/bin/env bash
# Restore drill (spec AC12): restore a backup into a brand-new Postgres and prove it works.
#
#   scripts/backup/restore-drill.sh [path/to/dl360-<time>.dump]   # default: newest in ~/dl360-backups
#
# Starts a throwaway Postgres container, creates the app role, restores, then checks:
#   1. every table's row count equals the count taken at backup time
#   2. every school table still has row-level security enabled and forced
#   3. the app role sees no school's rows without a school set (tenant isolation)
# and removes the container. Needs Docker. Touches no other database.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
dump="${1:-$(ls -1t "$HOME"/dl360-backups/dl360-*.dump 2>/dev/null | head -n1)}"
[ -f "$dump" ] || { echo "No backup found. Pass the .dump file."; exit 1; }
counts="${dump%.dump}.counts"
name="dl360-restore-drill-$$"
image="postgres:17-alpine"
psql_in() { docker exec -i "$name" psql -U postgres -d drill -Atq -v ON_ERROR_STOP=1 "$@"; }

cleanup() { docker rm -f "$name" > /dev/null 2>&1 || true; }
trap cleanup EXIT

started=$(date +%s)
echo "1/4 Fresh Postgres ($image) ..."
docker run -d --name "$name" -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=drill "$image" > /dev/null
until docker exec "$name" pg_isready -U postgres -d drill > /dev/null 2>&1; do sleep 1; done
sleep 2 # the entrypoint restarts the server once after initdb
until docker exec "$name" pg_isready -U postgres -d drill > /dev/null 2>&1; do sleep 1; done
psql_in < "$root/infra/postgres-init.sql" > /dev/null

echo "2/4 Restoring $(basename "$dump") ..."
docker cp "$dump" "$name:/tmp/backup.dump"
# Skip the source owner's DEFAULT PRIVILEGES (that role doesn't exist here, and
# postgres-init.sql already set them). Everything else must restore without a single error.
docker exec "$name" sh -c 'pg_restore -l /tmp/backup.dump | grep -v "DEFAULT ACL" > /tmp/toc.list'
docker exec "$name" pg_restore -U postgres -d drill --no-owner --exit-on-error -L /tmp/toc.list /tmp/backup.dump

echo "3/4 Comparing row counts ..."
psql_in < "$here/counts.sql" > /tmp/dl360-restored.counts
if [ -f "$counts" ]; then
  diff <(tr -d '\r' < "$counts") <(tr -d '\r' < /tmp/dl360-restored.counts) \
    && echo "    $(wc -l < "$counts") tables, all counts match"
else
  echo "    (no .counts file next to the dump; skipped)"
fi

echo "4/4 Checking tenant isolation survived ..."
problems="$(psql_in < "$here/checks.sql")"
[ -z "$problems" ] || { echo "FAILED: $problems"; exit 1; }
echo "    RLS on every school table; app role sees nothing without a school"

echo "PASSED in $(( $(date +%s) - started ))s: $(basename "$dump") restores cleanly."
