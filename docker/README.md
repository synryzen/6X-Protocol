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

API checks:
```bash
curl http://localhost:8787/healthz
curl http://localhost:8787/api/v1/meta
```

## Next Implementation Steps
1. Expand API routes for workflows, runs, integrations, and settings.
2. Add DB migrations and auth model.
3. Replace placeholder `web` with production frontend build/runtime.
4. Add backup, logging, and observability baseline.
