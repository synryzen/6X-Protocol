import json
import tempfile
import unittest
from pathlib import Path

from src.services.integration_settings_store import IntegrationSettingsStore


class IntegrationSettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = IntegrationSettingsStore()
        self.store.data_dir = self.root
        self.store.file_path = self.root / "integration-settings.json"

    def test_save_and_load_profile(self):
        self.store.save_profile(
            " Slack_Webhook ",
            {
                "input_context": "  smoke context  ",
                "directives": " url: https://example.com  ",
            },
        )
        profile = self.store.get_profile("slack_webhook")
        self.assertEqual(
            {
                "input_context": "smoke context",
                "directives": "url: https://example.com",
            },
            profile,
        )

    def test_export_profiles_writes_json_bundle(self):
        self.store.save_profile("slack_webhook", {"input_context": "a", "directives": "b"})
        self.store.save_profile("discord_webhook", {"input_context": "c", "directives": "d"})

        export_path, count = self.store.export_profiles()
        self.assertEqual(2, count)
        self.assertTrue(export_path.exists())

        with open(export_path, "r", encoding="utf-8") as file:
            exported = json.load(file)
        self.assertIn("slack_webhook", exported)
        self.assertIn("discord_webhook", exported)

    def test_import_profiles_merge_updates_existing(self):
        self.store.save_profile("slack_webhook", {"input_context": "old", "directives": "old"})
        import_bundle = self.root / "profiles.json"
        with open(import_bundle, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "slack_webhook": {
                        "input_context": "new context",
                        "directives": "new directives",
                    },
                    "openweather": {
                        "input_context": "weather context",
                        "directives": "location: Austin,US",
                    },
                },
                file,
                indent=2,
            )

        imported_count, total_count = self.store.import_profiles(import_bundle, merge=True)
        self.assertEqual(2, imported_count)
        self.assertEqual(2, total_count)
        self.assertEqual("new context", self.store.get_profile("slack_webhook").get("input_context"))
        self.assertEqual(
            "weather context",
            self.store.get_profile("openweather").get("input_context"),
        )

    def test_import_profiles_replace_mode(self):
        self.store.save_profile("slack_webhook", {"input_context": "old", "directives": "old"})
        import_bundle = self.root / "profiles-replace.json"
        with open(import_bundle, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "openweather": {
                        "input_context": "weather context",
                        "directives": "location: Austin,US",
                    }
                },
                file,
                indent=2,
            )

        imported_count, total_count = self.store.import_profiles(import_bundle, merge=False)
        self.assertEqual(1, imported_count)
        self.assertEqual(1, total_count)
        self.assertEqual({}, self.store.get_profile("slack_webhook"))
        self.assertEqual(
            "weather context",
            self.store.get_profile("openweather").get("input_context"),
        )

    def test_import_profiles_raises_for_invalid_bundle_shape(self):
        import_bundle = self.root / "invalid.json"
        with open(import_bundle, "w", encoding="utf-8") as file:
            json.dump(["invalid"], file)

        with self.assertRaises(ValueError):
            self.store.import_profiles(import_bundle)

    def test_import_profiles_raises_for_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            self.store.import_profiles(self.root / "missing.json")


if __name__ == "__main__":
    unittest.main()
