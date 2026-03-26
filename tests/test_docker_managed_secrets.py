import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


def load_managed_secrets_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "docker" / "api" / "app" / "managed_secrets.py"
    spec = importlib.util.spec_from_file_location("docker_api_managed_secrets", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load docker/api/app/managed_secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class ManagedSecretsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_managed_secrets_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self):
        os.environ.pop("OPENAI_TEST_KEY", None)
        self.temp_dir.cleanup()

    def test_parse_secret_reference_supports_env_and_file(self):
        self.assertEqual(("env", "OPENAI_TEST_KEY"), self.module.parse_secret_reference("env:OPENAI_TEST_KEY"))
        self.assertEqual(("file", "providers.openai.key"), self.module.parse_secret_reference("file:providers.openai.key"))
        self.assertEqual(
            ("env", "OPENAI_TEST_KEY"),
            self.module.parse_secret_reference("secret://env/OPENAI_TEST_KEY"),
        )
        self.assertEqual(
            ("file", "providers.openai.key"),
            self.module.parse_secret_reference("secret://file/providers.openai.key"),
        )

    def test_env_mode_resolves_settings_ref(self):
        os.environ["OPENAI_TEST_KEY"] = "openai-secret-value"
        resolver = self.module.ManagedSecretResolver(mode="env")
        settings = resolver.resolve_settings(
            {
                "openai_api_key_ref": "env:OPENAI_TEST_KEY",
                "openai_api_key": "",
            }
        )
        self.assertEqual("openai-secret-value", settings.get("openai_api_key"))

    def test_file_mode_resolves_integration_ref(self):
        file_path = self.data_dir / "managed-secrets.json"
        file_path.write_text(
            json.dumps({"providers": {"openai": {"api_key": "file-openai-secret"}}}),
            encoding="utf-8",
        )
        resolver = self.module.ManagedSecretResolver(mode="file", file_path=str(file_path))
        profiles = resolver.resolve_integration_profiles(
            [
                {
                    "id": "p1",
                    "key": "http_request",
                    "name": "Profile",
                    "config": {"api_key": "secret://file/providers.openai.api_key"},
                }
            ]
        )
        self.assertEqual("file-openai-secret", profiles[0]["config"].get("api_key"))


if __name__ == "__main__":
    unittest.main()
