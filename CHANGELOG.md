# Changelog

All notable changes to this project are documented here.

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

