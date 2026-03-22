import ast
import unittest
from pathlib import Path


def load_integration_catalog() -> list[dict]:
    repo_root = Path(__file__).resolve().parents[1]
    main_path = repo_root / "docker" / "api" / "app" / "main.py"
    source = main_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(main_path))

    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "INTEGRATION_CATALOG":
                value = ast.literal_eval(node.value)
                if isinstance(value, list):
                    return value
                raise AssertionError("INTEGRATION_CATALOG is not a list literal.")
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "INTEGRATION_CATALOG":
                value = ast.literal_eval(node.value)
                if isinstance(value, list):
                    return value
                raise AssertionError("INTEGRATION_CATALOG is not a list literal.")
    raise AssertionError("INTEGRATION_CATALOG was not found in docker/api/app/main.py")


class DockerIntegrationCatalogTests(unittest.TestCase):
    def test_catalog_includes_runtime_supported_integrations(self):
        catalog = load_integration_catalog()
        keys = {
            str(item.get("key", "")).strip().lower()
            for item in catalog
            if isinstance(item, dict)
        }
        expected = {
            "standard",
            "handoff",
            "http_request",
            "http_post",
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
            "telegram_bot",
            "gmail_send",
            "openweather_current",
            "google_apps_script",
            "google_sheets",
            "google_calendar_api",
            "outlook_graph",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "linear_api",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "resend_email",
            "mailgun_email",
            "postgres_sql",
            "mysql_sql",
            "sqlite_sql",
            "redis_command",
            "s3_cli",
            "file_append",
            "shell_command",
            "approval_gate",
        }
        self.assertTrue(expected.issubset(keys), f"Missing catalog keys: {sorted(expected - keys)}")

    def test_catalog_keys_are_unique_and_well_formed(self):
        catalog = load_integration_catalog()
        seen: set[str] = set()
        for item in catalog:
            self.assertIsInstance(item, dict)
            key = str(item.get("key", "")).strip().lower()
            name = str(item.get("name", "")).strip()
            category = str(item.get("category", "")).strip().lower()
            required_fields = item.get("required_fields", [])

            self.assertTrue(key, "Catalog integration key must be non-empty.")
            self.assertTrue(name, f"Catalog integration '{key}' must have a display name.")
            self.assertTrue(category, f"Catalog integration '{key}' must have a category.")
            self.assertIsInstance(
                required_fields,
                list,
                f"Catalog integration '{key}' required_fields must be a list.",
            )
            self.assertNotIn(key, seen, f"Duplicate integration key in catalog: {key}")
            seen.add(key)


if __name__ == "__main__":
    unittest.main()
