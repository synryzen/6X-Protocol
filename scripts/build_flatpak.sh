#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="6x-protocol-studio"
APP_ID="com.sixxprotocol.studio"
VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"
ARCH="${ARCH:-x86_64}"
BRANCH="${FLATPAK_BRANCH:-stable}"

MANIFEST="${ROOT_DIR}/packaging/flatpak/com.sixxprotocol.studio.yml"
BUILD_ROOT="${ROOT_DIR}/build/${PACKAGE_NAME}_flatpak"
BUILD_DIR="${BUILD_ROOT}/build-dir"
REPO_DIR="${BUILD_ROOT}/repo"
OUTPUT_DIR="${ROOT_DIR}/dist"
OUTPUT_PATH="${OUTPUT_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.flatpak"

if ! command -v flatpak >/dev/null 2>&1 || ! command -v flatpak-builder >/dev/null 2>&1; then
  echo "flatpak and flatpak-builder are required."
  exit 1
fi

flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo >/dev/null 2>&1 || true

rm -rf "${BUILD_ROOT}"
mkdir -p "${BUILD_DIR}" "${REPO_DIR}" "${OUTPUT_DIR}"

flatpak-builder \
  --force-clean \
  --user \
  --install-deps-from=flathub \
  --repo="${REPO_DIR}" \
  "${BUILD_DIR}" \
  "${MANIFEST}" >/dev/null

flatpak build-bundle "${REPO_DIR}" "${OUTPUT_PATH}" "${APP_ID}" "${BRANCH}" >/dev/null
echo "Built ${OUTPUT_PATH}"
