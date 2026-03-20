# Docker Scaffold (Web Edition)

This directory contains an initial scaffold for a future web/self-hosted deployment path.

## Important
- This is a planning scaffold, not a production release.
- The current primary product remains the Linux-native desktop app.

## Files
- `docker-compose.web.yml`: starter service topology for API, worker, web, Postgres, and Redis.
- `.env.example`: environment variable template.

## Quick Start (Scaffold Mode)
```bash
cd docker
cp .env.example .env
docker compose -f docker-compose.web.yml up -d
```

This brings up placeholder `api` and `web` containers plus real `postgres`/`redis`.

## Next Implementation Steps
1. Replace placeholder `api` container with a real service.
2. Add migration and health-check endpoints.
3. Replace placeholder `web` with actual frontend build/runtime.
4. Add backup, logging, and observability baseline.
