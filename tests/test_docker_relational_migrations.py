import importlib.util
import os
import unittest
from pathlib import Path


def load_relational_migrations_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "docker" / "api" / "app" / "relational_migrations.py"
    spec = importlib.util.spec_from_file_location("docker_api_relational_migrations", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load docker/api/app/relational_migrations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class RelationalMigrationsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_relational_migrations_module()
        for key in (
            "RELATIONAL_MIGRATION_CONNECT_TIMEOUT_SEC",
            "RELATIONAL_MIGRATION_RETRY_ATTEMPTS",
            "RELATIONAL_MIGRATION_RETRY_DELAY_SEC",
            "RELATIONAL_MIGRATION_REQUIRED",
        ):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in (
            "RELATIONAL_MIGRATION_CONNECT_TIMEOUT_SEC",
            "RELATIONAL_MIGRATION_RETRY_ATTEMPTS",
            "RELATIONAL_MIGRATION_RETRY_DELAY_SEC",
            "RELATIONAL_MIGRATION_REQUIRED",
        ):
            os.environ.pop(key, None)

    def test_mask_database_url_hides_password(self):
        masked = self.module.mask_database_url("postgresql://user:secret@localhost:5432/protocol")
        self.assertIn("user:***@", masked)
        self.assertNotIn("secret@", masked)

    def test_disabled_when_database_url_missing(self):
        manager = self.module.RelationalMigrationManager(database_url="")
        result = manager.apply(app_version="0.5.0-preview")
        self.assertEqual("disabled", result.get("status"))
        self.assertFalse(bool(result.get("enabled")))
        self.assertEqual(len(self.module.RELATIONAL_REVISIONS), int(result.get("pending_count", 0)))

    def test_revision_scaffold_contains_first_revision(self):
        revisions = self.module.RELATIONAL_REVISIONS
        self.assertTrue(revisions)
        first = revisions[0]
        self.assertEqual("r0001_initial_runtime_scaffold", first.revision)
        combined_sql = "\n".join(first.statements).lower()
        self.assertIn("sixpx_schema_migrations", combined_sql)
        self.assertIn("sixpx_runtime_state", combined_sql)


if __name__ == "__main__":
    unittest.main()
