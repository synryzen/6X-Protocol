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
            "RELATIONAL_MIGRATION_ENFORCE_COMPATIBILITY",
            "RELATIONAL_ALLOW_UNKNOWN_REVISIONS",
            "RELATIONAL_MIN_SCHEMA_VERSION",
            "RELATIONAL_MAX_SCHEMA_VERSION",
        ):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in (
            "RELATIONAL_MIGRATION_CONNECT_TIMEOUT_SEC",
            "RELATIONAL_MIGRATION_RETRY_ATTEMPTS",
            "RELATIONAL_MIGRATION_RETRY_DELAY_SEC",
            "RELATIONAL_MIGRATION_REQUIRED",
            "RELATIONAL_MIGRATION_ENFORCE_COMPATIBILITY",
            "RELATIONAL_ALLOW_UNKNOWN_REVISIONS",
            "RELATIONAL_MIN_SCHEMA_VERSION",
            "RELATIONAL_MAX_SCHEMA_VERSION",
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

    def test_revision_scaffold_includes_r0002_and_r0003(self):
        revision_ids = [item.revision for item in self.module.RELATIONAL_REVISIONS]
        self.assertIn("r0002_runtime_core_tables", revision_ids)
        self.assertIn("r0003_runtime_observability_tables", revision_ids)
        self.assertIn("r0004_runtime_metadata_columns", revision_ids)
        self.assertIn("r0005_runtime_quality_constraints", revision_ids)
        self.assertIn("r0006_runtime_evolution_checkpoints", revision_ids)

        sql_blob = "\n".join(
            "\n".join(item.statements).lower() for item in self.module.RELATIONAL_REVISIONS
        )
        self.assertIn("sixpx_workflows", sql_blob)
        self.assertIn("sixpx_runs", sql_blob)
        self.assertIn("sixpx_integrations", sql_blob)
        self.assertIn("sixpx_bots", sql_blob)
        self.assertIn("sixpx_settings", sql_blob)
        self.assertIn("sixpx_run_events", sql_blob)
        self.assertIn("sixpx_connector_executions", sql_blob)
        self.assertIn("add column if not exists metadata", sql_blob)
        self.assertIn("sixpx_workflows_graph_is_object", sql_blob)
        self.assertIn("sixpx_connector_duration_nonnegative", sql_blob)
        self.assertIn("sixpx_data_evolution_checkpoints", sql_blob)
        self.assertIn("idx_sixpx_evolution_checkpoints_recorded_at", sql_blob)

    def test_unknown_revision_is_error_when_not_allowed(self):
        manager = self.module.RelationalMigrationManager(database_url="")
        compatibility = manager.evaluate_schema_compatibility({"r9999_future_runtime"})
        self.assertEqual("error", compatibility.get("status"))
        self.assertGreater(int(compatibility.get("error_count", 0)), 0)

    def test_unknown_revision_can_be_warning_when_allowed(self):
        os.environ["RELATIONAL_ALLOW_UNKNOWN_REVISIONS"] = "true"
        manager = self.module.RelationalMigrationManager(database_url="")
        compatibility = manager.evaluate_schema_compatibility({"r9999_future_runtime"})
        self.assertEqual("warn", compatibility.get("status"))
        self.assertEqual(0, int(compatibility.get("error_count", 0)))

    def test_schema_range_violation_is_error(self):
        os.environ["RELATIONAL_MAX_SCHEMA_VERSION"] = "2"
        manager = self.module.RelationalMigrationManager(database_url="")
        compatibility = manager.evaluate_schema_compatibility({"r0003_runtime_observability_tables"})
        self.assertEqual("error", compatibility.get("status"))
        self.assertIn("exceeds maximum supported", " ".join(compatibility.get("errors", [])))

    def test_constraint_validation_disabled_without_database(self):
        manager = self.module.RelationalMigrationManager(database_url="")
        result = manager.validate_constraints(apply=False, limit=25)
        self.assertEqual("disabled", result.get("status"))
        self.assertFalse(bool(result.get("connected")))
        self.assertEqual(0, int(result.get("attempted_count", 0)))


if __name__ == "__main__":
    unittest.main()
