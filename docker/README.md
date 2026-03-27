# Docker Web Edition (Live Self-Hosted)

This directory contains the active self-hosted web public beta stack for 6X-Protocol.

## Important
- This is an active public beta, not yet a production release.
- The current primary product remains the Linux-native desktop app.

## Files
- `docker-compose.web.yml`: service topology for API, worker, web, Postgres, and Redis.
- `.env.example`: environment variable template.
- `api/`: FastAPI scaffold (`/healthz`, `/readyz`, `/api/v1/meta`).
- `web/`: lightweight web access dashboard served by Nginx.

## Quick Start (Public Beta)
```bash
cd docker
cp .env.example .env
docker compose -f docker-compose.web.yml up -d
```

This builds and runs:
- FastAPI runtime API on `http://localhost:8787`
- Worker runtime process
- Web preview dashboard on `http://localhost:3000`
- Postgres and Redis
- Shared JSON data volume (`api_data`)

If Docker daemon access is denied for your user:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

API checks:
```bash
curl http://localhost:8787/healthz
curl http://localhost:8787/api/v1/meta
```

Web dashboard actions include:
- API health + overview metrics
- create sample workflow
- start/cancel/retry run controls
- live workflow/run list
- settings load/save panel
- integration catalog + profile save/test panel
- integration profile bundle import/export controls
- server-backed workflow preflight validation

Cross-origin browser access is controlled by:
`CORS_ALLOW_ORIGINS` (see `.env.example`).

Optional API auth baseline:
- Set `API_AUTH_TOKEN` in `docker/.env` to require auth for `/api/v1/*`.
- Health routes (`/healthz`, `/readyz`) remain open for compose healthchecks.
- Clients can authenticate with either:
  - `X-6X-API-Key: <token>`
  - `Authorization: Bearer <token>`
- The web dashboard now includes an API token field in the top bar and sends `X-6X-API-Key` when set.

Optional secret encryption baseline:
- Set `SECRET_ENCRYPTION_KEY` in `docker/.env` to encrypt sensitive settings/integration fields at rest.
- Supported formats:
  - plain passphrase (derived server-side to a Fernet key)
  - `fernet:<base64-urlsafe-32-byte-key>`
- Encrypted values are stored with prefix `enc:v1:` in JSON files and transparently decrypted by the API at runtime.
- Rotate encrypted material using `POST /api/v1/admin/secrets/rotate` with `new_key_material`.

Managed secret adapter baseline:
- Configure `SECRET_PROVIDER_MODE` with one of: `disabled`, `env`, `file`, `http`, `vault`, `chain`.
- Resolve references in settings/integration configs using:
  - `env:YOUR_ENV_KEY` or `secret://env/YOUR_ENV_KEY`
  - `file:path.to.secret` or `secret://file/path.to.secret`
  - `http:path.to.secret` or `secret://http/path.to.secret` (from JSON fetched via HTTP provider URL)
  - `vault:path.to.secret` or `secret://vault/path.to.secret` (from Vault JSON/KV response payload)
- Optional file-backed provider path: `SECRET_PROVIDER_FILE` (default `/data/6x-protocol/managed-secrets.json`).
- Optional env prefix: `SECRET_PROVIDER_ENV_PREFIX` (for prefixed env lookup fallback).
- Optional HTTP provider settings:
  - `SECRET_PROVIDER_HTTP_URL`
  - `SECRET_PROVIDER_HTTP_AUTH_TOKEN`
  - `SECRET_PROVIDER_HTTP_TIMEOUT_SEC` (default `3.0`)
  - `SECRET_PROVIDER_HTTP_ALLOW_INSECURE` (`false` by default, enables non-HTTPS URLs only when true)
- Optional Vault provider settings:
  - `SECRET_PROVIDER_VAULT_URL`
  - `SECRET_PROVIDER_VAULT_AUTH_TOKEN`
  - `SECRET_PROVIDER_VAULT_TIMEOUT_SEC` (default `3.0`)
  - `SECRET_PROVIDER_VAULT_ALLOW_INSECURE` (`false` by default, enables non-HTTPS URLs only when true)
- Provider status routes:
  - `GET /api/v1/admin/secrets/provider`
  - `POST /api/v1/admin/secrets/provider/reload`

Image/version governance baseline:
- Configure runtime provenance and compatibility via:
  - `SIXPX_IMAGE_TAG` (runtime image tag)
  - `SIXPX_EXPECTED_IMAGE_TAG` (optional exact-tag assertion)
  - `SIXPX_RELEASE_CHANNEL` (`dev|beta|rc|ga|stable|prod`)
  - `SIXPX_BUILD_SHA` / `SIXPX_BUILD_DATE`
  - `SIXPX_IMAGE_DIGEST` (recommended for `ga/stable/prod`)
  - `SIXPX_MIN_API_VERSION` / `SIXPX_MAX_API_VERSION` (optional semver bounds)
  - `SIXPX_MIN_STORE_SCHEMA_VERSION` / `SIXPX_MAX_STORE_SCHEMA_VERSION`
- Governance status routes:
  - `GET /api/v1/admin/runtime/governance`
- `/api/v1/meta` now includes runtime governance status fields for health dashboards.
- CI guardrail: `python3 scripts/verify_runtime_governance.py`
- Release workflow now publishes package provenance attestations.

Relational migration scaffold baseline:
- API startup now runs a Postgres migration scaffold when `DATABASE_URL` is set.
- Tracks revisions in `sixpx_schema_migrations` and seeds runtime scaffold state in `sixpx_runtime_state`.
- Tracked revisions:
  - `r0001_initial_runtime_scaffold`
  - `r0002_runtime_core_tables`
  - `r0003_runtime_observability_tables`
  - `r0004_runtime_metadata_columns`
- Runtime migration status route:
  - `GET /api/v1/admin/runtime/migrations`
  - Optional refresh: `GET /api/v1/admin/runtime/migrations?refresh=true`
- Controls:
  - `SIXPX_STORAGE_BACKEND` (`json` or `postgres`)
  - `SIXPX_STORAGE_BACKEND_REQUIRED`
  - `RELATIONAL_MIGRATION_REQUIRED`
  - `RELATIONAL_MIGRATION_ENFORCE_COMPATIBILITY`
  - `RELATIONAL_MIGRATION_CONNECT_TIMEOUT_SEC`
  - `RELATIONAL_MIGRATION_RETRY_ATTEMPTS`
  - `RELATIONAL_MIGRATION_RETRY_DELAY_SEC`
  - `RELATIONAL_ALLOW_UNKNOWN_REVISIONS`
  - `RELATIONAL_MIN_SCHEMA_VERSION`
  - `RELATIONAL_MAX_SCHEMA_VERSION`
- Migration status now reports:
  - `current_schema_version`
  - `compatibility_status`
  - `compatibility_errors` / `compatibility_warnings`

Storage backend cutover (feature-flagged):
- Default remains JSON: `SIXPX_STORAGE_BACKEND=json`
- Enable Postgres repositories: `SIXPX_STORAGE_BACKEND=postgres`
- Strict mode: `SIXPX_STORAGE_BACKEND_REQUIRED=true` (fails startup if postgres backend is unavailable)
- When Postgres backend is active, API startup requires relational migration status `ok`.

Storage schema baseline:
- JSON persistence now tracks schema metadata in `/data/6x-protocol/schema_meta.json`.
- Migration history is recorded in `/data/6x-protocol/schema_migrations.json`.
- Legacy payloads are normalized automatically on startup (v1 -> v2 -> v3).
- Migration snapshots are captured in `/data/6x-protocol/migration_snapshots/`.
- Future-schema compatibility guardrails are enforced at startup and backup restore.

Automated smoke test from repo root:
```bash
./scripts/test_docker_web.sh
```

If your user was recently added to the `docker` group and this shell has not refreshed yet,
the smoke script will automatically re-run itself with `sg docker`.
You can also run it directly:
```bash
sg docker -c './scripts/test_docker_web.sh'
```

Current API routes:
- `GET /api/v1/overview`
- `GET /api/v1/observability/summary`
- `GET /api/v1/observability/runs`
- `POST /api/v1/admin/backup`
- `POST /api/v1/admin/restore`
- `POST /api/v1/admin/secrets/rotate`
- `GET /api/v1/admin/secrets/provider`
- `POST /api/v1/admin/secrets/provider/reload`
- `GET /api/v1/admin/runtime/governance`
- `GET /api/v1/admin/runtime/migrations`
- `GET/POST/PUT/DELETE /api/v1/workflows`
- `PATCH /api/v1/workflows/{id}/graph`
- `POST /api/v1/workflows/{id}/preflight`
- `GET/POST/PATCH/DELETE /api/v1/runs`
- `POST /api/v1/runs/start`
- `POST /api/v1/runs/{id}/cancel`
- `POST /api/v1/runs/{id}/resume`
- `POST /api/v1/runs/{id}/retry`
- `GET/POST /api/v1/bots`
- `GET/PATCH/DELETE /api/v1/bots/{id}`
- `POST /api/v1/bots/test`
- `GET /api/v1/integrations/catalog`
- `GET/POST /api/v1/integrations`
- `GET/PATCH/DELETE /api/v1/integrations/{id}`
- `POST /api/v1/integrations/test`
- `POST /api/v1/integrations/export`
- `POST /api/v1/integrations/import`
- `GET/PATCH /api/v1/settings`
- `POST /api/v1/settings/reset`

Create a workflow example:
```bash
curl -X POST http://localhost:8787/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"name":"Web API Starter","description":"Created from curl","graph":{"nodes":[],"edges":[]}}'
```

Retry behavior notes:
- `from_failed_node: true` requires the source run to be `failed`.
- The source run must include `last_failed_node_id`, otherwise retry-from-failed returns `409`.
- `approval_gate` actions move a run to `waiting_approval` until resumed via `POST /api/v1/runs/{id}/resume`.

Execution policy controls (per-run):
- `retry_max`
- `retry_backoff_ms`
- `timeout_sec`

`POST /api/v1/runs/start` accepts these values and applies them as run defaults.
Nodes can override with `config.retry_max`, `config.retry_backoff_ms`, and `config.timeout_sec`.

Execution routing behavior:
- Graph-aware traversal executes from start nodes using `graph.edges` (and legacy `graph.links`).
- Condition nodes route by edge condition (`true`/`false`) with `next` fallback.
- Retry-from-failed-node (`from_failed_node: true`) starts from the previously failed node and follows downstream edges.
- Parallel branch execution is enabled for independent ready nodes.
- Join semantics wait for all active inbound paths; pruned branches are marked `skipped`.
- Optional graph setting: `graph.settings.max_parallel` (1-8, default 2).

## Remaining Milestones
1. Replace preview `web` dashboard with production web frontend (workflow/canvas/runs/settings views).
2. Continue feature-flagged Postgres repository cutover using the tracked `r0001-r0004` schema baseline.
3. Expand secrets hardening (encrypted-at-rest provider adapters + rotation workflows).
4. Complete deployment hardening beyond baseline (external secret stores + signed release digest policy).
