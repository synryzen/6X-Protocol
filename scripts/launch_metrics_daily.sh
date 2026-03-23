#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADD_SCRIPT="${ROOT_DIR}/scripts/launch_metrics_add.py"
SUMMARY_SCRIPT="${ROOT_DIR}/scripts/launch_metrics_summary.py"
SYNC_SCRIPT="${ROOT_DIR}/scripts/launch_metrics_sync_github.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -f "${ADD_SCRIPT}" ]]; then
  echo "Missing updater script: ${ADD_SCRIPT}"
  exit 1
fi

if [[ ! -f "${SUMMARY_SCRIPT}" ]]; then
  echo "Missing summary script: ${SUMMARY_SCRIPT}"
  exit 1
fi

if [[ ! -f "${SYNC_SCRIPT}" ]]; then
  echo "Missing GitHub sync script: ${SYNC_SCRIPT}"
  exit 1
fi

prompt_default() {
  local label="$1"
  local default_value="$2"
  local input
  read -r -p "${label} [${default_value}]: " input
  if [[ -z "${input}" ]]; then
    printf '%s' "${default_value}"
  else
    printf '%s' "${input}"
  fi
}

prompt_optional() {
  local label="$1"
  local input
  read -r -p "${label} (blank to skip): " input
  printf '%s' "${input}"
}

prompt_yes_no() {
  local label="$1"
  local default_value="$2"
  local input normalized
  read -r -p "${label} [${default_value}]: " input
  if [[ -z "${input}" ]]; then
    normalized="${default_value}"
  else
    normalized="${input}"
  fi
  normalized="$(printf '%s' "${normalized}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${normalized}" == "y" || "${normalized}" == "yes" ]]; then
    printf 'yes'
  else
    printf 'no'
  fi
}

sync_from_github() {
  local entry_date="$1"
  local mode="$2"
  local sync_mode
  if [[ "${mode}" == "yes" ]]; then
    sync_mode="add"
  else
    sync_mode="set"
  fi
  echo
  echo "Syncing stars/downloads from GitHub..."
  "${PYTHON_BIN}" "${SYNC_SCRIPT}" --date "${entry_date}" --mode "${sync_mode}"
}

echo
echo "6X-Protocol Launch Metrics Daily Update"
echo "---------------------------------------"

default_date="$(date +%F)"
entry_date="$(prompt_default "Date (YYYY-MM-DD)" "${default_date}")"
add_mode="$(prompt_yes_no "Add numeric values to existing row?" "no")"
auto_sync="$(prompt_yes_no "Auto-sync stars/downloads from GitHub release?" "yes")"

day_label="$(prompt_optional "Day label (example: Day 1)")"
channel_focus="$(prompt_optional "Channel focus (example: Launch)")"
notes="$(prompt_optional "Notes")"
append_note="$(prompt_optional "Append note")"

posts="$(prompt_optional "Posts count")"
impressions="$(prompt_optional "Impressions")"
clicks="$(prompt_optional "Link clicks")"
repo_views="$(prompt_optional "Repo views")"
stars="$(prompt_optional "Stars gained")"
downloads="$(prompt_optional "Release downloads")"
deb="$(prompt_optional ".deb downloads")"
portable="$(prompt_optional "Portable downloads")"
appimage="$(prompt_optional "AppImage downloads")"
flatpak="$(prompt_optional "Flatpak downloads")"
page_views="$(prompt_optional "Pages views")"
issues="$(prompt_optional "Issues opened")"
discussions="$(prompt_optional "Discussions opened")"
signups="$(prompt_optional "Newsletter signups")"

args=(--date "${entry_date}")
if [[ "${add_mode}" == "yes" ]]; then
  args+=(--add)
fi

if [[ -n "${day_label}" ]]; then
  args+=(--day-label "${day_label}")
fi
if [[ -n "${channel_focus}" ]]; then
  args+=(--channel-focus "${channel_focus}")
fi
if [[ -n "${notes}" ]]; then
  args+=(--notes "${notes}")
fi
if [[ -n "${append_note}" ]]; then
  args+=(--append-note "${append_note}")
fi

if [[ -n "${posts}" ]]; then args+=(--posts "${posts}"); fi
if [[ -n "${impressions}" ]]; then args+=(--impressions "${impressions}"); fi
if [[ -n "${clicks}" ]]; then args+=(--clicks "${clicks}"); fi
if [[ -n "${repo_views}" ]]; then args+=(--repo-views "${repo_views}"); fi
if [[ -n "${stars}" ]]; then args+=(--stars "${stars}"); fi
if [[ -n "${downloads}" ]]; then args+=(--downloads "${downloads}"); fi
if [[ -n "${deb}" ]]; then args+=(--deb "${deb}"); fi
if [[ -n "${portable}" ]]; then args+=(--portable "${portable}"); fi
if [[ -n "${appimage}" ]]; then args+=(--appimage "${appimage}"); fi
if [[ -n "${flatpak}" ]]; then args+=(--flatpak "${flatpak}"); fi
if [[ -n "${page_views}" ]]; then args+=(--page-views "${page_views}"); fi
if [[ -n "${issues}" ]]; then args+=(--issues "${issues}"); fi
if [[ -n "${discussions}" ]]; then args+=(--discussions "${discussions}"); fi
if [[ -n "${signups}" ]]; then args+=(--signups "${signups}"); fi

echo
echo "Updating launch metrics..."
"${PYTHON_BIN}" "${ADD_SCRIPT}" "${args[@]}"

if [[ "${auto_sync}" == "yes" ]]; then
  sync_from_github "${entry_date}" "${add_mode}"
fi

summary_format="$(prompt_yes_no "Print markdown summary?" "no")"
echo
echo "Current launch summary:"
if [[ "${summary_format}" == "yes" ]]; then
  "${PYTHON_BIN}" "${SUMMARY_SCRIPT}" --markdown
else
  "${PYTHON_BIN}" "${SUMMARY_SCRIPT}"
fi
