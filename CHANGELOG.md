# Changelog

All notable changes to this project are documented here.

## [Unreleased]
### Changed
- Canvas node interaction reliability hardened again:
  stage/node gesture arbitration tightened, node hit fallback now keeps inspector
  selection in sync, and output port drag hit-targets are easier to catch for
  wire linking.
- Canvas node settings now apply context-aware execution defaults:
  trigger mode profiles (manual/interval/cron/webhook/watch) and action template
  context can auto-tune retry/backoff/timeout behavior.
- New nodes now persist baseline execution defaults at creation time so run
  behavior is deterministic before first manual edit.
- Execution runtime defaults are now aligned with canvas trigger profiles in
  both desktop and Docker/web engines (manual/interval/cron/webhook/file-watch)
  so retry/backoff/timeout behavior is consistent across UI and API runs.
- Docker/web runtime status synchronized with latest smoke validation:
  end-to-end compose test now confirms run start/cancel/retry flows, retry-from-
  failed-node replay, timeout/retry/backoff behavior, routing timeline filters,
  and integration profile create/test/delete lifecycle.
- README Docker progress updated to reflect active preview completion at ~84%.

## [0.1.4] - 2026-03-19
### Added
- In-app About page with creator/support identity and direct links:
  Developer Matthew C Elliott, synryzen.com, GitHub, and support email.
- GitHub Pages marketing expansion with dedicated app showcase pages for:
  NodeSpark, IQPearl, Write JSON, Lexora, and GhostLedger.
- Branded hero imagery pipeline for Pages (PNG + optimized WebP variants).

### Changed
- Linux packaging icon assets switched to the new fox artwork for `.deb`,
  portable desktop launcher install, AppImage, and Flatpak builds.
- Canvas link reliability improved with non-interactive link layer, live stage
  pointer tracking during link drags, and release-to-connect finalization.
- Versioning and release pipeline prepared for `v0.1.4` artifact publishing.

## [0.1.0] - 2026-03-19
### Added
- Multi-view app shell with dashboard, workflows, canvas, bots, runs, integrations, marketplace, daemon, settings.
- Visual canvas graph editor with drag/drop nodes, linking, inspector editing, preflight checks, zoom/pan, minimap.
- Execution engine with retries/backoff/timeout policy support and run timeline records.
- Unified AI service adapter for local and cloud providers.
- Integrations registry with built-in connectors and quick setup/test tooling.
- Settings storage with theme/runtime/provider options.
- Premium UI theming pass with compact controls and panelized layout.

### Changed
- Canvas node behavior expanded with integration-specific field UX and node-level execution defaults.
- Dark/light visual preset support and global appearance controls.

### Fixed
- Startup traceback issues around missing view attributes.
- Multiple CSS parser errors and control sizing regressions.
- Canvas link/selection reliability regressions across recent UI passes.
