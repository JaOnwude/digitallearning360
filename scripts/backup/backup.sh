#!/usr/bin/env bash
# Back up the DigitalLearning360 database (spec AC12). Needs Docker.
#
#   DL360_BACKUP_URL='postgresql://owner:password@host/db?sslmode=require' scripts/backup/backup.sh [dir]
#
# Use the OWNER connection string (Neon: the neondb_owner one), never commit it. Writes
#   dl360-<UTC time>.dump    pg_dump custom format (compressed, restorable table by table)
#   dl360-<UTC time>.counts  exact row counts, so a restore can be checked against it
# and keeps the newest 14 of each. Default dir: ~/dl360-backups (keep it off the repo).
set -euo pipefail

url="${DL360_BACKUP_URL:?Set DL360_BACKUP_URL to the database owner connection string}"
dir="${1:-$HOME/dl360-backups}"
image="postgres:17-alpine" # pg_dump must be at least the server's version
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
base="$dir/dl360-$stamp"

echo "Dumping to $base.dump ..."
docker run --rm "$image" pg_dump --format=custom --no-owner "$url" > "$base.dump.partial"
docker run --rm -i "$image" pg_restore --list < "$base.dump.partial" > /dev/null # readable?
mv "$base.dump.partial" "$base.dump"
docker run --rm -i "$image" psql "$url" -At -v ON_ERROR_STOP=1 < "$here/counts.sql" > "$base.counts"

# Keep the newest 14 backups.
ls -1t "$dir"/dl360-*.dump 2>/dev/null | tail -n +15 | while read -r old; do
  rm -f -- "$old" "${old%.dump}.counts"
done
echo "OK: $(du -h "$base.dump" | cut -f1) dump, $(wc -l < "$base.counts") tables. Kept: $(ls -1 "$dir"/dl360-*.dump | wc -l)."
