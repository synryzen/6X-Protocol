# Contributing

Thanks for helping improve 6X-Protocol Studio.

## Setup
1. Clone and enter repo.
2. Install Linux deps (`python3-gi`, `gtk4`, `libadwaita` bindings).
3. Run:
```bash
python3 main.py
```

## Development Guidelines
- Keep UI compact and consistent with existing premium panel style.
- Prefer reusable components over one-off controls.
- For canvas work, always verify:
  - Node drag
  - Link drag/click
  - Zoom/pan/minimap
  - Save/load graph
- For integrations, include:
  - Required field validation
  - Save and test behavior
  - Useful error messages

## Quality Checks
Run before PR:
```bash
python3 -m compileall src main.py
```

## PR Scope
- Keep PRs focused.
- Include screenshots/GIFs for visible UI changes.
- Mention risk areas (canvas interactions, settings persistence, integrations, run engine).

