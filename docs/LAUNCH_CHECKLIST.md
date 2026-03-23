# 6X-Protocol Studio Launch Checklist

Use this checklist when you are ready to publicly announce the project.

## 1. Pre-Launch Validation (Local)
- Activate environment: `source .venv/bin/activate`
- Run readiness checks: `./scripts/release_readiness.sh`
- Confirm output includes:
  - `Release readiness checks passed.`
  - `Smoke test passed.`
- Confirm package artifacts exist in `dist/`:
  - `.deb`
  - portable `.tar.gz`
  - `SHA256SUMS.txt`

## 2. GitHub Repo Visibility
- Go to repository settings:
  - `https://github.com/synryzen/6X-Protocol/settings`
- Set repository to **Public** (if still private).

## 3. GitHub Pages (Project Site)
- Open Pages settings:
  - `https://github.com/synryzen/6X-Protocol/settings/pages`
- Source: **GitHub Actions**.
- Confirm Pages workflow succeeds:
  - `https://github.com/synryzen/6X-Protocol/actions`
- Verify live site:
  - `https://synryzen.github.io/6X-Protocol/`

## 4. GitHub Release
- Build artifacts:
  - `./scripts/build_packages.sh`
- Create tag and release (example):
  - Tag: `v0.1.6` (or next version)
  - Title: `6X-Protocol Studio v0.1.6`
- Upload `dist/*` artifacts to the release:
  - `.deb`
  - portable `.tar.gz`
  - optional `.AppImage` and `.flatpak` (if available)
  - `SHA256SUMS.txt`

## 5. Docker/Web Verification
- Validate compose stack before announcement:
  - `./scripts/test_docker_web.sh`
- Confirm these URLs work when stack is up:
  - Web UI: `http://localhost:8080`
  - API docs: `http://localhost:8787/docs`

## 6. Public Messaging
- Update announcement text with:
  - GitHub repo URL
  - Releases URL
  - Pages URL
  - Key features (local-first desktop + self-hosted Docker web)
- Share across:
  - X/Twitter
  - Reddit (relevant dev/self-hosted communities)
  - Hacker News (Show HN)
  - Linux communities / Discord servers

## 7. Post-Launch Hygiene
- Keep Issues and Discussions monitored daily for first week.
- Label and triage incoming bugs quickly.
- Pin a “Getting Started” issue for new users.
- Publish a short patch release fast if startup/canvas issues are reported.
