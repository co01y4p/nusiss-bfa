# Runbook — back up and restore the database

All commands run from the repository root. For the production overlay, set the
command prefix once so every script and example targets the right stack:

```bash
export COMPOSE="docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml"
```

Leave `COMPOSE` unset for the local development stack.

## Back up

```bash
scripts/backup_postgres.sh          # writes backups/bfa-<UTC timestamp>.dump, keeps the newest 7
KEEP=14 scripts/backup_postgres.sh  # keep more
```

To run it nightly on a server (off-box copy is the operator's choice; a backup on the same disk does not survive the disk failing):

```cron
0 2 * * * cd /srv/nusiss-bfa && COMPOSE="docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml" scripts/backup_postgres.sh >> backups/backup.log 2>&1
```

## Verify a backup (safe, does not touch live data)

```bash
scripts/restore_postgres.sh backups/bfa-20261008T120000Z.dump
```

The script restores into a scratch database, prints live vs restored row counts for the main tables, and drops the scratch database afterwards. Do this after the first backup and after any schema change.

## Restore over the live database (disaster recovery)

This **replaces** current data. Take a fresh backup of the current state first, even if it is damaged.

1. Stop everything that writes: `$COMPOSE stop api web`
2. Recreate the database:
   ```bash
   $COMPOSE exec -T postgres psql -U bfa -d postgres -c "DROP DATABASE bfa"
   $COMPOSE exec -T postgres psql -U bfa -d postgres -c "CREATE DATABASE bfa"
   ```
3. Restore: `$COMPOSE exec -T postgres pg_restore -U bfa -d bfa --no-owner <backups/bfa-….dump`
4. Start the stack again: `$COMPOSE up -d`. The API runs `alembic upgrade head` on start, which brings an older backup's schema up to date.
5. Check: log in to the manager queue, open a recent incident and its trace, and send a test question to the assistant.

## Schema and image versions

A dump restores into the same or a newer application version. Restoring a **newer** dump into an **older** image can fail because the schema is ahead of the code; check out the matching commit first.
