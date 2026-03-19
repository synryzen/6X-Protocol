# 6X-Protocol Studio

Linux-native, local-first workflow automation studio with visual graph building, AI nodes, integrations, bot profiles, run timelines, and daemon execution.

## Why This Exists
6X-Protocol Studio is built to give users a powerful automation control room that runs on Linux machines without forcing cloud lock-in.

## Current Feature Set
- Dashboard with live counts and operational status.
- Workflows CRUD and graph persistence.
- Canvas builder with draggable nodes, links, zoom/pan, minimap, preflight validation, and inspector editing.
- Node types: `Trigger`, `Action`, `AI`, `Condition`.
- Runs model and history timeline.
- Bots CRUD and AI test console.
- Integrations hub with quick setup cards and connector test actions.
- Settings hub for runtime, AI providers, appearance, and automation behavior.
- Local AI and cloud AI provider support via a unified adapter.

## Built-In Integrations (Current)
- Core: HTTP POST/Request, File Append, Shell Command, Approval Gate, Bot Handoff.
- Communication: Slack, Discord, Teams, Telegram, Gmail, Outlook Graph, Twilio, Resend, Mailgun.
- Data/Productivity: OpenWeather, Google Apps Script, Google Sheets, Google Calendar API, Notion, Airtable.
- CRM/Business: HubSpot, Stripe, Salesforce, Pipedrive, Zendesk.
- Developer/Project: GitHub, GitLab, Linear, Jira, Asana, ClickUp, Trello, Monday.
- Database/Infra: Postgres, MySQL, SQLite, Redis, S3 CLI.

## Quick Start (Linux)
1. Install system dependencies:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```
2. Run the app:
```bash
cd 6X-Protocol
python3 main.py
```
3. Optional virtual env:
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 main.py
```

## Data Location
User data is stored under:
`~/.local/share/6x-protocol-studio/`

## Product Site / GitHub Page
The project page content is in [`docs/index.html`](docs/index.html) and auto-deploys via GitHub Actions when Pages is enabled.

Planned Pages URL:
`https://synryzen.github.io/6X-Protocol/`

## Release Plan
See:
- [`APP_FINISH_PLAN.md`](APP_FINISH_PLAN.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)

## License
MIT. See [`LICENSE`](LICENSE).

