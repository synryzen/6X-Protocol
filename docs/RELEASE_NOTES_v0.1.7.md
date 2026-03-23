# 6X-Protocol Studio v0.1.7

Release date: March 23, 2026

## Highlights
- Desktop + Docker release track is now fully launch-ready with validated
  release readiness checks.
- Docker Web canvas now supports direct wire dragging from output ports to input
  ports with live preview and duplicate-link protection.
- Public launch docs are now included so publishing to GitHub Pages/Releases is
  straightforward.

## What’s Improved
- Web visual graph stage:
  - draggable node cards
  - live SVG links
  - direct port-to-port link creation
  - auto-arrange + fit-view actions
- Project documentation:
  - launch checklist for public rollout
  - updated release/download links for `v0.1.7`

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
