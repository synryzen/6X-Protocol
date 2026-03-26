import sys
import unittest
from pathlib import Path
import types
import importlib.util

# Keep this unit test lightweight outside the Docker API venv.
if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    def _field_stub(default=None, **_kwargs):
        if callable(default):
            return default()
        return default

    pydantic_stub.BaseModel = _BaseModel
    pydantic_stub.Field = _field_stub
    sys.modules["pydantic"] = pydantic_stub


def load_schemas_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "docker" / "api" / "app" / "schemas.py"
    spec = importlib.util.spec_from_file_location("docker_api_schemas_for_tests", module_path)
    if not spec or not spec.loader:
        raise RuntimeError("Failed to create module spec for docker/api/app/schemas.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_schemas = load_schemas_module()
DEFAULT_SETTINGS = _schemas.DEFAULT_SETTINGS
normalize_settings = _schemas.normalize_settings


class DockerSettingsSchemaTests(unittest.TestCase):
    def test_defaults_include_automation_and_minimap_fields(self):
        self.assertIn("auto_save_workflows", DEFAULT_SETTINGS)
        self.assertIn("daemon_autostart", DEFAULT_SETTINGS)
        self.assertIn("tray_enabled", DEFAULT_SETTINGS)
        self.assertIn("canvas_minimap_x", DEFAULT_SETTINGS)
        self.assertIn("canvas_minimap_y", DEFAULT_SETTINGS)
        self.assertIn("canvas_minimap_user_placed", DEFAULT_SETTINGS)
        self.assertIn("local_ai_api_key_ref", DEFAULT_SETTINGS)
        self.assertIn("openai_api_key_ref", DEFAULT_SETTINGS)
        self.assertIn("anthropic_api_key_ref", DEFAULT_SETTINGS)

    def test_normalize_settings_applies_backend_endpoint_defaults_and_model_sanitization(self):
        normalized = normalize_settings(
            {
                "local_ai_backend": "lm_studio",
                "local_ai_endpoint": "",
                "default_local_model": "nvidia/nemotron-3-nano/v1/chat/completions",
            }
        )
        self.assertEqual(normalized["local_ai_endpoint"], "http://localhost:1234/v1")
        self.assertEqual(normalized["default_local_model"], "nvidia/nemotron-3-nano")

    def test_normalize_settings_coerces_boolean_like_values(self):
        normalized = normalize_settings(
            {
                "local_ai_enabled": "false",
                "reduce_motion": "true",
                "auto_save_workflows": "0",
                "daemon_autostart": "1",
                "tray_enabled": "no",
                "canvas_minimap_user_placed": "yes",
            }
        )
        self.assertFalse(normalized["local_ai_enabled"])
        self.assertTrue(normalized["reduce_motion"])
        self.assertFalse(normalized["auto_save_workflows"])
        self.assertTrue(normalized["daemon_autostart"])
        self.assertFalse(normalized["tray_enabled"])
        self.assertTrue(normalized["canvas_minimap_user_placed"])

    def test_normalize_settings_rejects_unknown_theme_preset_and_clamps_minimap(self):
        normalized = normalize_settings(
            {
                "theme_preset": "midnight",
                "canvas_minimap_x": -25,
                "canvas_minimap_y": "-6",
            }
        )
        self.assertEqual(normalized["theme_preset"], "graphite")
        self.assertEqual(normalized["canvas_minimap_x"], 0)
        self.assertEqual(normalized["canvas_minimap_y"], 0)


if __name__ == "__main__":
    unittest.main()
