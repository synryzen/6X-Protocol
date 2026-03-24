# 6X-Protocol Studio v0.1.8

Release date: March 24, 2026

## Highlights
- Canvas interaction reliability improved again: node drag jitter/shake was
  eliminated by enforcing single drag-driver ownership, and inspector sidebar
  scroll position no longer snaps back to top during node edits.
- Docker API gained workflow preflight endpoint parity and the web preflight
  action now validates through API first (with local fallback), so warnings and
  errors better match runtime behavior.
- Release operations are streamlined with a new `github_finalize.sh` helper and
  refreshed launch/docs links for current version assets.

## What’s Improved
- Desktop canvas:
  - smoother drag behavior on GTK stacks that previously flickered
  - stable node selection flow while dragging/linking
  - inspector mode keeps user scroll context unless mode actually changes
- Docker/Web:
  - `POST /api/v1/workflows/{id}/preflight` endpoint added
  - web preflight button now uses server validation by default
  - smoke suite verifies preflight endpoint in end-to-end compose flow
- Project docs + release flow:
  - release/site/download references moved to `v0.1.8`
  - new `./scripts/github_finalize.sh` for final pre-publish checks

## Validation
- Unit tests: `python3 -m unittest` (pass)
- Docker smoke: `./scripts/test_docker_web.sh` (pass)
- Release readiness: `./scripts/release_readiness.sh` (pass)

## Linux Downloads (GitHub Release Artifacts)
- `.deb` installer
- portable `.tar.gz`
- `.AppImage` (release workflow environment)
- `.flatpak` (release workflow environment)
- `SHA256SUMS.txt`

## Upgrade Notes
- Existing users can install over previous versions with the latest `.deb` or
  switch to the portable build.
- No data migration action is required for normal local workflow/settings
  storage.
