#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.web.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not in PATH"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for this smoke test"
  echo "Install: sudo apt install -y jq"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not accessible for current user"
  echo "Fix: sudo usermod -aG docker $USER && newgrp docker"
  exit 1
fi

cd "$ROOT_DIR/docker"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "[1/6] Building and starting compose stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

cleanup() {
  echo "[6/6] Stopping compose stack..."
  docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[2/6] Waiting for API health..."
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8787/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8787/healthz | jq .

echo "[3/6] Creating workflow..."
WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Smoke Workflow","description":"Created by test script","graph":{"nodes":[],"edges":[]}}')"

echo "$WORKFLOW_JSON" | jq .
WORKFLOW_ID="$(echo "$WORKFLOW_JSON" | jq -r '.id')"

echo "[4/6] Creating run for workflow..."
RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$WORKFLOW_ID\",\"status\":\"queued\",\"trigger\":\"manual\"}")"
echo "$RUN_JSON" | jq .
RUN_ID="$(echo "$RUN_JSON" | jq -r '.id')"

echo "[5/6] Patching settings and run status..."
curl -fsS -X PATCH http://127.0.0.1:8787/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"theme":"dark","ui_density":"compact","preferred_provider":"local"}' | jq .

curl -fsS -X PATCH "http://127.0.0.1:8787/api/v1/runs/$RUN_ID" \
  -H 'Content-Type: application/json' \
  -d '{"status":"success","log":"Smoke test completed"}' | jq .

echo "Smoke test passed."
