import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
import sys


def load_storage_module():
    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "docker" / "api"
    sys.path.insert(0, str(api_root))
    storage_path = repo_root / "docker" / "api" / "app" / "storage.py"
    spec = importlib.util.spec_from_file_location("docker_api_storage", storage_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load docker/api/app/storage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class DockerStoreSchemaTests(unittest.TestCase):
    def setUp(self):
        self.module = load_storage_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self):
        os.environ.pop("SECRET_ENCRYPTION_KEY", None)
        os.environ.pop("SECRET_PROVIDER_MODE", None)
        os.environ.pop("SECRET_PROVIDER_FILE", None)
        os.environ.pop("SECRET_PROVIDER_ENV_PREFIX", None)
        os.environ.pop("SECRET_PROVIDER_HTTP_URL", None)
        os.environ.pop("SECRET_PROVIDER_HTTP_AUTH_TOKEN", None)
        os.environ.pop("SECRET_PROVIDER_HTTP_TIMEOUT_SEC", None)
        os.environ.pop("SECRET_PROVIDER_HTTP_ALLOW_INSECURE", None)
        os.environ.pop("SECRET_PROVIDER_VAULT_URL", None)
        os.environ.pop("SECRET_PROVIDER_VAULT_AUTH_TOKEN", None)
        os.environ.pop("SECRET_PROVIDER_VAULT_TIMEOUT_SEC", None)
        os.environ.pop("SECRET_PROVIDER_VAULT_ALLOW_INSECURE", None)
        os.environ.pop("RELATIONAL_MIGRATION_REQUIRED", None)
        os.environ.pop("RELATIONAL_MIGRATION_ENFORCE_COMPATIBILITY", None)
        os.environ.pop("RELATIONAL_MIGRATION_CONNECT_TIMEOUT_SEC", None)
        os.environ.pop("RELATIONAL_MIGRATION_RETRY_ATTEMPTS", None)
        os.environ.pop("RELATIONAL_MIGRATION_RETRY_DELAY_SEC", None)
        os.environ.pop("RELATIONAL_ALLOW_UNKNOWN_REVISIONS", None)
        os.environ.pop("RELATIONAL_MIN_SCHEMA_VERSION", None)
        os.environ.pop("RELATIONAL_MAX_SCHEMA_VERSION", None)
        os.environ.pop("SIXPX_STORAGE_BACKEND", None)
        os.environ.pop("SIXPX_STORAGE_BACKEND_REQUIRED", None)
        os.environ.pop("OPENAI_MANAGED_KEY", None)
        os.environ.pop("INTEGRATION_MANAGED_KEY", None)
        os.environ.pop("ANTHROPIC_MANAGED_KEY", None)
        self.temp_dir.cleanup()

    def _write_json(self, name: str, payload):
        (self.data_dir / name).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _read_json(self, name: str):
        return json.loads((self.data_dir / name).read_text(encoding="utf-8"))

    def test_bootstrap_creates_schema_meta_file(self):
        store = self.module.JsonStore(data_dir=str(self.data_dir))
        self.assertEqual(self.module.STORE_SCHEMA_VERSION, store.schema_version)

        meta = self._read_json("schema_meta.json")
        self.assertEqual(self.module.STORE_SCHEMA_VERSION, int(meta.get("schema_version", 0)))
        self.assertTrue(str(meta.get("initialized_at", "")).strip())
        self.assertTrue(str(meta.get("updated_at", "")).strip())

    def test_legacy_payloads_are_migrated_and_normalized(self):
        self._write_json(
            "workflows.json",
            [{"id": "w1", "name": "Legacy Flow", "graph": "broken"}],
        )
        self._write_json(
            "runs.json",
            [
                {
                    "id": "r1",
                    "workflow_id": "w1",
                    "status": "success",
                    "timeline": [{"node_id": "n1", "status": "success"}],
                }
            ],
        )
        self._write_json(
            "integrations.json",
            [{"id": "i1", "key": "HTTP_REQUEST", "name": "Legacy Integration"}],
        )
        self._write_json(
            "bots.json",
            [{"id": "b1", "name": "Legacy Bot", "provider": "local", "temperature": "0.6"}],
        )
        self._write_json("settings.json", "not-a-dict")

        store = self.module.JsonStore(data_dir=str(self.data_dir))
        self.assertEqual(self.module.STORE_SCHEMA_VERSION, store.schema_version)

        workflows = store.load_workflows()
        self.assertEqual(1, len(workflows))
        graph = workflows[0]["graph"]
        self.assertEqual(3, int(graph.get("schema_version", 0)))
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("links", graph)
        self.assertEqual("draft", workflows[0]["status"])

        runs = store.load_runs()
        self.assertEqual(1, len(runs))
        run = runs[0]
        self.assertEqual(1, run["attempt"])
        self.assertEqual(0, run["retry_count"])
        self.assertIn("execution_retry_max", run)
        self.assertIn("execution_backoff_ms", run)
        self.assertIn("execution_timeout_sec", run)
        self.assertIsInstance(run["node_results"], list)
        self.assertEqual(run["node_results"], run.get("timeline"))

        integrations = store.load_integrations()
        self.assertEqual(1, len(integrations))
        self.assertEqual("http_request", integrations[0]["key"])

        bots = store.load_bots()
        self.assertEqual(1, len(bots))
        self.assertAlmostEqual(0.6, float(bots[0]["temperature"]))
        self.assertIn("last_test_output", bots[0])

        settings = self._read_json("settings.json")
        self.assertEqual({}, settings)

        migration_history = self._read_json("schema_migrations.json")
        self.assertTrue(migration_history)
        migration_pairs = {
            (int(item.get("from_version", 0)), int(item.get("to_version", 0)))
            for item in migration_history
            if isinstance(item, dict)
        }
        self.assertIn((1, 2), migration_pairs)
        self.assertIn((2, 3), migration_pairs)

        snapshots_dir = self.data_dir / "migration_snapshots"
        self.assertTrue(snapshots_dir.exists())
        self.assertGreaterEqual(len(list(snapshots_dir.glob("*.json"))), 1)

    def test_backup_export_and_restore_replace(self):
        store = self.module.JsonStore(data_dir=str(self.data_dir))
        store.save_workflows(
            [
                {
                    "id": "wf_a",
                    "name": "Backup Workflow",
                    "description": "",
                    "graph": {},
                    "status": "draft",
                    "tags": [],
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:00:00+00:00",
                }
            ]
        )
        store.save_runs(
            [
                {
                    "id": "run_a",
                    "workflow_id": "wf_a",
                    "workflow_name": "Backup Workflow",
                    "status": "success",
                    "trigger": "manual",
                    "log": "ok",
                    "summary": "done",
                    "node_results": [],
                    "finished_at": "2026-03-24T00:01:00+00:00",
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:01:00+00:00",
                }
            ]
        )
        backup_path = self.data_dir / "full-backup.json"
        export_path, counts = store.export_backup(backup_path)
        self.assertEqual(backup_path, export_path)
        self.assertEqual(1, counts.get("workflows"))
        self.assertEqual(1, counts.get("runs"))

        store.save_workflows([])
        store.save_runs([])
        restored = store.restore_backup(str(backup_path), merge=False)
        self.assertEqual(1, restored.get("workflows"))
        self.assertEqual(1, restored.get("runs"))
        self.assertEqual(1, len(store.load_workflows()))
        self.assertEqual(1, len(store.load_runs()))

    def test_backup_restore_merge_upserts_by_id(self):
        store = self.module.JsonStore(data_dir=str(self.data_dir))
        store.save_workflows(
            [
                {
                    "id": "wf_keep",
                    "name": "Keep Me",
                    "description": "",
                    "graph": {},
                    "status": "draft",
                    "tags": [],
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:00:00+00:00",
                }
            ]
        )
        backup_payload = {
            "format": "6x-protocol.backup.v1",
            "exported_at": "2026-03-24T01:00:00+00:00",
            "data": {
                "workflows": [
                    {
                        "id": "wf_keep",
                        "name": "Keep Me Updated",
                        "description": "",
                        "graph": {},
                        "status": "active",
                        "tags": [],
                        "created_at": "2026-03-24T00:00:00+00:00",
                        "updated_at": "2026-03-24T01:00:00+00:00",
                    },
                    {
                        "id": "wf_new",
                        "name": "New Workflow",
                        "description": "",
                        "graph": {},
                        "status": "draft",
                        "tags": [],
                        "created_at": "2026-03-24T01:00:00+00:00",
                        "updated_at": "2026-03-24T01:00:00+00:00",
                    },
                ],
                "runs": [],
                "settings": {"theme": "dark"},
                "integrations": [],
                "bots": [],
            },
        }
        backup_path = self.data_dir / "merge-backup.json"
        self._write_json("merge-backup.json", backup_payload)
        restored = store.restore_backup(str(backup_path), merge=True)
        self.assertEqual(2, restored.get("workflows"))

        workflows = {item["id"]: item for item in store.load_workflows()}
        self.assertIn("wf_keep", workflows)
        self.assertIn("wf_new", workflows)
        self.assertEqual("Keep Me Updated", workflows["wf_keep"]["name"])
        self.assertEqual("active", workflows["wf_keep"]["status"])

    def test_secret_encryption_for_settings_and_integrations(self):
        try:
            import cryptography  # noqa: F401
        except Exception:
            self.skipTest("cryptography not available in local test environment")

        os.environ["SECRET_ENCRYPTION_KEY"] = "test-hardening-key"
        store = self.module.JsonStore(data_dir=str(self.data_dir))

        store.save_settings(
            {
                "openai_api_key": "sk-secret-openai",
                "anthropic_api_key": "sk-ant-secret",
                "local_ai_api_key": "local-token",
                "theme": "dark",
            }
        )
        raw_settings = self._read_json("settings.json")
        self.assertTrue(str(raw_settings.get("openai_api_key", "")).startswith("enc:v1:"))
        self.assertNotEqual("sk-secret-openai", raw_settings.get("openai_api_key"))

        loaded_settings = store.load_settings({})
        self.assertEqual("sk-secret-openai", loaded_settings.get("openai_api_key"))
        self.assertEqual("sk-ant-secret", loaded_settings.get("anthropic_api_key"))
        self.assertEqual("local-token", loaded_settings.get("local_ai_api_key"))

        store.save_integrations(
            [
                {
                    "id": "i1",
                    "key": "http_request",
                    "name": "Secure Profile",
                    "description": "",
                    "config": {
                        "api_key": "integration-secret",
                        "url": "https://example.com",
                        "headers": {"Authorization": "Bearer abc"},
                    },
                    "enabled": True,
                    "tags": [],
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:00:00+00:00",
                }
            ]
        )
        raw_integrations = self._read_json("integrations.json")
        raw_config = raw_integrations[0]["config"]
        self.assertTrue(str(raw_config.get("api_key", "")).startswith("enc:v1:"))
        self.assertTrue(
            str(raw_config.get("headers", {}).get("Authorization", "")).startswith("enc:v1:")
        )
        loaded_integrations = store.load_integrations()
        self.assertEqual("integration-secret", loaded_integrations[0]["config"]["api_key"])
        self.assertEqual("Bearer abc", loaded_integrations[0]["config"]["headers"]["Authorization"])

    def test_secret_rotation_reencrypts_payloads(self):
        try:
            import cryptography  # noqa: F401
        except Exception:
            self.skipTest("cryptography not available in local test environment")

        os.environ["SECRET_ENCRYPTION_KEY"] = "old-hardening-key"
        store = self.module.JsonStore(data_dir=str(self.data_dir))
        store.save_settings({"openai_api_key": "old-secret"})
        raw_before = self._read_json("settings.json")
        encrypted_before = str(raw_before.get("openai_api_key", ""))
        self.assertTrue(encrypted_before.startswith("enc:v1:"))

        rotated = store.rotate_secret_encryption("new-hardening-key")
        self.assertEqual(1, int(rotated.get("settings", 0)))

        raw_after = self._read_json("settings.json")
        encrypted_after = str(raw_after.get("openai_api_key", ""))
        self.assertTrue(encrypted_after.startswith("enc:v1:"))
        self.assertNotEqual(encrypted_before, encrypted_after)
        self.assertEqual("old-secret", store.load_settings({}).get("openai_api_key"))

    def test_store_rejects_future_schema_version(self):
        self._write_json(
            "schema_meta.json",
            {
                "schema_version": int(self.module.STORE_SCHEMA_VERSION) + 1,
                "initialized_at": "2026-03-24T00:00:00+00:00",
                "updated_at": "2026-03-24T00:00:00+00:00",
            },
        )
        with self.assertRaises(RuntimeError):
            self.module.JsonStore(data_dir=str(self.data_dir))

    def test_restore_rejects_future_schema_backup(self):
        store = self.module.JsonStore(data_dir=str(self.data_dir))
        self._write_json(
            "future-backup.json",
            {
                "format": "6x-protocol.backup.v1",
                "schema_version": int(self.module.STORE_SCHEMA_VERSION) + 2,
                "data": {
                    "workflows": [],
                    "runs": [],
                    "settings": {},
                    "integrations": [],
                    "bots": [],
                },
            },
        )
        with self.assertRaises(ValueError):
            store.restore_backup(self.data_dir / "future-backup.json", merge=False)

    def test_managed_secret_env_refs_resolve_settings_and_integrations(self):
        os.environ["SECRET_PROVIDER_MODE"] = "env"
        os.environ["OPENAI_MANAGED_KEY"] = "openai-managed-secret"
        os.environ["INTEGRATION_MANAGED_KEY"] = "integration-managed-secret"
        store = self.module.JsonStore(data_dir=str(self.data_dir))

        store.save_settings(
            {
                "openai_api_key_ref": "env:OPENAI_MANAGED_KEY",
                "openai_api_key": "",
            }
        )
        raw_settings = self._read_json("settings.json")
        self.assertEqual("env:OPENAI_MANAGED_KEY", raw_settings.get("openai_api_key_ref"))
        loaded_settings = store.load_settings({})
        self.assertEqual("openai-managed-secret", loaded_settings.get("openai_api_key"))

        store.save_integrations(
            [
                {
                    "id": "i_env_ref",
                    "key": "http_request",
                    "name": "Env Ref Integration",
                    "description": "",
                    "config": {
                        "api_key": "secret://env/INTEGRATION_MANAGED_KEY",
                        "url": "https://example.com",
                    },
                    "enabled": True,
                    "tags": [],
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:00:00+00:00",
                }
            ]
        )
        loaded_integrations = store.load_integrations()
        self.assertEqual(
            "integration-managed-secret",
            loaded_integrations[0]["config"].get("api_key"),
        )

    def test_managed_secret_file_ref_resolves_settings(self):
        secret_file = self.data_dir / "managed-secrets.json"
        self._write_json(
            "managed-secrets.json",
            {
                "providers": {
                    "anthropic": {
                        "key": "anthropic-managed-secret",
                    }
                }
            },
        )
        os.environ["SECRET_PROVIDER_MODE"] = "file"
        os.environ["SECRET_PROVIDER_FILE"] = str(secret_file)
        store = self.module.JsonStore(data_dir=str(self.data_dir))

        store.save_settings(
            {
                "anthropic_api_key_ref": "file:providers.anthropic.key",
                "anthropic_api_key": "",
            }
        )
        loaded_settings = store.load_settings({})
        self.assertEqual(
            "anthropic-managed-secret",
            loaded_settings.get("anthropic_api_key"),
        )


if __name__ == "__main__":
    unittest.main()
