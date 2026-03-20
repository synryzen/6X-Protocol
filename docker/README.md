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
- `GET/PATCH /api/v1/settings`
- `POST /api/v1/settings/reset`

Create a workflow example:
```bash
curl -X POST http://localhost:8787/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"name":"Web API Starter","description":"Created from curl","graph":{"nodes":[],"edges":[]}}'
```

## Next Implementation Steps
1. Expand API routes for workflows, runs, integrations, and settings.
2. Add DB migrations and auth model.
3. Replace placeholder `web` with production frontend build/runtime.
4. Add backup, logging, and observability baseline.
