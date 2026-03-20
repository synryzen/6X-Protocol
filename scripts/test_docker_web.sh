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

echo "[1/7] Building and starting compose stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

cleanup() {
  echo "[7/7] Stopping compose stack..."
  docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[2/7] Waiting for API health..."
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8787/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8787/healthz | jq .

echo "[3/7] Creating workflow..."
WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Smoke Workflow","description":"Created by test script","graph":{"nodes":[{"id":"n1","name":"Trigger","type":"trigger"},{"id":"n2","name":"AI Step","type":"ai"},{"id":"n3","name":"Action","type":"action"}],"edges":[]}}')"

echo "$WORKFLOW_JSON" | jq .
WORKFLOW_ID="$(echo "$WORKFLOW_JSON" | jq -r '.id')"

echo "[4/7] Starting run for workflow..."
RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs/start \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$WORKFLOW_ID\",\"trigger\":\"manual\"}")"
echo "$RUN_JSON" | jq .
RUN_ID="$(echo "$RUN_JSON" | jq -r '.id')"

echo "[5/7] Exercising cancel + retry controls..."
curl -fsS -X POST "http://127.0.0.1:8787/api/v1/runs/$RUN_ID/cancel" | jq .

for _ in {1..20}; do
  RUN_STATUS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$RUN_ID" | jq -r '.status')"
  if [[ "$RUN_STATUS" == "cancelled" || "$RUN_STATUS" == "failed" || "$RUN_STATUS" == "success" ]]; then
    break
  fi
  sleep 0.2
done

RETRY_JSON="$(curl -fsS -X POST "http://127.0.0.1:8787/api/v1/runs/$RUN_ID/retry" \
  -H 'Content-Type: application/json' \
  -d '{"from_failed_node":false}')"
echo "$RETRY_JSON" | jq .
RETRY_RUN_ID="$(echo "$RETRY_JSON" | jq -r '.id')"

sleep 1
curl -fsS "http://127.0.0.1:8787/api/v1/runs/$RETRY_RUN_ID" | jq .

echo "[6/7] Validating retry-from-failed-node flow..."
FAIL_WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Failure Workflow","description":"Failure/retry flow validation","graph":{"nodes":[{"id":"f1","name":"Start","type":"trigger"},{"id":"f2","name":"Failing Step","type":"action","metadata":{"simulate_failure":true}},{"id":"f3","name":"Recover Step","type":"action"}],"edges":[]}}')"
echo "$FAIL_WORKFLOW_JSON" | jq .
FAIL_WORKFLOW_ID="$(echo "$FAIL_WORKFLOW_JSON" | jq -r '.id')"

FAIL_RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs/start \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$FAIL_WORKFLOW_ID\",\"trigger\":\"manual\"}")"
echo "$FAIL_RUN_JSON" | jq .
FAIL_RUN_ID="$(echo "$FAIL_RUN_JSON" | jq -r '.id')"

for _ in {1..30}; do
  FAIL_STATUS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$FAIL_RUN_ID" | jq -r '.status')"
  if [[ "$FAIL_STATUS" == "failed" ]]; then
    break
  fi
  sleep 0.2
done

FAIL_DETAILS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$FAIL_RUN_ID")"
echo "$FAIL_DETAILS" | jq .
LAST_FAILED_NODE_ID="$(echo "$FAIL_DETAILS" | jq -r '.last_failed_node_id')"
if [[ "$LAST_FAILED_NODE_ID" != "f2" ]]; then
  echo "Expected failed node id 'f2', got '$LAST_FAILED_NODE_ID'"
  exit 1
fi

curl -fsS -X PATCH "http://127.0.0.1:8787/api/v1/workflows/$FAIL_WORKFLOW_ID/graph" \
  -H 'Content-Type: application/json' \
  -d '{"nodes":[{"id":"f1","name":"Start","type":"trigger"},{"id":"f2","name":"Failing Step","type":"action","metadata":{"simulate_failure":false}},{"id":"f3","name":"Recover Step","type":"action"}],"edges":[]}' | jq .

FAIL_RETRY_JSON="$(curl -fsS -X POST "http://127.0.0.1:8787/api/v1/runs/$FAIL_RUN_ID/retry" \
  -H 'Content-Type: application/json' \
  -d '{"from_failed_node":true}')"
echo "$FAIL_RETRY_JSON" | jq .
FAIL_RETRY_RUN_ID="$(echo "$FAIL_RETRY_JSON" | jq -r '.id')"

for _ in {1..30}; do
  RETRY_STATUS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$FAIL_RETRY_RUN_ID" | jq -r '.status')"
  if [[ "$RETRY_STATUS" == "success" ]]; then
    break
  fi
  sleep 0.2
done
curl -fsS "http://127.0.0.1:8787/api/v1/runs/$FAIL_RETRY_RUN_ID" | jq .

echo "[6/7] Patching settings and run status..."
curl -fsS -X PATCH http://127.0.0.1:8787/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"theme":"dark","ui_density":"compact","preferred_provider":"local"}' | jq .

curl -fsS -X PATCH "http://127.0.0.1:8787/api/v1/runs/$RETRY_RUN_ID" \
  -H 'Content-Type: application/json' \
  -d '{"status":"success","log":"Smoke test completed"}' | jq .

echo "Smoke test passed."
