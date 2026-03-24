#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

green() { printf '\033[0;32m%s\033[0m\n' "${1:-}"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "${1:-}"; }
red() { printf '\033[0;31m%s\033[0m\n' "${1:-}"; }
info() { printf '%s\n' "${1:-}"; }

extract_owner_repo() {
  local remote="$1"
  local trimmed="${remote%.git}"
  if [[ "$trimmed" =~ github\.com[:/]([^/]+)/([^/]+)$ ]]; then
    printf "%s/%s" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

info "== 6X-Protocol GitHub Finalize Helper =="
info

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  red "Not inside a git repository."
  exit 1
fi

REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE_URL" ]]; then
  red "Remote 'origin' is not configured."
  exit 1
fi

OWNER_REPO="$(extract_owner_repo "$REMOTE_URL" || true)"
if [[ -z "$OWNER_REPO" ]]; then
  yellow "Could not parse owner/repo from origin URL: $REMOTE_URL"
else
  green "Repository: $OWNER_REPO"
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" == "main" ]]; then
  green "Branch: $CURRENT_BRANCH"
else
  yellow "Branch: $CURRENT_BRANCH (recommended: main)"
fi

if git diff --quiet && git diff --cached --quiet; then
  green "Working tree: clean"
else
  yellow "Working tree has uncommitted changes"
fi

VERSION="0.1.0"
if [[ -f VERSION ]]; then
  VERSION="$(tr -d '[:space:]' < VERSION)"
fi
info "Version file: $VERSION"
info

info "Local readiness command:"
info "  ./scripts/release_readiness.sh"
info

if [[ -n "$OWNER_REPO" ]]; then
  info "GitHub setup URLs:"
  info "  Repo:   https://github.com/$OWNER_REPO"
  info "  Pages:  https://github.com/$OWNER_REPO/settings/pages"
  info "  Actions:https://github.com/$OWNER_REPO/actions"
  info "  Release:https://github.com/$OWNER_REPO/releases"
  info
fi

info "Tag + push release (when ready):"
info "  git tag -a v${VERSION} -m \"6X-Protocol Studio v${VERSION}\""
info "  git push origin v${VERSION}"
info

if command -v gh >/dev/null 2>&1 && [[ -n "$OWNER_REPO" ]]; then
  info "GitHub CLI checks:"
  if VISIBILITY="$(gh api "repos/$OWNER_REPO" --jq '.visibility' 2>/dev/null)"; then
    green "  visibility: $VISIBILITY"
  else
    yellow "  could not read repo visibility with gh (auth may be required)."
  fi
  if PAGE_URL="$(gh api "repos/$OWNER_REPO/pages" --jq '.html_url' 2>/dev/null)"; then
    green "  pages: $PAGE_URL"
  else
    yellow "  pages: not enabled yet (or API access denied)."
  fi
fi

info
green "Done. Use this helper any time before publishing a new release."
