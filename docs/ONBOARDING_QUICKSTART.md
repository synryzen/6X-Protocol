# 6X-Protocol Onboarding Quick Start

Last verified: **March 24, 2026**

This guide gets a new user from zero to first workflow run in under 15 minutes.

## Path A: Linux Desktop (Fastest)
1. Download the latest `.deb` from GitHub Releases.
2. Install:
   ```bash
   sudo apt install ./6x-protocol-studio_0.1.9_amd64.deb
   ```
3. Open **6X-Protocol Studio** from the app menu.
4. Go to **Settings**:
   - Set local runtime backend (`ollama` or `lm_studio`).
   - Add local endpoint or cloud API key.
   - Click **Test AI**.
5. Go to **Canvas** and create a workflow:
   - Add `Trigger` -> `AI` -> `Action`.
   - Link nodes and save graph.
6. Run workflow and confirm timeline events in **Runs**.

## Path B: Docker Web Edition (Cross-platform)
1. Install Docker.
2. Start stack:
   ```bash
   cd docker
   docker compose -f docker-compose.web.yml up -d --build
   ```
3. Open web UI: `http://localhost:3000`
4. Open API docs: `http://localhost:8787/docs`
5. In web app, create workflow, add nodes, link ports, save, and run.

## First Configuration Checklist
- [ ] Local or cloud AI provider configured
- [ ] At least one integration profile saved and tested
- [ ] First workflow saved
- [ ] First successful run visible in timeline
- [ ] Theme preset + UI density set to preference

## If AI Test Fails
- Confirm endpoint path for OpenAI-compatible runtimes is `/v1/chat/completions`.
- Confirm provider/model values exactly match your runtime model id.
- For `403` errors, verify required auth header/token and endpoint permissions.

## Useful Links
- Docker quick start: [`../docker/README.md`](../docker/README.md)
- Tutorial: [`TUTORIAL_FIRST_WORKFLOW.md`](./TUTORIAL_FIRST_WORKFLOW.md)
- Launch checklist: [`LAUNCH_CHECKLIST.md`](./LAUNCH_CHECKLIST.md)
