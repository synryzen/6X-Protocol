import unittest

from src.services.settings_store import SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = SettingsStore()

    def test_invalid_provider_falls_back_to_default(self):
        sanitized = self.store._sanitize_settings({"preferred_provider": "invalid_provider"})
        self.assertEqual(sanitized["preferred_provider"], self.store.default_settings["preferred_provider"])

    def test_invalid_theme_falls_back_to_default(self):
        sanitized = self.store._sanitize_settings({"theme": "ultra_dark"})
        self.assertEqual(sanitized["theme"], self.store.default_settings["theme"])

    def test_local_backend_default_endpoint_is_applied(self):
        sanitized = self.store._sanitize_settings(
            {
                "local_ai_backend": "lm_studio",
                "local_ai_endpoint": "",
                "ollama_url": "",
            }
        )
        self.assertEqual(sanitized["local_ai_endpoint"], "http://localhost:1234/v1")

    def test_model_name_sanitization_trims_completion_suffix(self):
        sanitized = self.store._sanitize_settings(
            {"default_local_model": "nvidia/nemotron-3-nano/v1/chat/completions"}
        )
        self.assertEqual(sanitized["default_local_model"], "nvidia/nemotron-3-nano")


if __name__ == "__main__":
    unittest.main()

