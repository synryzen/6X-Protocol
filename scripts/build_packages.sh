#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
REQUIRE_ALL="${REQUIRE_ALL_PACKAGES:-0}"

mkdir -p "${DIST_DIR}"
rm -f "${DIST_DIR}"/*.deb "${DIST_DIR}"/*.tar.gz "${DIST_DIR}"/*.AppImage "${DIST_DIR}"/*.flatpak "${DIST_DIR}/SHA256SUMS.txt" 2>/dev/null || true

run_step() {
  local title="$1"
  shift
  if "$@"; then
    return 0
  fi

  if [[ "${REQUIRE_ALL}" == "1" ]]; then
    echo "Required package step failed: ${title}"
    exit 1
  fi
  echo "Skipping optional package step: ${title}"
}

bash "${ROOT_DIR}/scripts/build_deb.sh"
bash "${ROOT_DIR}/scripts/build_portable.sh"
run_step "AppImage" bash "${ROOT_DIR}/scripts/build_appimage.sh"
run_step "Flatpak" bash "${ROOT_DIR}/scripts/build_flatpak.sh"

shopt -s nullglob
artifacts=(
  "${DIST_DIR}"/*.deb
  "${DIST_DIR}"/*.tar.gz
  "${DIST_DIR}"/*.AppImage
  "${DIST_DIR}"/*.flatpak
)

if [[ "${#artifacts[@]}" -eq 0 ]]; then
  echo "No artifacts found in ${DIST_DIR}"
  exit 1
fi

sha256sum "${artifacts[@]}" > "${DIST_DIR}/SHA256SUMS.txt"

echo "Built package artifacts in ${DIST_DIR}"
