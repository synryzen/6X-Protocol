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
  if [[ "${_SIXPX_DOCKER_GROUP_REEXEC:-0}" != "1" ]] && command -v sg >/dev/null 2>&1; then
    if getent group docker >/dev/null 2>&1 && getent group docker | grep -Eq "(^|[:,])${USER}(,|$)"; then
      echo "docker group membership detected but not active in this shell."
      echo "Re-running smoke test under 'sg docker'..."
      exec sg docker -c "cd \"$ROOT_DIR\" && _SIXPX_DOCKER_GROUP_REEXEC=1 ./scripts/test_docker_web.sh"
    fi
  fi
  echo "docker daemon is not accessible for current user"
  echo "Fix: sudo usermod -aG docker $USER && newgrp docker"
  exit 1
fi

cd "$ROOT_DIR/docker"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "[1/10] Building and starting compose stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

cleanup() {
  echo "[10/10] Stopping compose stack..."
  docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[2/10] Waiting for API health..."
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8787/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8787/healthz | jq .

echo "[3/10] Creating workflow..."
WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Smoke Workflow","description":"Created by test script","graph":{"nodes":[{"id":"n1","name":"Trigger","type":"trigger"},{"id":"n2","name":"AI Step","type":"ai"},{"id":"n3","name":"Action","type":"action"}],"edges":[]}}')"

echo "$WORKFLOW_JSON" | jq .
WORKFLOW_ID="$(echo "$WORKFLOW_JSON" | jq -r '.id')"

echo "[4/10] Starting run for workflow..."
RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs/start \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$WORKFLOW_ID\",\"trigger\":\"manual\"}")"
echo "$RUN_JSON" | jq .
RUN_ID="$(echo "$RUN_JSON" | jq -r '.id')"

echo "[5/10] Exercising cancel + retry controls..."
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

echo "[6/10] Validating retry-from-failed-node flow..."
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

echo "[7/10] Validating retry/backoff/timeout execution policies..."
POLICY_WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Policy Workflow","description":"Execution policy validation","graph":{"nodes":[{"id":"p1","name":"Policy Start","type":"trigger"},{"id":"p2","name":"Flaky Action","type":"action","metadata":{"simulate_failure_attempts":1,"simulate_delay_ms":120}}],"edges":[]}}')"
echo "$POLICY_WORKFLOW_JSON" | jq .
POLICY_WORKFLOW_ID="$(echo "$POLICY_WORKFLOW_JSON" | jq -r '.id')"

POLICY_RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs/start \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$POLICY_WORKFLOW_ID\",\"trigger\":\"manual\",\"retry_max\":2,\"retry_backoff_ms\":120,\"timeout_sec\":2.0}")"
echo "$POLICY_RUN_JSON" | jq .
POLICY_RUN_ID="$(echo "$POLICY_RUN_JSON" | jq -r '.id')"

for _ in {1..40}; do
  POLICY_STATUS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$POLICY_RUN_ID" | jq -r '.status')"
  if [[ "$POLICY_STATUS" == "success" || "$POLICY_STATUS" == "failed" ]]; then
    break
  fi
  sleep 0.2
done
POLICY_DETAILS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$POLICY_RUN_ID")"
echo "$POLICY_DETAILS" | jq .
if [[ "$(echo "$POLICY_DETAILS" | jq -r '.status')" != "success" ]]; then
  echo "Expected policy run success."
  exit 1
fi
if [[ "$(echo "$POLICY_DETAILS" | jq -r '.execution_retry_max')" != "2" ]]; then
  echo "Expected execution_retry_max=2"
  exit 1
fi
if [[ "$(echo "$POLICY_DETAILS" | jq -r '.execution_backoff_ms')" != "120" ]]; then
  echo "Expected execution_backoff_ms=120"
  exit 1
fi
TIMEOUT_VALUE="$(echo "$POLICY_DETAILS" | jq -r '.execution_timeout_sec')"
if [[ "$TIMEOUT_VALUE" != "2" && "$TIMEOUT_VALUE" != "2.0" ]]; then
  echo "Expected execution_timeout_sec=2.0"
  exit 1
fi

TIMEOUT_WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Timeout Workflow","description":"Timeout validation","graph":{"nodes":[{"id":"t1","name":"Slow Step","type":"action","metadata":{"simulate_delay_ms":600}}],"edges":[]}}')"
TIMEOUT_WORKFLOW_ID="$(echo "$TIMEOUT_WORKFLOW_JSON" | jq -r '.id')"

TIMEOUT_RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs/start \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$TIMEOUT_WORKFLOW_ID\",\"trigger\":\"manual\",\"retry_max\":1,\"retry_backoff_ms\":50,\"timeout_sec\":0.1}")"
TIMEOUT_RUN_ID="$(echo "$TIMEOUT_RUN_JSON" | jq -r '.id')"

for _ in {1..40}; do
  TIMEOUT_STATUS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$TIMEOUT_RUN_ID" | jq -r '.status')"
  if [[ "$TIMEOUT_STATUS" == "failed" ]]; then
    break
  fi
  sleep 0.2
done
TIMEOUT_DETAILS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$TIMEOUT_RUN_ID")"
echo "$TIMEOUT_DETAILS" | jq .
if [[ "$(echo "$TIMEOUT_DETAILS" | jq -r '.status')" != "failed" ]]; then
  echo "Expected timeout run to fail."
  exit 1
fi
if ! echo "$TIMEOUT_DETAILS" | jq -r '.summary' | grep -qi 'Timed out'; then
  echo "Expected timeout summary to mention timeout."
  exit 1
fi

echo "[8/10] Validating graph routing + condition branching..."
ROUTING_WORKFLOW_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/workflows \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Routing Workflow","description":"Condition branch validation","graph":{"nodes":[{"id":"r1","name":"Start","type":"trigger"},{"id":"r2","name":"Decide","type":"condition","config":{"expression":"always_false"}},{"id":"r3","name":"True Branch","type":"action"},{"id":"r4","name":"False Branch","type":"action"}],"edges":[{"source":"r1","target":"r2","type":"next"},{"source":"r2","target":"r3","type":"true"},{"source":"r2","target":"r4","type":"false"}]}}')"
ROUTING_WORKFLOW_ID="$(echo "$ROUTING_WORKFLOW_JSON" | jq -r '.id')"

ROUTING_RUN_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/runs/start \
  -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$ROUTING_WORKFLOW_ID\",\"trigger\":\"manual\"}")"
ROUTING_RUN_ID="$(echo "$ROUTING_RUN_JSON" | jq -r '.id')"

for _ in {1..30}; do
  ROUTING_STATUS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$ROUTING_RUN_ID" | jq -r '.status')"
  if [[ "$ROUTING_STATUS" == "success" || "$ROUTING_STATUS" == "failed" ]]; then
    break
  fi
  sleep 0.2
done
ROUTING_DETAILS="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$ROUTING_RUN_ID")"
echo "$ROUTING_DETAILS" | jq .
if [[ "$(echo "$ROUTING_DETAILS" | jq -r '.status')" != "success" ]]; then
  echo "Expected routing run success."
  exit 1
fi
if ! echo "$ROUTING_DETAILS" | jq -e '.node_results[] | select(.status=="success" and .node_id=="r4")' >/dev/null; then
  echo "Expected false branch node r4 to execute."
  exit 1
fi
if echo "$ROUTING_DETAILS" | jq -e '.node_results[] | select(.status=="success" and .node_id=="r3")' >/dev/null; then
  echo "Expected true branch node r3 to be skipped for always_false."
  exit 1
fi

echo "[9/11] Validating run timeline/log query endpoints..."
TIMELINE_JSON="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$ROUTING_RUN_ID/timeline?status=success&limit=25&order=desc")"
echo "$TIMELINE_JSON" | jq .
if ! echo "$TIMELINE_JSON" | jq -e '.items | type == "array"' >/dev/null; then
  echo "Expected timeline endpoint to return array items."
  exit 1
fi

LOGS_JSON="$(curl -fsS "http://127.0.0.1:8787/api/v1/runs/$ROUTING_RUN_ID/logs?limit=25&order=desc")"
echo "$LOGS_JSON" | jq .
if ! echo "$LOGS_JSON" | jq -e '.items | type == "array"' >/dev/null; then
  echo "Expected logs endpoint to return array items."
  exit 1
fi

echo "[10/11] Validating integration profile endpoints..."
CATALOG_JSON="$(curl -fsS http://127.0.0.1:8787/api/v1/integrations/catalog)"
echo "$CATALOG_JSON" | jq '.items[:3]'
if ! echo "$CATALOG_JSON" | jq -e '.items | length > 0' >/dev/null; then
  echo "Expected non-empty integration catalog."
  exit 1
fi

PROFILE_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/integrations \
  -H 'Content-Type: application/json' \
  -d '{"key":"http_request","name":"Docker Smoke Profile","description":"Created by smoke test","config":{"url":"https://example.com","method":"GET"},"enabled":true}')"
echo "$PROFILE_JSON" | jq .
PROFILE_ID="$(echo "$PROFILE_JSON" | jq -r '.id')"

TEST_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/integrations/test \
  -H 'Content-Type: application/json' \
  -d "{\"profile_id\":\"$PROFILE_ID\",\"input_context\":\"docker smoke integration test\"}")"
echo "$TEST_JSON" | jq .
if [[ "$(echo "$TEST_JSON" | jq -r '.ok')" != "true" ]]; then
  echo "Expected integration profile test to pass."
  exit 1
fi

curl -fsS -X DELETE "http://127.0.0.1:8787/api/v1/integrations/$PROFILE_ID" | jq .

echo "[11/12] Validating bot profile endpoints..."
BOT_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/bots \
  -H 'Content-Type: application/json' \
  -d '{"name":"Docker Smoke Bot","role":"Validate bot API in smoke test","provider":"local","model":"nvidia/nemotron-3-nano","temperature":0.2,"max_tokens":700}')"
echo "$BOT_JSON" | jq .
BOT_ID="$(echo "$BOT_JSON" | jq -r '.id')"

BOT_TEST_JSON="$(curl -fsS -X POST http://127.0.0.1:8787/api/v1/bots/test \
  -H 'Content-Type: application/json' \
  -d "{\"bot_id\":\"$BOT_ID\",\"prompt\":\"Confirm bot test works\"}")"
echo "$BOT_TEST_JSON" | jq .
if [[ "$(echo "$BOT_TEST_JSON" | jq -r '.ok')" != "true" ]]; then
  echo "Expected bot profile test to pass."
  exit 1
fi

curl -fsS -X PATCH "http://127.0.0.1:8787/api/v1/bots/$BOT_ID" \
  -H 'Content-Type: application/json' \
  -d '{"provider":"openai"}' | jq .

curl -fsS -X DELETE "http://127.0.0.1:8787/api/v1/bots/$BOT_ID" | jq .

echo "[12/12] Patching settings and run status..."
curl -fsS -X PATCH http://127.0.0.1:8787/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"theme":"dark","ui_density":"compact","preferred_provider":"local"}' | jq .

curl -fsS -X PATCH "http://127.0.0.1:8787/api/v1/runs/$RETRY_RUN_ID" \
  -H 'Content-Type: application/json' \
  -d '{"status":"success","log":"Smoke test completed"}' | jq .

echo "Smoke test passed."
