# Docker Scaffold (Web Edition)

This directory contains the scaffold for a future web/self-hosted deployment path.

## Important
- This is an early scaffold, not a production release.
- The current primary product remains the Linux-native desktop app.

## Files
- `docker-compose.web.yml`: service topology for API, worker, web, Postgres, and Redis.
- `.env.example`: environment variable template.
- `api/`: FastAPI scaffold (`/healthz`, `/readyz`, `/api/v1/meta`).
- `web/`: placeholder web shell served by Nginx.

## Quick Start (Scaffold Mode)
```bash
cd docker
cp .env.example .env
docker compose -f docker-compose.web.yml up -d
```

This builds and runs:
- FastAPI scaffold API on `http://localhost:8787`
- Worker scaffold process
- Placeholder web shell on `http://localhost:3000`
- Postgres and Redis
- Shared scaffold JSON data volume (`api_data`)

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

Automated smoke test from repo root:
```bash
./scripts/test_docker_web.sh
```

Core scaffold routes:
- `GET /api/v1/overview`
- `GET/POST/PUT/DELETE /api/v1/workflows`
- `PATCH /api/v1/workflows/{id}/graph`
- `GET/POST/PATCH/DELETE /api/v1/runs`
- `POST /api/v1/runs/start`
- `POST /api/v1/runs/{id}/cancel`
- `POST /api/v1/runs/{id}/retry`
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

## Next Implementation Steps
1. Expand API routes for workflows, runs, integrations, and settings.
2. Add DB migrations and auth model.
3. Replace placeholder `web` with production frontend build/runtime.
4. Add backup, logging, and observability baseline.
