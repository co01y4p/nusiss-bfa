# M7 — Deployment (light)

[← back to overview](00-overview.md)

## Objective

Harden the same Docker Compose stack used throughout for a real server, and **document** the production path in full — without provisioning anything yet. Development stays local until you're ready to go live.

## Scope

Build:
- `infra/compose/compose.prod.yml` — an overlay adding: Caddy reverse proxy (automatic HTTPS via Let's Encrypt), non-root containers (`cap_drop: [ALL]`, `no-new-privileges`), read-only filesystems where possible, `secrets:`-backed Postgres password instead of a plain env var.
- `infra/reverse-proxy/Caddyfile` — routes `web`/`api`, forces HTTPS.
- `.env.production.example` — template, real values never committed.
- A backup approach documented (e.g. nightly `pg_dump` to an off-box destination) — implemented as a simple cron/script, not a managed service, to keep this proportionate to the project's scope.

Kubernetes stays explicitly **out of scope** — Docker Compose is the only deployment mechanism this project builds. If a Kubernetes comparison is ever wanted, it's a separate, later request.

## Folders touched

```
infra/compose/compose.prod.yml
infra/reverse-proxy/Caddyfile
.env.production.example
scripts/backup_postgres.sh
```

## Deployment artifact

`docker compose -f infra/compose/compose.yml -f infra/compose/compose.prod.yml up -d` on the target server — same images as dev, different `.env` and the Caddy/hardening overlay.

## Setup (documented now, executed once you provision a server)

```bash
# on the server, once provisioned:
git clone <repo> && cd nusiss-bfa
cp .env.production.example .env
# fill in production secrets (see manual tasks below)
docker compose -f infra/compose/compose.yml -f infra/compose/compose.prod.yml up -d
```

## Manual tasks (things only you can do)

- [ ] Provision a VM or server (any cloud provider, or a university/organization-provided host) — requires an account only you can create.
- [ ] Register or point a domain's DNS **A record** at the server's IP (needed for Caddy's automatic HTTPS).
- [ ] Add your SSH public key to the server for access.
- [ ] Set production secrets directly on the server (`JWT_SECRET`, Postgres password, `LLM_API_KEY`) — generated the same way as in M1/M2 but **never committed to git**.
- [ ] Add deploy-related secrets (SSH private key, server host) under **GitHub repo → Settings → Secrets and variables → Actions** — this is a GitHub UI action only you have access to.
- [ ] Pick an off-box backup destination (e.g. an S3-compatible bucket) if you want backups to survive the server itself failing.

## Exit criteria (once actually provisioned — not required to finish this milestone's *planning*)

- `https://<your-domain>` serves the app with a valid TLS certificate.
- Containers run as non-root; `docker inspect` shows dropped capabilities.
- A restorable Postgres backup exists and has been test-restored at least once.
