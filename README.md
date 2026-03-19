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

## Install Options (Linux)
### 1) Debian Package (Recommended)
Download the latest `.deb` from Releases and install:
```bash
sudo apt install ./6x-protocol-studio_<version>_amd64.deb
```
Launch from your desktop app menu as `6X-Protocol Studio` (no terminal required).

### 2) Portable Archive
Download `6x-protocol-studio_<version>_linux_portable.tar.gz` from Releases:
```bash
tar -xzf 6x-protocol-studio_<version>_linux_portable.tar.gz
cd 6x-protocol-studio
./6x-protocol-studio
```
Optional desktop launcher:
```bash
./install-desktop-entry.sh
```

### 3) AppImage
Download and run:
```bash
chmod +x 6x-protocol-studio_<version>_x86_64.AppImage
./6x-protocol-studio_<version>_x86_64.AppImage
```

### 4) Flatpak Bundle
Download and install:
```bash
flatpak install --user ./6x-protocol-studio_<version>_x86_64.flatpak
flatpak run com.sixxprotocol.studio
```

### 5) Source Run (Developer Mode)
Install dependencies and run from source:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
python3 main.py
```

## Data Location
User data is stored under:
`~/.local/share/6x-protocol-studio/`

## Product Site / GitHub Page
The project page content is in [`docs/index.html`](docs/index.html) and auto-deploys via GitHub Actions when Pages is enabled.

Planned Pages URL:
`https://synryzen.github.io/6X-Protocol/`

## Creator + Support
- Developer: `Matthew C Elliott`
- Website: `https://synryzen.com`
- GitHub: `https://github.com/synryzen/6X-Protocol`
- Support Email: `6X-Protocol@gmail.com`

## Marketing Funnel (Free -> Paid Apps)
- Use this repo and GitHub Releases as the free Linux download entry point.
- Keep a dedicated "Explore Matthew's Apps" section on the Pages site.
- Add one page per iOS/macOS app (best for search visibility and clearer call-to-action).
- Cross-link every app page back to this repo for trust and audience growth.

## Release Plan
See:
- [`APP_FINISH_PLAN.md`](APP_FINISH_PLAN.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)

## Package Build Commands
Build local installer artifacts:
```bash
./scripts/build_packages.sh
```

Output files are created in `dist/`:
- `.deb` installer
- portable `.tar.gz`
- `.AppImage`
- `.flatpak` bundle
- `SHA256SUMS.txt`

## License
MIT. See [`LICENSE`](LICENSE).
