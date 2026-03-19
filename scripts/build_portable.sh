#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="6x-protocol-studio"
VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"
PORTABLE_NAME="${PACKAGE_NAME}_${VERSION}_linux_portable"
BUILD_ROOT="${ROOT_DIR}/build/${PORTABLE_NAME}"
APP_DIR="${BUILD_ROOT}/${PACKAGE_NAME}"
OUTPUT_DIR="${ROOT_DIR}/dist"
ARCHIVE_PATH="${OUTPUT_DIR}/${PORTABLE_NAME}.tar.gz"

if [[ -z "${VERSION}" ]]; then
  echo "VERSION file is empty."
  exit 1
fi

rm -rf "${BUILD_ROOT}"
mkdir -p \
  "${APP_DIR}" \
  "${APP_DIR}/packaging/linux/icons" \
  "${OUTPUT_DIR}"

cp -a "${ROOT_DIR}/src" "${APP_DIR}/"
cp "${ROOT_DIR}/main.py" "${ROOT_DIR}/README.md" "${ROOT_DIR}/LICENSE" "${ROOT_DIR}/VERSION" "${APP_DIR}/"
cp "${ROOT_DIR}/packaging/linux/icons/com.sixxprotocol.studio.png" "${APP_DIR}/packaging/linux/icons/"

# Keep portable archive clean and deterministic.
find "${APP_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${APP_DIR}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

cat > "${APP_DIR}/6x-protocol-studio" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${APP_DIR}/main.py" "$@"
EOF

cat > "${APP_DIR}/install-desktop-entry.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
APPLICATIONS_DIR="${XDG_DATA_HOME}/applications"
ICONS_DIR="${XDG_DATA_HOME}/icons/hicolor/512x512/apps"
DESKTOP_FILE="${APPLICATIONS_DIR}/com.sixxprotocol.studio.desktop"
ICON_FILE="${ICONS_DIR}/com.sixxprotocol.studio.png"

mkdir -p "${APPLICATIONS_DIR}" "${ICONS_DIR}"
cp "${APP_DIR}/packaging/linux/icons/com.sixxprotocol.studio.png" "${ICON_FILE}"

cat > "${DESKTOP_FILE}" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=6X-Protocol Studio
Comment=Linux-native automation cockpit with local-first AI workflows
Exec=${APP_DIR}/6x-protocol-studio
Icon=com.sixxprotocol.studio
Terminal=false
Categories=Development;Utility;Network;
Keywords=automation;workflow;ai;nodes;local-first;
StartupNotify=true
DESKTOP

chmod 0755 "${DESKTOP_FILE}" "${APP_DIR}/6x-protocol-studio"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi
echo "Desktop launcher installed."
echo "App command: ${APP_DIR}/6x-protocol-studio"
EOF

cat > "${APP_DIR}/INSTALL.txt" <<'EOF'
6X-Protocol Studio Portable Install
===================================

1) Ensure dependencies are installed:
   sudo apt install -y python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1

2) Run directly:
   ./6x-protocol-studio

3) Optional desktop launcher:
   ./install-desktop-entry.sh
EOF

chmod 0755 "${APP_DIR}/6x-protocol-studio" "${APP_DIR}/install-desktop-entry.sh"

rm -f "${ARCHIVE_PATH}"
tar -C "${BUILD_ROOT}" -czf "${ARCHIVE_PATH}" "${PACKAGE_NAME}"
echo "Built ${ARCHIVE_PATH}"
