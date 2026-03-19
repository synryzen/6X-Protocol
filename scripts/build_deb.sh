#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="6x-protocol-studio"
VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"
ARCHITECTURE="${ARCH:-$(dpkg --print-architecture 2>/dev/null || echo amd64)}"

if [[ -z "${VERSION}" ]]; then
  echo "VERSION file is empty."
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb is required to build .deb packages."
  exit 1
fi

BUILD_ROOT="${ROOT_DIR}/build/${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}"
STAGE_DIR="${BUILD_ROOT}/stage"
APP_DIR="${STAGE_DIR}/opt/${PACKAGE_NAME}"
OUTPUT_DIR="${ROOT_DIR}/dist"
DEB_PATH="${OUTPUT_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}.deb"

rm -rf "${BUILD_ROOT}"
mkdir -p \
  "${STAGE_DIR}/DEBIAN" \
  "${STAGE_DIR}/usr/bin" \
  "${STAGE_DIR}/usr/share/applications" \
  "${STAGE_DIR}/usr/share/icons/hicolor/scalable/apps" \
  "${APP_DIR}" \
  "${OUTPUT_DIR}"

cp -a "${ROOT_DIR}/src" "${APP_DIR}/"
cp "${ROOT_DIR}/main.py" "${ROOT_DIR}/README.md" "${ROOT_DIR}/LICENSE" "${ROOT_DIR}/VERSION" "${APP_DIR}/"
cp "${ROOT_DIR}/packaging/linux/com.sixxprotocol.studio.desktop" "${STAGE_DIR}/usr/share/applications/"
cp "${ROOT_DIR}/packaging/linux/icons/com.sixxprotocol.studio.svg" "${STAGE_DIR}/usr/share/icons/hicolor/scalable/apps/"
cp "${ROOT_DIR}/packaging/linux/bin/6x-protocol-studio" "${STAGE_DIR}/usr/bin/6x-protocol-studio"

chmod 0755 "${STAGE_DIR}/usr/bin/6x-protocol-studio"

# Keep package clean and deterministic.
find "${APP_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${APP_DIR}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

cat > "${STAGE_DIR}/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCHITECTURE}
Maintainer: Synryzen <support@synryzen.com>
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
Recommends: libgtk-4-1, libadwaita-1-0
Homepage: https://github.com/synryzen/6X-Protocol
Description: 6X-Protocol Studio local-first automation cockpit
 Linux-native automation app with visual workflows, AI nodes,
 integrations, run timelines, and daemon control.
EOF

cat > "${STAGE_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
EOF

cat > "${STAGE_DIR}/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
EOF

chmod 0755 "${STAGE_DIR}/DEBIAN/postinst" "${STAGE_DIR}/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "${STAGE_DIR}" "${DEB_PATH}" >/dev/null
echo "Built ${DEB_PATH}"
