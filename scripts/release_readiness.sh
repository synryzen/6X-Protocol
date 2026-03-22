#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"

REQUIRE_DOCKER="${REQUIRE_DOCKER_SMOKE:-0}"
RUN_DOCKER_SMOKE=1
if [[ "${SKIP_DOCKER_SMOKE:-0}" == "1" ]]; then
  RUN_DOCKER_SMOKE=0
fi

step() {
  echo
  echo "==> $1"
}

cd "$ROOT_DIR"

step "Compile check"
python3 -m compileall -q src main.py

step "Unit tests"
python3 -m unittest discover -s tests -p 'test_*.py'

if [[ "$RUN_DOCKER_SMOKE" == "1" ]]; then
  if command -v docker >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
    step "Docker/web smoke"
    ./scripts/test_docker_web.sh
  elif [[ "$REQUIRE_DOCKER" == "1" ]]; then
    echo "Docker smoke required but docker/jq is missing."
    exit 1
  else
    step "Docker/web smoke (skipped)"
    echo "Skipping because docker or jq is unavailable. Set REQUIRE_DOCKER_SMOKE=1 to enforce."
  fi
else
  step "Docker/web smoke (disabled)"
  echo "Skipping because SKIP_DOCKER_SMOKE=1 was set."
fi

step "Package build"
./scripts/build_packages.sh

step "Artifact verification"
if [[ ! -f "${DIST_DIR}/SHA256SUMS.txt" ]]; then
  echo "Missing ${DIST_DIR}/SHA256SUMS.txt"
  exit 1
fi

DEB_COUNT="$(find "${DIST_DIR}" -maxdepth 1 -type f -name '*.deb' | wc -l | tr -d ' ')"
PORTABLE_COUNT="$(find "${DIST_DIR}" -maxdepth 1 -type f -name '*.tar.gz' | wc -l | tr -d ' ')"
if [[ "${DEB_COUNT}" -lt 1 ]]; then
  echo "Expected at least one .deb artifact."
  exit 1
fi
if [[ "${PORTABLE_COUNT}" -lt 1 ]]; then
  echo "Expected at least one portable .tar.gz artifact."
  exit 1
fi

echo
echo "Release readiness checks passed."
echo "Artifacts in ${DIST_DIR}:"
ls -1 "${DIST_DIR}" | sed 's/^/- /'
