# App Finish Plan

This is the execution track to complete a strong public `v1`.

## Phase 1: Stability + Reliability (Immediate)
- Lock canvas linking behavior (drag + click) and regression test all gestures.
- Harden node inspector state transitions (selected vs no selection modes).
- Validate required integration fields inline before apply/test.
- Remove all runtime tracebacks across all views.
- Performance pass for large graphs and large list views.

## Phase 2: Node Behavior Depth
- Trigger node presets:
  - Manual
  - Interval
  - Cron
  - Webhook
  - File watch
- Action node integration-aware forms with required hints and contextual defaults.
- Condition node editor improvements and branch preview.
- AI node model/provider override + quick test with structured output preview.

## Phase 3: Execution Engine v2
- Deterministic run policy per node type.
- Retry/backoff/timeout behavior clarity in timeline.
- Retry from failed node.
- Resume/cancel UX and cleaner status transitions.
- Error workflow routing policy per node.

## Phase 4: Integration Maturity
- Ensure every built-in connector has:
  - Save
  - Test
  - Required fields template
  - Actionable error messaging
- Add integration packs docs/examples.
- Add import/export of integration test profiles.

## Phase 5: Release Hardening
- Add smoke tests for core services and data stores.
- Add CI checks for compile/lint/smoke.
- Produce release artifacts and tag `v0.1.0`.
- Final docs/screenshots and launch notes.

## Phase 6: Post-Launch Expansion
- Plugin SDK for external connectors.
- Workflow templates marketplace growth.
- Better observability and telemetry panels.
- Optional enterprise secret backends.

