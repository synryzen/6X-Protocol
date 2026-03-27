import importlib.util
import os
import unittest
from pathlib import Path
import sys


def load_storage_module():
    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "docker" / "api"
    sys.path.insert(0, str(api_root))
    module_path = repo_root / "docker" / "api" / "app" / "storage.py"
    spec = importlib.util.spec_from_file_location("docker_api_storage", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load docker/api/app/storage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class StorageBackendFactoryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_storage_module()
        self.keys = [
            "SIXPX_STORAGE_BACKEND",
            "SIXPX_STORAGE_BACKEND_REQUIRED",
            "DATABASE_URL",
        ]
        self.original_env = {key: os.environ.get(key) for key in self.keys}

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_factory_defaults_to_json_backend(self):
        os.environ.pop("SIXPX_STORAGE_BACKEND", None)
        store = self.module.create_store(data_dir="/tmp/6x-protocol-test-json")
        self.assertEqual("json", getattr(store, "storage_backend", ""))

    def test_factory_falls_back_to_json_when_postgres_unavailable(self):
        os.environ["SIXPX_STORAGE_BACKEND"] = "postgres"
        os.environ.pop("DATABASE_URL", None)
        os.environ["SIXPX_STORAGE_BACKEND_REQUIRED"] = "false"
        store = self.module.create_store(data_dir="/tmp/6x-protocol-test-fallback")
        self.assertEqual("json", getattr(store, "storage_backend", ""))

    def test_factory_raises_when_postgres_required_and_unavailable(self):
        os.environ["SIXPX_STORAGE_BACKEND"] = "postgres"
        os.environ.pop("DATABASE_URL", None)
        os.environ["SIXPX_STORAGE_BACKEND_REQUIRED"] = "true"
        with self.assertRaises(RuntimeError):
            self.module.create_store(data_dir="/tmp/6x-protocol-test-required")


if __name__ == "__main__":
    unittest.main()
