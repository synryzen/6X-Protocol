# Tutorial: Build Your First Workflow

Last verified: **March 24, 2026**

Goal: create a simple `Trigger -> AI -> Action` flow, then run and validate it.

## 1. Create Workflow
1. Open **Workflows**.
2. Click **New Workflow**.
3. Name it: `First Workflow`.
4. Status: `draft`.

## 2. Build Graph in Canvas
1. Open **Canvas** and select `First Workflow`.
2. Add nodes:
   - `Trigger` (manual)
   - `AI` (prompt processing)
   - `Action` (standard or integration route)
3. Drag links:
   - Trigger output -> AI input
   - AI output -> Action input
4. Save graph.

## 3. Configure Node Behavior
- Trigger node:
  - Mode: `manual` (or schedule/webhook if available)
- AI node:
  - Provider/model from your settings or node override
  - Prompt template with clear output instruction
- Action node:
  - Integration type (e.g. Slack, HTTP, Telegram, Gmail)
  - Required fields shown by integration hints

## 4. Preflight + Run
1. Click **Preflight** and resolve any errors.
2. Click **Save**.
3. Click **Run**.

## 5. Validate Run
1. Open **Runs**.
2. Select latest run.
3. Verify node order and statuses in timeline.
4. If failed, use **Retry** or **Retry from Failed Node**.

## 6. Common Improvements
- Add `Condition` node for branch logic.
- Set execution defaults (retry/backoff/timeout).
- Add action presets for common integrations.
- Export integration profile bundle for reuse.
