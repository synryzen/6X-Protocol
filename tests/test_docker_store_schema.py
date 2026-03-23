import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_storage_module():
    repo_root = Path(__file__).resolve().parents[1]
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
        self.assertEqual({}, workflows[0]["graph"])
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
        latest = migration_history[-1]
        self.assertEqual(1, int(latest.get("from_version", 0)))
        self.assertEqual(2, int(latest.get("to_version", 0)))


if __name__ == "__main__":
    unittest.main()
