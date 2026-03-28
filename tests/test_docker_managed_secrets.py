import importlib.util
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import tempfile
import threading
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

    def test_parse_secret_reference_supports_env_file_http_and_vault(self):
        self.assertEqual(("env", "OPENAI_TEST_KEY"), self.module.parse_secret_reference("env:OPENAI_TEST_KEY"))
        self.assertEqual(("file", "providers.openai.key"), self.module.parse_secret_reference("file:providers.openai.key"))
        self.assertEqual(("http", "providers.openai.key"), self.module.parse_secret_reference("http:providers.openai.key"))
        self.assertEqual(("vault", "providers.openai.key"), self.module.parse_secret_reference("vault:providers.openai.key"))
        self.assertEqual(
            ("env", "OPENAI_TEST_KEY"),
            self.module.parse_secret_reference("secret://env/OPENAI_TEST_KEY"),
        )
        self.assertEqual(
            ("file", "providers.openai.key"),
            self.module.parse_secret_reference("secret://file/providers.openai.key"),
        )
        self.assertEqual(
            ("http", "providers.openai.key"),
            self.module.parse_secret_reference("secret://http/providers.openai.key"),
        )
        self.assertEqual(
            ("vault", "providers.openai.key"),
            self.module.parse_secret_reference("secret://vault/providers.openai.key"),
        )
        self.assertEqual(
            ("chain", "providers.openai.key"),
            self.module.parse_secret_reference("chain:providers.openai.key"),
        )
        self.assertEqual(
            ("chain", "providers.openai.key"),
            self.module.parse_secret_reference("secret://providers.openai.key"),
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

    def test_chain_mode_resolves_without_provider_prefix(self):
        os.environ["OPENAI_TEST_KEY"] = "env-chain-secret"
        resolver = self.module.ManagedSecretResolver(mode="chain")
        settings = resolver.resolve_settings(
            {
                "openai_api_key_ref": "secret://OPENAI_TEST_KEY",
                "openai_api_key": "",
            }
        )
        self.assertEqual("env-chain-secret", settings.get("openai_api_key"))

    def test_adapter_snapshot_includes_chain_order_and_errors(self):
        resolver = self.module.ManagedSecretResolver(
            mode="chain",
            file_path=str(self.data_dir / "missing-secrets.json"),
            chain_order="file,env,http,vault",
        )
        _ = resolver.resolve_reference("secret://file/providers.openai.api_key")
        snapshot = resolver.adapter_snapshot()
        self.assertEqual(["file", "env", "http", "vault"], snapshot.get("chain_order", []))
        adapters = snapshot.get("adapters", {})
        self.assertIn("file", adapters)
        self.assertIn("last_error", adapters.get("file", {}))

    def test_health_probe_and_recent_diagnostics_are_available(self):
        resolver = self.module.ManagedSecretResolver(
            mode="chain",
            file_path=str(self.data_dir / "missing-secrets.json"),
            chain_order="file,env",
        )
        health = resolver.health_probe(force_reload=True)
        self.assertIn("status", health)
        diagnostics = resolver.recent_diagnostics(limit=10)
        self.assertIsInstance(diagnostics, list)
        self.assertGreaterEqual(len(diagnostics), 1)

    def test_http_mode_resolves_integration_ref(self):
        expected_token = "token-123"
        payload = json.dumps({"providers": {"openai": {"api_key": "http-openai-secret"}}}).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path != "/secrets":
                    self.send_response(404)
                    self.end_headers()
                    return
                if self.headers.get("Authorization") != f"Bearer {expected_token}":
                    self.send_response(401)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _fmt, *_args):  # noqa: D401
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            resolver = self.module.ManagedSecretResolver(
                mode="http",
                http_url=f"http://127.0.0.1:{server.server_port}/secrets",
                http_auth_token=expected_token,
                http_allow_insecure=True,
            )
            profiles = resolver.resolve_integration_profiles(
                [
                    {
                        "id": "p1",
                        "key": "http_request",
                        "name": "Profile",
                        "config": {"api_key": "secret://http/providers.openai.api_key"},
                    }
                ]
            )
            self.assertEqual("http-openai-secret", profiles[0]["config"].get("api_key"))
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_vault_mode_resolves_integration_ref(self):
        expected_token = "vault-token-456"
        payload = json.dumps(
            {
                "data": {
                    "data": {
                        "providers": {
                            "openai": {
                                "api_key": "vault-openai-secret",
                            }
                        }
                    }
                }
            }
        ).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path != "/v1/kv/data/secrets":
                    self.send_response(404)
                    self.end_headers()
                    return
                if self.headers.get("X-Vault-Token") != expected_token:
                    self.send_response(403)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _fmt, *_args):  # noqa: D401
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            resolver = self.module.ManagedSecretResolver(
                mode="vault",
                vault_url=f"http://127.0.0.1:{server.server_port}/v1/kv/data/secrets",
                vault_auth_token=expected_token,
                vault_allow_insecure=True,
            )
            profiles = resolver.resolve_integration_profiles(
                [
                    {
                        "id": "p1",
                        "key": "http_request",
                        "name": "Profile",
                        "config": {"api_key": "secret://vault/providers.openai.api_key"},
                    }
                ]
            )
            self.assertEqual("vault-openai-secret", profiles[0]["config"].get("api_key"))
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
