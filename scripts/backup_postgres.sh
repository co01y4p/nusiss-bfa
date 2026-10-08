#!/usr/bin/env bash
# Dump the application database to backups/bfa-<UTC timestamp>.dump (pg_dump custom format)
# and keep the newest $KEEP dumps. Works against whichever stack Compose resolves.
#
#   scripts/backup_postgres.sh
#   COMPOSE="docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml" \
#     scripts/backup_postgres.sh
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="${COMPOSE:-docker compose -f infra/compose/compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP="${KEEP:-7}"

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/bfa-$(date -u +%Y%m%dT%H%M%SZ).dump"

# Write to a temp name first so an interrupted dump never looks like a good backup.
$COMPOSE exec -T postgres pg_dump -U bfa -d bfa -Fc >"$target.partial"
mv "$target.partial" "$target"

# Retention: delete everything but the newest $KEEP dumps.
while IFS= read -r old; do
  rm -f -- "$old"
done < <(ls -1t "$BACKUP_DIR"/bfa-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))")

echo "Backup written: $target ($(du -h "$target" | cut -f1))"
