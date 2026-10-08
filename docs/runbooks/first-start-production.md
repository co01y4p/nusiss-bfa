# Runbook — first start of the production overlay

Run once on a new server (or a fresh local dry run). For the dry run, use
`SITE_DOMAIN=localhost HTTP_PORT=8080 HTTPS_PORT=8443` and open `https://localhost:8443`
(the browser warns about Caddy's local certificate; that is expected).

```bash
export COMPOSE="docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml"
```

## 1. Configure

```bash
cp .env.production.example .env
# Fill in SITE_DOMAIN, POSTGRES_PASSWORD, JWT_SECRET, LLM_API_KEY (openssl rand -hex 32 for the secrets)
```

The stack refuses to start without `POSTGRES_PASSWORD` and `JWT_SECRET`, and the API refuses a
`JWT_SECRET` shorter than 32 characters in production.

## 2. Start

```bash
$COMPOSE up -d --build
$COMPOSE ps          # every service should be (healthy)
```

Database migrations run automatically when the API starts.

## 3. Create the manager account

There is no default account. The script prompts for an email and a password of 12+ characters:

```bash
$COMPOSE exec api python -m app.scripts.seed_manager
```

## 4. Load the approved knowledge documents

A new database has no knowledge, so the assistant answers every policy question with
"I do not have enough approved facility information". Ingest the approved documents
(this calls the embedding model, so `LLM_API_KEY` must be valid):

```bash
for f in building-hours aircon-policy emergency-contacts facility-directory; do
  $COMPOSE exec api python -m app.scripts.ingest_document /data/source-material/$f.md --approve
done
```

## 5. Verify

```bash
curl -s https://$SITE_DOMAIN/api/v1/health/live
curl -s -X POST https://$SITE_DOMAIN/api/v1/assistant/messages -H 'content-type: application/json' \
  -d '{"message":"What are the general building operating hours?"}'
```

The second call should return `FINALIZED` with the opening hours. Also check that
`https://$SITE_DOMAIN/metrics` and `/docs` return 404.

## 6. Back up

Take the first backup and verify it as described in [restore-database.md](restore-database.md).
