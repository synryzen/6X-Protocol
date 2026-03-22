# Changelog

All notable changes to this project are documented here.

## [Unreleased]
### Changed
- Docker Web graph node editor now includes structured condition controls
  (mode/value/min-length/raw), OpenWeather units configuration, and smarter
  per-node recommended execution preset defaults by node type/integration.
- Docker Web graph preflight now validates condition-mode inputs more clearly,
  including invalid regex detection and missing condition values for value-based
  modes.
- Docker runtime condition execution now supports richer expressions
  (`not_contains:`, `regex:`, `min_len:`) and structured fallback config
  (`condition_mode`, `condition_value`, `condition_min_len`).
- Canvas node drag now includes a stage-level fallback drag owner when node
  gesture ownership is missed, and frame drag handlers no longer cancel active
  output-port drag sessions, restoring click-hold move reliability and drag-to-
  wire linking on stricter GTK gesture stacks.
- Canvas event routing now uses bubble-phase stage click/drag handlers to avoid
  stealing pointer ownership from node gestures, restoring reliable node move,
  click-to-inspector selection, and drag-to-link interactions.
- Canvas auto-link source selection now prefers open tail nodes so repeatedly
  adding modules forms a stable serial chain by default.
- Canvas node press now updates selection/inspector independently of the
  post-drag click suppression guard, preventing stale inspector panels after
  drag interactions.
- Canvas drag ownership now prefers per-node gestures; stage box-select no
  longer claims normal node drags, and stage-motion fallback updates run only
  for stage-owned drags. This removes competing drag updates that caused
  flicker/shake and unreliable inspector switching during node interaction.
- Docker API now includes bots CRUD + test endpoints (`/api/v1/bots*`) with
  persisted bot profiles and test-result history.
- Docker Web Access now includes a Bot Profiles + Test panel and a live Bots
  metric, with save/test/refresh flows wired to the new API endpoints.
- Docker web node editor now surfaces live integration guidance: required-field
  completion status updates while typing and integration-specific placeholders
  are applied for webhook/API, Twilio, email, SQL, Redis, weather, and handoff
  connectors.
- Docker web graph preflight now treats missing required action integration
  fields as errors (not warnings) to better match desktop validation strictness.
- Docker web graph editor node behavior panel now includes richer
  integration-specific action fields (Twilio account/auth, delivery envelope,
  subject/domain, headers) with dynamic visibility and save/load/default wiring.
- Canvas drag/link stability now enforces a single drag owner per gesture
  sequence (stage fallback vs node controller), preventing competing handlers
  from fighting and causing node shake or frozen drags.
- Canvas node hit-testing and connector anchors now use live widget geometry
  instead of fixed card constants, improving click/drag/select/link accuracy
  across theme density/layout changes.
- Canvas node interaction reliability hardened again:
  stage/node gesture arbitration tightened, node hit fallback now keeps inspector
  selection in sync, and output port drag hit-targets are easier to catch for
  wire linking.
- Canvas gesture stability received another reliability pass:
  stage Shift-select drag no longer competes with normal node drag/link
  gestures, clicked-node fallback now always refreshes inspector state, spawn
  placement avoids overlap via ring/grid probing, and output-port wire drags use
  live pointer tracking for more consistent release-to-connect behavior.
- Canvas drag resilience improved further with a stage-motion fallback that
  continues active node movement using live pointer coordinates when some GTK
  environments miss intermittent node drag-update callbacks.
- Canvas input routing now uses capture-phase stage click/drag/motion
  controllers as a reliability backstop, so node selection, inspector sync,
  drag-move, and output-handle wire drags still work when child widgets swallow
  pointer events on certain GTK setups.
- New non-trigger nodes now include auto-link source fallback logic so module
  add operations keep serial wiring even if the primary selected source is stale.
- Docker/web runtime action execution now includes explicit `handoff` behavior:
  bot-chain directives are parsed (`Bot A > Bot B`) and the output context is
  transformed through each handoff step for deterministic preview/testing.
- Node execution default profiles now classify `handoff` as a heavy integration
  (higher timeout/backoff profile) consistently across canvas suggestions,
  desktop runtime execution policy resolution, and Docker/web runtime policy.
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
