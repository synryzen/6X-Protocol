# Docker Web Edition (Active Preview)

This directory contains the active self-hosted web preview stack for 6X-Protocol.

## Important
- This is an active preview, not yet a production release.
- The current primary product remains the Linux-native desktop app.

## Files
- `docker-compose.web.yml`: service topology for API, worker, web, Postgres, and Redis.
- `.env.example`: environment variable template.
- `api/`: FastAPI scaffold (`/healthz`, `/readyz`, `/api/v1/meta`).
- `web/`: lightweight web access dashboard served by Nginx.

## Quick Start (Preview Mode)
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

Cross-origin browser access is controlled by:
`CORS_ALLOW_ORIGINS` (see `.env.example`).

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
- `GET/POST/PUT/DELETE /api/v1/workflows`
- `PATCH /api/v1/workflows/{id}/graph`
- `GET/POST/PATCH/DELETE /api/v1/runs`
- `POST /api/v1/runs/start`
- `POST /api/v1/runs/{id}/cancel`
- `POST /api/v1/runs/{id}/retry`
- `GET/POST /api/v1/bots`
- `GET/PATCH/DELETE /api/v1/bots/{id}`
- `POST /api/v1/bots/test`
- `GET /api/v1/integrations/catalog`
- `GET/POST /api/v1/integrations`
- `GET/PATCH/DELETE /api/v1/integrations/{id}`
- `POST /api/v1/integrations/test`
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
2. Add DB migration/versioning workflow and stronger persistence boundaries.
3. Add authentication and secrets hardening baseline.
4. Add backup, observability, and deployment hardening.
