# 6X-Protocol Studio v0.1.9

Release date: March 24, 2026

## Highlights
- Canvas drag/link reliability improved again on Linux GTK stacks where
  pointer-gesture ownership can drift between node and stage handlers.
- Node dragging no longer gets blocked by stale output-port hover state.
- Node drag jitter was reduced by removing duplicate stage-motion fallback
  updates during node-owned drags.
- Release docs and GitHub Pages links are updated to `v0.1.9` artifacts and
  launch kits.

## What’s Improved
- Desktop canvas:
  - Stage fallback now clears stale output-port hover before deciding drag mode.
  - Node drags remain node-owned without parallel fallback updates.
  - Selection + inspector behavior remains stable while dragging and linking.
- Docs/release flow:
  - Version train advanced to `0.1.9` in site/download links.
  - New announcement kits and launch calendar added for `v0.1.9`.
  - Launch checklist examples now reference `v0.1.9`.

## Validation
- Unit tests: `python3 -m unittest` (pass)
- Canvas translation/gesture tests: `python3 -m unittest tests.test_canvas_coordinate_translation` (pass)
- Docker smoke: `./scripts/test_docker_web.sh` (pass, included in readiness run)
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
- No manual data migration is required for standard local workflow/settings
  storage.
