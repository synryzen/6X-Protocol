# Contributing

Thanks for helping improve 6X-Protocol Studio.

Contributions are welcome. By submitting code, you agree maintainers may modify,
adapt, or decline changes to keep the project aligned with roadmap and quality standards.

## First Steps
1. Read [README.md](README.md), [ROADMAP.md](ROADMAP.md), and [GOVERNANCE.md](GOVERNANCE.md).
2. For major work, open an issue before implementation.
3. Keep PRs focused and small whenever possible.

## Setup
1. Clone and enter repo.
2. Install Linux deps (`python3-gi`, `gtk4`, `libadwaita` bindings).
3. Run:
```bash
python3 main.py
```

## Contribution Types We Prefer
- Bug fixes and regression repairs.
- Documentation and setup improvements.
- Linux packaging and installer improvements.
- Test coverage and reliability work.
- Integrations/connectors and node improvements that align with roadmap.
- UX polish that improves clarity, accessibility, and speed.

## Requires Maintainer Discussion First
- Major architecture changes.
- Security/auth, licensing, or monetization-impacting behavior.
- Branding or trademark-sensitive UI/content.
- Changes that alter product direction or core workflow model.

## Development Guidelines
- Keep UI compact and consistent with premium panel style.
- Prefer reusable components over one-off controls.
- Preserve current interactions unless intentionally improved.
- Add or update tests when behavior changes.

Canvas changes must verify:
- Node drag
- Link drag/click
- Zoom/pan/minimap
- Save/load graph

Integration changes must include:
- Required field validation
- Save and test behavior
- Clear error messages

## Quality Checks
Run before PR:
```bash
python3 -m compileall src main.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Pull Request Expectations
- Keep PR scope narrow and explain intent clearly.
- Include screenshots/GIFs for visible UI changes.
- Mention risk areas (canvas interactions, settings persistence, integrations, run engine).
- Link the related issue and describe validation steps.
- Be responsive to review feedback and follow-up updates.
