#!/usr/bin/env bash
# Prove a backup is restorable WITHOUT touching live data: restore it into a scratch
# database (bfa_restore_check) and compare row counts with the live database.
#
#   scripts/restore_postgres.sh backups/bfa-20261008T120000Z.dump
#
# To restore over the live database instead, follow docs/runbooks/restore-database.md.
set -euo pipefail

cd "$(dirname "$0")/.."
dump="${1:?Usage: $0 <dump file>}"
[ -f "$dump" ] || { echo "No such file: $dump" >&2; exit 1; }
COMPOSE="${COMPOSE:-docker compose -f infra/compose/compose.yml}"
SCRATCH="bfa_restore_check"
TABLES=(users incidents workflow_runs knowledge_documents knowledge_chunks security_events agent_prompts)

psql_live() { $COMPOSE exec -T postgres psql -U bfa -d bfa -tA "$@"; }
psql_scratch() { $COMPOSE exec -T postgres psql -U bfa -d "$SCRATCH" -tA "$@"; }

cleanup() { $COMPOSE exec -T postgres psql -U bfa -d postgres -qc "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null; }
trap cleanup EXIT
cleanup
$COMPOSE exec -T postgres psql -U bfa -d postgres -qc "CREATE DATABASE $SCRATCH"

# --no-owner/--no-privileges: only the data and schema matter for the check.
$COMPOSE exec -T postgres pg_restore -U bfa -d "$SCRATCH" --no-owner --no-privileges <"$dump"

status=0
printf '%-24s %10s %10s\n' table live restored
for table in "${TABLES[@]}"; do
  live=$(psql_live -c "SELECT count(*) FROM $table")
  restored=$(psql_scratch -c "SELECT count(*) FROM $table")
  flag=""
  # The live database may have gained rows since the dump; only a MISSING row is an error.
  if [ "$restored" -gt "$live" ]; then flag="  <-- restored has MORE rows than live"; status=1; fi
  printf '%-24s %10s %10s%s\n' "$table" "$live" "$restored" "$flag"
done

if [ "$status" -eq 0 ]; then
  echo "OK: backup restored into $SCRATCH (live data untouched)."
else
  echo "CHECK: counts look inconsistent; inspect before relying on this backup." >&2
fi
exit "$status"
