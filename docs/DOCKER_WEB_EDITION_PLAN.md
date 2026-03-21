# Docker + Web Edition Build Plan

## Last Verified Status
- Date: **March 21, 2026**
- Overall completion toward first public self-hosted web beta: **~84%**
- Automated smoke status: **passing** via `./scripts/test_docker_web.sh`

## Product Layout
1. **6X-Protocol Desktop** (Linux-native local-first app)
2. **6X-Protocol Server** (shared runtime/API layer)
3. **6X-Protocol Web** (browser client)
4. **Docker Deployment** (self-hosted stack)

This path keeps the Linux desktop strong while expanding to cross-platform access through server + web.

## Architecture Direction
### Layer 1: Core Engine (shared)
- Workflow/node models
- Validation
- Execution contracts
- Retry/backoff/timeout rules
- Serialization/import/export

### Layer 2: Runtime Services
- API + orchestration
- Queue/runner behavior
- Connectors + secrets abstraction
- Logging and run history models

### Layer 3: Clients
- GTK Linux desktop client
- Web client

## Container Topology (Current)
- `6xp-api` — FastAPI workflows/runs/settings + run controls
- `6xp-worker` — runtime worker process
- `6xp-web` — web preview panel
- `postgres` — persistence dependency
- `redis` — queue/cache dependency

## Milestone Board
### M1: Runtime extraction and execution parity
- [x] Graph-aware traversal using edges/legacy links
- [x] Condition branch routing (`true`/`false` + fallback)
- [x] Retry/backoff/timeout controls
- [x] Retry-from-failed-node replay support
- [x] Parallel ready-node fan-out with join/branch pruning

### M2: API surface for web parity
- [x] Workflow CRUD endpoints
- [x] Runs CRUD and run-control endpoints
- [x] Settings load/save endpoints
- [x] Integrations catalog + CRUD + test endpoints
- [x] Rich execution timeline/query APIs

### M3: Web client foundation
- [x] Browser-accessible preview dashboard in Docker
- [x] Graph draft builder (nodes/links/preflight/save) in web preview
- [x] Per-node behavior editor (trigger/action/AI/condition + execution defaults) in web preview
- [x] Integration-specific action field UX (endpoint/method/auth/message/location/path/command) in web preview
- [x] Workflow list search + selected-workflow edit/delete controls in web preview
- [x] Workflow editor form (create/update/duplicate with status/tags) in web preview
- [x] Run timeline event filters (status + search) in web preview
- [x] Expanded settings controls (`local_ai_enabled`, `local_ai_backend`, API keys, `theme_preset`, `reduce_motion`) in web preview
- [x] Workflow list/editor parity
- [x] Runs timeline parity
- [ ] Settings parity
- [ ] Production web canvas builder

### M4: Compose quality and docs
- [x] Official `docker-compose.web.yml`
- [x] `.env.example`
- [x] Docker smoke test script
- [x] Health checks and restart policies
- [ ] Release-grade image versioning strategy

### M5: Hardening and team-readiness
- [ ] DB migration/versioning baseline
- [ ] Auth layer baseline
- [ ] Secret management hardening
- [ ] Backup/restore + observability endpoints

## What Is Done Right Now
- Docker compose stack starts and runs (`api`, `worker`, `web`, `postgres`, `redis`).
- End-to-end smoke validation passes:
  - create workflow
  - start run
  - cancel run
  - retry run
  - retry from failed node
  - timeout/retry policy behavior
  - graph branching validation
  - integration profile create/test/delete lifecycle
- Server execution model now handles node-type behavior + policy controls per run/node.
- Web preview now includes integration profile save/test controls wired to API.
- Web preview now includes graph draft editing + node behavior controls to configure integration/trigger/AI/condition details before save.
- Web preview now includes run query filters + selected-run timeline inspection and selected-run control actions.
- Web preview node behavior editor now includes action templates, execution presets, trigger-mode presets, and integration required-field hints.
- Web preview action editor now auto-shows only relevant integration fields and writes normalized config keys for each integration type.
- Web preview workflow panel now supports search and selected-workflow metadata lifecycle actions (edit/delete).
- Web preview workflow panel now includes a form-based editor for create/update/duplicate operations with status/tags controls.
- Web preview runs panel now supports timeline querying (status/search/node/limit/order) via API-backed timeline endpoints.
- Web preview runs panel now supports selected-run delete and richer run detail refresh workflow.
- Web preview settings panel now supports local backend selection, local/cloud API keys, local runtime enable toggle, theme preset selection, and reduce-motion toggle.

## Remaining To Reach First Public Web Beta
1. Replace web preview dashboard with production web UI modules.
2. Add migration/versioned persistence workflow.
3. Add auth and secrets baseline.
4. Expand integration profile UX toward full connector-field parity with desktop editor.

## Recommended Positioning
- **Desktop mode:** local-first Linux native experience.
- **Self-hosted web mode:** cross-platform (Linux/macOS/Windows) via Docker.

## References
- Docker quick start: [`docker/README.md`](../docker/README.md)
- Compose file: [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml)
- Smoke test script: [`scripts/test_docker_web.sh`](../scripts/test_docker_web.sh)
