#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"

bash "${ROOT_DIR}/scripts/build_deb.sh"
bash "${ROOT_DIR}/scripts/build_portable.sh"

(
  cd "${DIST_DIR}"
  sha256sum *.deb *.tar.gz > SHA256SUMS.txt
)

echo "Built package artifacts in ${DIST_DIR}"
