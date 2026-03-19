import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


class IntegrationRegistryService:
    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.packs_dir = self.data_dir / "integration-packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    def list_integrations(self) -> List[Dict]:
        integrations: Dict[str, Dict] = {}

        for item in self._builtin_integrations():
            integrations[item["key"]] = item

        for pack in self._load_external_packs():
            pack_name = pack.get("name", "External Pack")
            for item in pack.get("integrations", []):
                if not isinstance(item, dict):
                    continue

                key = str(item.get("key", "")).strip().lower()
                name = str(item.get("name", "")).strip()
                handler = str(item.get("handler", "")).strip().lower()
                if not key or not name:
                    continue

                required = item.get("required_fields", [])
                if not isinstance(required, list):
                    required = []

                integrations[key] = {
                    "key": key,
                    "name": name,
                    "description": str(item.get("description", "")).strip(),
                    "required_fields": [str(field) for field in required if str(field).strip()],
                    "handler": handler or key,
                    "source": pack_name,
                    "category": str(item.get("category", "External")).strip() or "External",
                    "auth_type": str(item.get("auth_type", "custom")).strip() or "custom",
                }

        return sorted(integrations.values(), key=lambda item: item["name"].lower())

    def get_integration(self, key: str) -> Dict | None:
        target = key.strip().lower()
        if not target:
            return None

        for item in self.list_integrations():
            if item.get("key", "").strip().lower() == target:
                return item
        return None

    def install_pack_from_file(self, source_path: str) -> Tuple[bool, str]:
        candidate = Path(source_path).expanduser()
        if not candidate.exists() or not candidate.is_file():
            return False, "Integration pack file was not found."

        try:
            with open(candidate, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as error:
            return False, f"Failed to read pack JSON: {error}"

        if not isinstance(data, dict):
            return False, "Pack JSON must be an object."

        integrations = data.get("integrations", [])
        if not isinstance(integrations, list) or not integrations:
            return False, "Pack JSON must include a non-empty 'integrations' list."

        for item in integrations:
            if not isinstance(item, dict):
                return False, "Each integration entry must be an object."
            key = str(item.get("key", "")).strip().lower()
            name = str(item.get("name", "")).strip()
            if not key or not name:
                return False, "Each integration must include non-empty 'key' and 'name'."

        destination = self.packs_dir / candidate.name
        try:
            shutil.copy2(candidate, destination)
        except Exception as error:
            return False, f"Failed to copy pack file: {error}"

        return True, f"Installed integration pack: {candidate.name}"

    def _load_external_packs(self) -> List[Dict]:
        packs: List[Dict] = []
        for file_path in sorted(self.packs_dir.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    packs.append(data)
            except Exception:
                continue
        return packs

    def _builtin_integrations(self) -> List[Dict]:
        return [
            {
                "key": "standard",
                "name": "Standard Action",
                "description": "Completes an action step using the current context.",
                "required_fields": [],
                "handler": "standard",
                "source": "Built-in",
                "category": "Core",
                "auth_type": "none",
            },
            {
                "key": "handoff",
                "name": "Bot Handoff",
                "description": "Passes output through one or more bots.",
                "required_fields": ["bot_chain"],
                "handler": "handoff",
                "source": "Built-in",
                "category": "AI",
                "auth_type": "none",
            },
            {
                "key": "http_post",
                "name": "HTTP POST",
                "description": "Sends workflow output as JSON to an HTTP endpoint.",
                "required_fields": ["url"],
                "handler": "http_post",
                "source": "Built-in",
                "category": "Core",
                "auth_type": "none",
            },
            {
                "key": "http_request",
                "name": "HTTP Request",
                "description": "Performs an HTTP request with method, headers, and JSON body.",
                "required_fields": ["url"],
                "handler": "http_request",
                "source": "Built-in",
                "category": "Core",
                "auth_type": "optional_api_key",
            },
            {
                "key": "slack_webhook",
                "name": "Slack Webhook",
                "description": "Sends a message to a Slack incoming webhook.",
                "required_fields": ["webhook_url"],
                "handler": "slack_webhook",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "webhook",
            },
            {
                "key": "discord_webhook",
                "name": "Discord Webhook",
                "description": "Posts a message to a Discord webhook.",
                "required_fields": ["webhook_url"],
                "handler": "discord_webhook",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "webhook",
            },
            {
                "key": "teams_webhook",
                "name": "Microsoft Teams Webhook",
                "description": "Posts a message to a Teams incoming webhook.",
                "required_fields": ["webhook_url"],
                "handler": "teams_webhook",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "webhook",
            },
            {
                "key": "telegram_bot",
                "name": "Telegram Bot",
                "description": "Sends a Telegram message with bot token + chat id.",
                "required_fields": ["api_key", "chat_id"],
                "handler": "telegram_bot",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "bot_token",
            },
            {
                "key": "gmail_send",
                "name": "Gmail Send",
                "description": "Sends email through Gmail API using OAuth bearer token.",
                "required_fields": ["api_key", "to", "subject"],
                "handler": "gmail_send",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "oauth_bearer",
            },
            {
                "key": "openweather_current",
                "name": "OpenWeather Current",
                "description": "Fetches current weather for a city using OpenWeather API.",
                "required_fields": ["api_key", "location"],
                "handler": "openweather_current",
                "source": "Built-in",
                "category": "Data",
                "auth_type": "api_key",
            },
            {
                "key": "google_apps_script",
                "name": "Google Apps Script",
                "description": "Calls a deployed Google Apps Script webhook endpoint.",
                "required_fields": ["script_url"],
                "handler": "google_apps_script",
                "source": "Built-in",
                "category": "Google",
                "auth_type": "webhook",
            },
            {
                "key": "google_sheets",
                "name": "Google Sheets",
                "description": "Writes values to Google Sheets via REST API.",
                "required_fields": ["api_key", "spreadsheet_id", "range"],
                "handler": "google_sheets",
                "source": "Built-in",
                "category": "Google",
                "auth_type": "oauth_bearer",
            },
            {
                "key": "google_calendar_api",
                "name": "Google Calendar API",
                "description": "Creates, updates, or lists Google Calendar events.",
                "required_fields": ["api_key", "url"],
                "handler": "google_calendar_api",
                "source": "Built-in",
                "category": "Google",
                "auth_type": "oauth_bearer",
            },
            {
                "key": "outlook_graph",
                "name": "Outlook Graph API",
                "description": "Calls Microsoft Graph for Outlook mail/calendar actions.",
                "required_fields": ["api_key", "url"],
                "handler": "outlook_graph",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "oauth_bearer",
            },
            {
                "key": "notion_api",
                "name": "Notion API",
                "description": "Sends requests to Notion API using bearer token.",
                "required_fields": ["api_key", "url"],
                "handler": "notion_api",
                "source": "Built-in",
                "category": "Productivity",
                "auth_type": "oauth_bearer",
            },
            {
                "key": "airtable_api",
                "name": "Airtable API",
                "description": "Creates or updates Airtable records via REST API.",
                "required_fields": ["api_key", "url"],
                "handler": "airtable_api",
                "source": "Built-in",
                "category": "Productivity",
                "auth_type": "api_key",
            },
            {
                "key": "hubspot_api",
                "name": "HubSpot API",
                "description": "Calls HubSpot CRM APIs with private app token.",
                "required_fields": ["api_key", "url"],
                "handler": "hubspot_api",
                "source": "Built-in",
                "category": "CRM",
                "auth_type": "bearer",
            },
            {
                "key": "stripe_api",
                "name": "Stripe API",
                "description": "Calls Stripe APIs using a secret key.",
                "required_fields": ["api_key", "url"],
                "handler": "stripe_api",
                "source": "Built-in",
                "category": "Payments",
                "auth_type": "bearer",
            },
            {
                "key": "twilio_sms",
                "name": "Twilio SMS",
                "description": "Sends SMS through Twilio using account SID/auth token.",
                "required_fields": ["account_sid", "auth_token", "from", "to"],
                "handler": "twilio_sms",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "basic",
            },
            {
                "key": "github_rest",
                "name": "GitHub REST",
                "description": "Calls GitHub REST API with bearer token.",
                "required_fields": ["api_key", "url"],
                "handler": "github_rest",
                "source": "Built-in",
                "category": "Developer",
                "auth_type": "bearer",
            },
            {
                "key": "linear_api",
                "name": "Linear API",
                "description": "Runs Linear GraphQL requests with API key.",
                "required_fields": ["api_key"],
                "handler": "linear_api",
                "source": "Built-in",
                "category": "Developer",
                "auth_type": "bearer",
            },
            {
                "key": "jira_api",
                "name": "Jira API",
                "description": "Calls Jira Cloud REST API with bearer/API token.",
                "required_fields": ["api_key", "url"],
                "handler": "jira_api",
                "source": "Built-in",
                "category": "Project",
                "auth_type": "bearer",
            },
            {
                "key": "asana_api",
                "name": "Asana API",
                "description": "Calls Asana REST API with personal access token.",
                "required_fields": ["api_key", "url"],
                "handler": "asana_api",
                "source": "Built-in",
                "category": "Project",
                "auth_type": "bearer",
            },
            {
                "key": "clickup_api",
                "name": "ClickUp API",
                "description": "Calls ClickUp REST API using API token.",
                "required_fields": ["api_key", "url"],
                "handler": "clickup_api",
                "source": "Built-in",
                "category": "Project",
                "auth_type": "bearer",
            },
            {
                "key": "trello_api",
                "name": "Trello API",
                "description": "Calls Trello REST API using API token/key headers.",
                "required_fields": ["api_key", "url"],
                "handler": "trello_api",
                "source": "Built-in",
                "category": "Project",
                "auth_type": "bearer",
            },
            {
                "key": "monday_api",
                "name": "Monday API",
                "description": "Runs Monday.com GraphQL API requests.",
                "required_fields": ["api_key", "url"],
                "handler": "monday_api",
                "source": "Built-in",
                "category": "Project",
                "auth_type": "bearer",
            },
            {
                "key": "zendesk_api",
                "name": "Zendesk API",
                "description": "Calls Zendesk REST API with bearer token.",
                "required_fields": ["api_key", "url"],
                "handler": "zendesk_api",
                "source": "Built-in",
                "category": "Support",
                "auth_type": "bearer",
            },
            {
                "key": "pipedrive_api",
                "name": "Pipedrive API",
                "description": "Calls Pipedrive REST API endpoints.",
                "required_fields": ["api_key", "url"],
                "handler": "pipedrive_api",
                "source": "Built-in",
                "category": "CRM",
                "auth_type": "api_key",
            },
            {
                "key": "salesforce_api",
                "name": "Salesforce API",
                "description": "Calls Salesforce REST API with OAuth token.",
                "required_fields": ["api_key", "url"],
                "handler": "salesforce_api",
                "source": "Built-in",
                "category": "CRM",
                "auth_type": "bearer",
            },
            {
                "key": "gitlab_api",
                "name": "GitLab API",
                "description": "Calls GitLab REST API with private token/bearer.",
                "required_fields": ["api_key", "url"],
                "handler": "gitlab_api",
                "source": "Built-in",
                "category": "Developer",
                "auth_type": "bearer",
            },
            {
                "key": "resend_email",
                "name": "Resend Email",
                "description": "Sends email through Resend API.",
                "required_fields": ["api_key", "from", "to", "subject"],
                "handler": "resend_email",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "bearer",
            },
            {
                "key": "mailgun_email",
                "name": "Mailgun Email",
                "description": "Sends email via Mailgun API.",
                "required_fields": ["api_key", "domain", "from", "to", "subject"],
                "handler": "mailgun_email",
                "source": "Built-in",
                "category": "Communication",
                "auth_type": "basic",
            },
            {
                "key": "postgres_sql",
                "name": "Postgres SQL",
                "description": "Executes SQL using local psql client.",
                "required_fields": ["connection_url", "sql"],
                "handler": "postgres_sql",
                "source": "Built-in",
                "category": "Database",
                "auth_type": "connection_url",
            },
            {
                "key": "mysql_sql",
                "name": "MySQL SQL",
                "description": "Executes SQL using local mysql client.",
                "required_fields": ["connection_url", "sql"],
                "handler": "mysql_sql",
                "source": "Built-in",
                "category": "Database",
                "auth_type": "connection_url",
            },
            {
                "key": "sqlite_sql",
                "name": "SQLite SQL",
                "description": "Executes SQL against a local SQLite file.",
                "required_fields": ["path", "sql"],
                "handler": "sqlite_sql",
                "source": "Built-in",
                "category": "Database",
                "auth_type": "file_path",
            },
            {
                "key": "redis_command",
                "name": "Redis Command",
                "description": "Executes redis-cli command against a Redis server.",
                "required_fields": ["command"],
                "handler": "redis_command",
                "source": "Built-in",
                "category": "Database",
                "auth_type": "optional_url",
            },
            {
                "key": "s3_cli",
                "name": "S3 CLI",
                "description": "Performs AWS S3 operation via aws CLI command.",
                "required_fields": ["command"],
                "handler": "s3_cli",
                "source": "Built-in",
                "category": "Storage",
                "auth_type": "aws_env",
            },
            {
                "key": "file_append",
                "name": "File Append",
                "description": "Appends workflow output to a local file.",
                "required_fields": ["path"],
                "handler": "file_append",
                "source": "Built-in",
                "category": "Core",
                "auth_type": "none",
            },
            {
                "key": "shell_command",
                "name": "Shell Command",
                "description": "Runs a local shell command on this machine.",
                "required_fields": ["command"],
                "handler": "shell_command",
                "source": "Built-in",
                "category": "Core",
                "auth_type": "none",
            },
            {
                "key": "approval_gate",
                "name": "Approval Gate",
                "description": "Pauses execution until a human approves and resumes the run.",
                "required_fields": [],
                "handler": "approval_gate",
                "source": "Built-in",
                "category": "Trust",
                "auth_type": "none",
            },
        ]
