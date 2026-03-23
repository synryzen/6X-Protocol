import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "api"))

from app.storage import JsonStore


def _profile(
    profile_id: str,
    *,
    key: str,
    name: str,
    description: str = "",
    config: dict | None = None,
) -> dict:
    return {
        "id": profile_id,
        "key": key,
        "name": name,
        "description": description,
        "enabled": True,
        "config": config or {},
        "tags": [],
        "last_test_status": "",
        "last_test_message": "",
        "last_tested_at": "",
        "created_at": "2026-03-01T00:00:00+00:00",
        "updated_at": "2026-03-01T00:00:00+00:00",
    }


class DockerIntegrationProfileBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(data_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_integrations_writes_bundle_with_metadata(self):
        self.store.save_integrations(
            [
                _profile("p1", key="slack_webhook", name="Slack Alerts"),
                _profile("p2", key="openweather_current", name="Weather"),
            ]
        )

        export_path, count = self.store.export_integrations()

        self.assertEqual(2, count)
        self.assertTrue(export_path.exists())
        raw = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual("6x-protocol.integration-profiles.v1", raw.get("format"))
        self.assertEqual(2, raw.get("profile_count"))
        self.assertEqual(2, len(raw.get("profiles", [])))

    def test_import_integrations_merge_updates_matching_id_and_keeps_others(self):
        self.store.save_integrations(
            [
                _profile("p1", key="slack_webhook", name="Slack Original"),
                _profile("p2", key="telegram_bot", name="Telegram Existing"),
            ]
        )
        bundle_path = Path(self.tmp.name) / "bundle.json"
        bundle_payload = {
            "format": "6x-protocol.integration-profiles.v1",
            "profiles": [
                _profile("p1", key="slack_webhook", name="Slack Updated"),
                _profile("p3", key="notion_api", name="Notion Added"),
            ],
        }
        bundle_path.write_text(json.dumps(bundle_payload, indent=2), encoding="utf-8")

        imported_count, total_count = self.store.import_integrations(bundle_path, merge=True)

        self.assertEqual(2, imported_count)
        self.assertEqual(3, total_count)
        profiles = self.store.load_integrations()
        by_id = {item["id"]: item for item in profiles}
        self.assertEqual("Slack Updated", by_id["p1"]["name"])
        self.assertEqual("Telegram Existing", by_id["p2"]["name"])
        self.assertEqual("Notion Added", by_id["p3"]["name"])

    def test_import_integrations_replace_overwrites_existing_profiles(self):
        self.store.save_integrations(
            [
                _profile("p1", key="slack_webhook", name="Slack Original"),
                _profile("p2", key="telegram_bot", name="Telegram Existing"),
            ]
        )
        bundle_path = Path(self.tmp.name) / "replace.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "profiles": [
                        _profile("p9", key="github_rest", name="GitHub"),
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        imported_count, total_count = self.store.import_integrations(bundle_path, merge=False)

        self.assertEqual(1, imported_count)
        self.assertEqual(1, total_count)
        profiles = self.store.load_integrations()
        self.assertEqual(["p9"], [item["id"] for item in profiles])

    def test_import_integrations_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.import_integrations(Path(self.tmp.name) / "missing.json", merge=True)

    def test_import_integrations_invalid_payload_raises(self):
        bundle_path = Path(self.tmp.name) / "invalid.json"
        bundle_path.write_text(json.dumps({"profiles": {}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.import_integrations(bundle_path, merge=True)


if __name__ == "__main__":
    unittest.main()
