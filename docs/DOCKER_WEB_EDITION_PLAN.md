# Docker And Web Edition Plan

## Objective
Add a cross-platform self-hosted path (Linux/macOS/Windows) without replacing the Linux-native desktop app.

## Product Strategy
1. Keep native Linux desktop edition as the local-first UX.
2. Build a shared runtime/server layer.
3. Add a web UI that consumes server APIs.
4. Ship official Docker Compose deployment for the web edition.

## Why This Approach
- One deployable stack for multiple operating systems.
- Consistent runtime behavior.
- Easier team deployment and support.
- Better long-term foundation for optional commercial offerings.

## Scope Boundaries
- Recommended: server + API + web frontend + worker(s) + database in containers.
- Not recommended as primary path: running GTK desktop UI through VNC/noVNC.

## Target Container Topology
- `6xp-api`: workflow API + orchestration endpoints.
- `6xp-worker`: workflow execution and queue processing.
- `6xp-web`: browser UI.
- `postgres`: persistence.
- `redis`: queue/cache.

## Security Baseline
- Secrets via env vars or mounted secret files.
- No secrets in repo.
- Non-root containers where practical.
- Health checks and restart policies.

## Milestones
### M1: Runtime extraction
- Define clean service boundaries.
- Isolate execution engine interfaces.

### M2: API surface
- Workflow CRUD, runs/history, settings, integration tests.
- Auth model decision (single-user local vs team mode).

### M3: Web UI foundation
- Dashboard, workflows, canvas, runs, settings parity baseline.

### M4: Compose release
- Official `docker-compose.web.yml`.
- Setup docs and sample `.env`.

### M5: Ops hardening
- Backups, migrations, health dashboards, observability endpoints.

## Current Status
- Active scaffold stage.
- Compose now includes a real FastAPI scaffold API, worker process scaffold, and web placeholder.
- API scaffold now includes persistence-backed routes for workflows, runs, and settings.
- Run control scaffolding now includes `start`, `cancel`, and `retry` endpoints with state transitions.
- Run scaffold now applies node-type-aware execution and per-run/per-node timeout/retry/backoff controls.
- Runtime traversal now uses workflow graph edges (including legacy links) with condition branch routing.
- Runtime now supports parallel ready-node execution with basic join semantics and branch pruning.
- See `docker/README.md` and `docker/docker-compose.web.yml`.
