#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="6x-protocol-studio"
VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"
ARCH="${ARCH:-x86_64}"
BUILD_ROOT="${ROOT_DIR}/build/${PACKAGE_NAME}_appimage"
APPDIR="${BUILD_ROOT}/${PACKAGE_NAME}.AppDir"
OUTPUT_DIR="${ROOT_DIR}/dist"
OUTPUT_PATH="${OUTPUT_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.AppImage"

APPIMAGETOOL_BIN="${APPIMAGETOOL:-appimagetool}"
if ! command -v "${APPIMAGETOOL_BIN}" >/dev/null 2>&1; then
  if [[ -x "/tmp/appimagetool" ]]; then
    APPIMAGETOOL_BIN="/tmp/appimagetool"
  else
    echo "appimagetool not found. Install it or set APPIMAGETOOL=/path/to/appimagetool."
    exit 1
  fi
fi

rm -rf "${BUILD_ROOT}"
mkdir -p \
  "${APPDIR}/usr/share/applications" \
  "${APPDIR}/usr/share/icons/hicolor/512x512/apps" \
  "${APPDIR}/opt/${PACKAGE_NAME}" \
  "${OUTPUT_DIR}"

cp -a "${ROOT_DIR}/src" "${APPDIR}/opt/${PACKAGE_NAME}/"
cp "${ROOT_DIR}/main.py" "${ROOT_DIR}/README.md" "${ROOT_DIR}/LICENSE" "${ROOT_DIR}/VERSION" "${APPDIR}/opt/${PACKAGE_NAME}/"
cp "${ROOT_DIR}/packaging/linux/com.sixxprotocol.studio.desktop" "${APPDIR}/usr/share/applications/"
cp "${ROOT_DIR}/packaging/linux/icons/com.sixxprotocol.studio.png" "${APPDIR}/usr/share/icons/hicolor/512x512/apps/"

# AppImage expects these at AppDir root too.
cp "${ROOT_DIR}/packaging/linux/com.sixxprotocol.studio.desktop" "${APPDIR}/com.sixxprotocol.studio.desktop"
cp "${ROOT_DIR}/packaging/linux/icons/com.sixxprotocol.studio.png" "${APPDIR}/com.sixxprotocol.studio.png"

find "${APPDIR}/opt/${PACKAGE_NAME}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${APPDIR}/opt/${PACKAGE_NAME}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

cat > "${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/env python3 "${HERE}/opt/6x-protocol-studio/main.py" "$@"
EOF
chmod 0755 "${APPDIR}/AppRun"

rm -f "${OUTPUT_PATH}"
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="${ARCH}" "${APPIMAGETOOL_BIN}" "${APPDIR}" "${OUTPUT_PATH}" >/dev/null
echo "Built ${OUTPUT_PATH}"
