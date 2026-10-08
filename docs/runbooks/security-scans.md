# Runbook — security scans

`.github/workflows/security.yml` runs on every pull request (any path), on pushes to
`master`, and every Monday 01:00 UTC. Every job is a plain command with a pinned tool, so you
can run exactly what CI runs.

| Job | Tool | Blocks the build on | Run locally |
|---|---|---|---|
| Secrets | Gitleaks 8.24.2, full git history, config in `.gitleaks.toml` | any finding | see below |
| Python dependencies | pip-audit 2.9.0 on a clean install of `apps/api` | any known vulnerability | see below |
| Node dependencies | `pnpm audit --audit-level=high` for `apps/web` | high or critical | `cd apps/web && pnpm audit --audit-level=high` |
| Node dependencies (advisory) | same, for `evals/promptfoo` | nothing (reported only) | `cd evals/promptfoo && pnpm audit` |
| Static analysis | Semgrep 1.119.0 (`p/python`, `p/typescript`, `p/owasp-top-ten`), error severity | any finding | see below |
| Container images | Trivy 0.62.1 on the `api` and `web` images, high/critical with a fix | any finding | see below |

```bash
# Secrets (scans all history)
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.24.2 detect --source /repo --config /repo/.gitleaks.toml --redact --verbose --exit-code 1

# Static analysis
docker run --rm -v "$PWD:/src" semgrep/semgrep:1.119.0 semgrep scan --metrics=off --error --severity ERROR \
  --config p/python --config p/typescript --config p/owasp-top-ten \
  --exclude node_modules --exclude .next --exclude apps/api/tests /src

# Images
docker build -t bfa-api:scan apps/api && docker build -t bfa-web:scan apps/web
for i in api web; do docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.62.1 \
  image --quiet --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 bfa-$i:scan; done

# Python dependencies
python -m venv /tmp/api-env && /tmp/api-env/bin/pip install ./apps/api
pip install pip-audit==2.9.0 && pip-audit --path /tmp/api-env/lib/python3.13/site-packages
```

## Baseline on 8 October 2026 and what was fixed

| Scan | Before | After |
|---|---|---|
| `pnpm audit` (`apps/web`) | 20 findings: 3 critical, 10 high (Next.js 16.3.0 incl. unauthenticated RCE and an image-optimisation SSRF; transitive `js-yaml`, `brace-expansion`, `source-map-js`) | 0 critical; 1 high documented below |
| Trivy `api` image | 4 high/critical, all copies vendored inside `pip` | 0 (pip is removed from the runtime image) |
| Trivy `web` image | 10 high/critical, all in the `npm` bundled with the Node base image | 0 (npm/yarn removed from the runtime image) |
| pip-audit | none | none |
| Semgrep | none (93 rules, 227 files) | none |
| Gitleaks | **1: a committed `.env.old-vanilla-backup`** | file untracked; the finding remains in git history (see below) |

## Open items

1. **Leaked secrets in git history (action needed by the repository owner).**
   `.env.old-vanilla-backup` was committed in `1473898` and pushed to the public repository.
   It contains a `SESSION_SECRET`, a `GEMINI_API_KEY` value and `MANAGER_EMAILS`. The file is
   no longer tracked, but it stays in history, so **treat both secrets as compromised: rotate
   the Gemini key and the session secret.** Gitleaks keeps failing on that one history entry
   until it is either removed from history (a force-push that every teammate must absorb) or,
   once the secrets are rotated, allowlisted by fingerprint in `.gitleaks.toml` with a dated
   comment. Do not allowlist before rotating.
2. **`braces` (GHSA-vfj7-8cjw-p6xm).** The advisory names `3.0.4` as the fix but that release
   is not published, so it cannot be installed. It is ignored in `apps/web/pnpm-workspace.yaml`
   with a dated note; it is reachable only through the lint-time glob chain, not the shipped
   image. Remove the ignore when a fixed release appears.
3. **`evals/promptfoo` findings** (41 at baseline, 32 on the newest Promptfoo) are in deep
   dependencies of a pinned test runner. Bumping Promptfoo would change the evaluation
   baseline, so it is a separate, deliberate change.

## Handling exceptions

Allow-list files are `.gitleaks.toml`, `ignoreGhsas` in `apps/web/pnpm-workspace.yaml`, and
`# nosemgrep` comments. Each entry needs a reason, a date, and the condition for removing it.
Never allowlist a real secret to make a build pass: rotate it first.
