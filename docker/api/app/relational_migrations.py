"""Postgres relational migration scaffolds + compatibility guardrails."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
import re
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class RelationalRevision:
    def __init__(
        self,
        revision: str,
        description: str,
        statements: tuple[str, ...],
        schema_version: int | None = None,
    ) -> None:
        self.revision = str(revision)
        self.description = str(description)
        self.statements = tuple(statements)
        self.schema_version = (
            max(1, int(schema_version))
            if schema_version is not None
            else revision_schema_version(self.revision)
        )


_REVISION_SCHEMA_RE = re.compile(r"^r(\d{4})[_\-].*$", re.IGNORECASE)
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def revision_schema_version(revision: str) -> int:
    matched = _REVISION_SCHEMA_RE.match(str(revision or "").strip())
    if not matched:
        return 0
    return max(0, int(matched.group(1)))


def _quote_identifier(value: Any) -> str:
    identifier = str(value or "").strip()
    if not identifier or not _SQL_IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return f'"{identifier}"'


RELATIONAL_REVISIONS: tuple[RelationalRevision, ...] = (
    RelationalRevision(
        revision="r0001_initial_runtime_scaffold",
        description=(
            "Create baseline relational migration history and runtime state tables "
            "for future Postgres-backed persistence."
        ),
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sixpx_schema_migrations (
                revision TEXT PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                app_version TEXT NOT NULL DEFAULT ''
            )
            """.strip(),
            """
            CREATE TABLE IF NOT EXISTS sixpx_runtime_state (
                state_key TEXT PRIMARY KEY,
                state_value JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            INSERT INTO sixpx_runtime_state (state_key, state_value)
            VALUES ('bootstrap', jsonb_build_object('initialized', true))
            ON CONFLICT (state_key) DO NOTHING
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0002_runtime_core_tables",
        description=(
            "Create baseline relational runtime tables for workflows, runs, integrations, bots, "
            "and settings."
        ),
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sixpx_workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                graph JSONB NOT NULL DEFAULT '{"nodes":[],"edges":[]}'::jsonb,
                status TEXT NOT NULL DEFAULT 'draft',
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_workflows_updated_at
            ON sixpx_workflows (updated_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_workflows_status
            ON sixpx_workflows (status)
            """.strip(),
            """
            CREATE TABLE IF NOT EXISTS sixpx_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL DEFAULT '',
                workflow_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                trigger TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                log TEXT NOT NULL DEFAULT '',
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                finished_at TIMESTAMPTZ NULL
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_runs_workflow_id
            ON sixpx_runs (workflow_id)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_runs_status_created_at
            ON sixpx_runs (status, created_at DESC)
            """.strip(),
            """
            CREATE TABLE IF NOT EXISTS sixpx_integrations (
                id TEXT PRIMARY KEY,
                integration_key TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                config JSONB NOT NULL DEFAULT '{}'::jsonb,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_integrations_key_enabled
            ON sixpx_integrations (integration_key, enabled)
            """.strip(),
            """
            CREATE TABLE IF NOT EXISTS sixpx_bots (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT 'local',
                model TEXT NOT NULL DEFAULT '',
                config JSONB NOT NULL DEFAULT '{}'::jsonb,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_bots_provider_enabled
            ON sixpx_bots (provider, enabled)
            """.strip(),
            """
            CREATE TABLE IF NOT EXISTS sixpx_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            INSERT INTO sixpx_settings (setting_key, setting_value)
            VALUES ('bootstrap', jsonb_build_object('ready', true))
            ON CONFLICT (setting_key) DO NOTHING
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0003_runtime_observability_tables",
        description=(
            "Create timeline and connector execution tables for run observability and diagnostics."
        ),
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sixpx_run_events (
                event_id BIGSERIAL PRIMARY KEY,
                run_id TEXT NOT NULL DEFAULT '',
                workflow_id TEXT NOT NULL DEFAULT '',
                node_id TEXT NOT NULL DEFAULT '',
                node_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                details JSONB NOT NULL DEFAULT '{}'::jsonb,
                event_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_run_events_run_id_event_at
            ON sixpx_run_events (run_id, event_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_run_events_workflow_id_event_at
            ON sixpx_run_events (workflow_id, event_at DESC)
            """.strip(),
            """
            CREATE TABLE IF NOT EXISTS sixpx_connector_executions (
                execution_id BIGSERIAL PRIMARY KEY,
                run_id TEXT NOT NULL DEFAULT '',
                workflow_id TEXT NOT NULL DEFAULT '',
                integration_key TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                duration_ms INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT '',
                response_excerpt TEXT NOT NULL DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_connector_exec_run_created
            ON sixpx_connector_executions (run_id, created_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_connector_exec_key_status
            ON sixpx_connector_executions (integration_key, status)
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0004_runtime_metadata_columns",
        description=(
            "Add metadata columns for workflow/integration/bot repositories used by Postgres cutover."
        ),
        statements=(
            """
            ALTER TABLE sixpx_workflows
            ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            """.strip(),
            """
            ALTER TABLE sixpx_integrations
            ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            """.strip(),
            """
            ALTER TABLE sixpx_bots
            ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0005_runtime_quality_constraints",
        description=(
            "Add runtime data-quality guardrails and performance indexes for Postgres-backed repositories."
        ),
        statements=(
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_runs_workflow_status_updated
            ON sixpx_runs (workflow_id, status, updated_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_run_events_status_event_at
            ON sixpx_run_events (status, event_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_connector_exec_provider_status_created
            ON sixpx_connector_executions (provider, status, created_at DESC)
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_workflows_graph_is_object'
                ) THEN
                    ALTER TABLE sixpx_workflows
                    ADD CONSTRAINT sixpx_workflows_graph_is_object
                    CHECK (jsonb_typeof(graph) = 'object') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_workflows_tags_is_array'
                ) THEN
                    ALTER TABLE sixpx_workflows
                    ADD CONSTRAINT sixpx_workflows_tags_is_array
                    CHECK (jsonb_typeof(tags) = 'array') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_runs_payload_is_object'
                ) THEN
                    ALTER TABLE sixpx_runs
                    ADD CONSTRAINT sixpx_runs_payload_is_object
                    CHECK (jsonb_typeof(payload) = 'object') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_integrations_config_is_object'
                ) THEN
                    ALTER TABLE sixpx_integrations
                    ADD CONSTRAINT sixpx_integrations_config_is_object
                    CHECK (jsonb_typeof(config) = 'object') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_integrations_tags_is_array'
                ) THEN
                    ALTER TABLE sixpx_integrations
                    ADD CONSTRAINT sixpx_integrations_tags_is_array
                    CHECK (jsonb_typeof(tags) = 'array') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_bots_config_is_object'
                ) THEN
                    ALTER TABLE sixpx_bots
                    ADD CONSTRAINT sixpx_bots_config_is_object
                    CHECK (jsonb_typeof(config) = 'object') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_bots_tags_is_array'
                ) THEN
                    ALTER TABLE sixpx_bots
                    ADD CONSTRAINT sixpx_bots_tags_is_array
                    CHECK (jsonb_typeof(tags) = 'array') NOT VALID;
                END IF;
            END
            $$
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_connector_duration_nonnegative'
                ) THEN
                    ALTER TABLE sixpx_connector_executions
                    ADD CONSTRAINT sixpx_connector_duration_nonnegative
                    CHECK (duration_ms >= 0) NOT VALID;
                END IF;
            END
            $$
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0006_runtime_evolution_checkpoints",
        description=(
            "Add migration checkpoint history table to support safer schema evolution tracking."
        ),
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sixpx_data_evolution_checkpoints (
                checkpoint_id BIGSERIAL PRIMARY KEY,
                revision TEXT NOT NULL DEFAULT '',
                schema_version INTEGER NOT NULL DEFAULT 0,
                app_version TEXT NOT NULL DEFAULT '',
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_evolution_checkpoints_recorded_at
            ON sixpx_data_evolution_checkpoints (recorded_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_evolution_checkpoints_revision
            ON sixpx_data_evolution_checkpoints (revision)
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0007_runtime_schema_revision_audit",
        description=(
            "Add explicit schema revision audit ledger for migration provenance and safer data evolution."
        ),
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sixpx_schema_revision_audit (
                audit_id BIGSERIAL PRIMARY KEY,
                revision TEXT NOT NULL DEFAULT '',
                schema_version INTEGER NOT NULL DEFAULT 0,
                app_version TEXT NOT NULL DEFAULT '',
                applied_by TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'runtime',
                revision_checksum TEXT NOT NULL DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_schema_revision_audit_recorded
            ON sixpx_schema_revision_audit (recorded_at DESC)
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_schema_revision_audit_revision
            ON sixpx_schema_revision_audit (revision)
            """.strip(),
        ),
    ),
    RelationalRevision(
        revision="r0008_runtime_schema_boundaries",
        description=(
            "Add relational schema-boundary policy ledger for safer, auditable data evolution."
        ),
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sixpx_schema_boundaries (
                boundary_id BIGSERIAL PRIMARY KEY,
                min_supported_schema_version INTEGER NOT NULL DEFAULT 1,
                max_supported_schema_version INTEGER NOT NULL DEFAULT 0,
                enforce_compatibility BOOLEAN NOT NULL DEFAULT TRUE,
                allow_unknown_revisions BOOLEAN NOT NULL DEFAULT FALSE,
                source TEXT NOT NULL DEFAULT 'runtime',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """.strip(),
            """
            CREATE INDEX IF NOT EXISTS idx_sixpx_schema_boundaries_recorded_at
            ON sixpx_schema_boundaries (recorded_at DESC)
            """.strip(),
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sixpx_schema_boundaries_valid_range'
                ) THEN
                    ALTER TABLE sixpx_schema_boundaries
                    ADD CONSTRAINT sixpx_schema_boundaries_valid_range
                    CHECK (max_supported_schema_version >= min_supported_schema_version) NOT VALID;
                END IF;
            END
            $$
            """.strip(),
        ),
    ),
)

KNOWN_RELATIONAL_REVISIONS = {item.revision for item in RELATIONAL_REVISIONS}
KNOWN_RELATIONAL_SCHEMA_VERSIONS = sorted(
    {item.schema_version for item in RELATIONAL_REVISIONS if item.schema_version > 0}
)
LATEST_RELATIONAL_SCHEMA_VERSION = max(KNOWN_RELATIONAL_SCHEMA_VERSIONS or [1])


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return default


def _to_int(value: Any, default: int = 0, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def mask_database_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except Exception:
        return ""
    netloc = parts.netloc
    if "@" in netloc:
        auth, host = netloc.rsplit("@", 1)
        user = auth.split(":", 1)[0] if auth else ""
        masked_auth = f"{user}:***" if user else "***"
        netloc = f"{masked_auth}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class RelationalMigrationManager:
    def __init__(
        self,
        *,
        database_url: str = "",
        connect_timeout_sec: int | None = None,
        retry_attempts: int | None = None,
        retry_delay_sec: float | None = None,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        self.enforce_compatibility = _to_bool(
            os.getenv("RELATIONAL_MIGRATION_ENFORCE_COMPATIBILITY", "true"),
            default=True,
        )
        self.allow_unknown_revisions = _to_bool(
            os.getenv("RELATIONAL_ALLOW_UNKNOWN_REVISIONS", "false"),
            default=False,
        )
        self.min_supported_schema_version = _to_int(
            os.getenv("RELATIONAL_MIN_SCHEMA_VERSION", "1"),
            default=1,
            minimum=1,
            maximum=LATEST_RELATIONAL_SCHEMA_VERSION,
        )
        self.max_supported_schema_version = _to_int(
            os.getenv("RELATIONAL_MAX_SCHEMA_VERSION", str(LATEST_RELATIONAL_SCHEMA_VERSION)),
            default=LATEST_RELATIONAL_SCHEMA_VERSION,
            minimum=self.min_supported_schema_version,
        )
        self.connect_timeout_sec = _to_int(
            connect_timeout_sec
            if connect_timeout_sec is not None
            else os.getenv("RELATIONAL_MIGRATION_CONNECT_TIMEOUT_SEC", "3"),
            default=3,
            minimum=1,
            maximum=30,
        )
        self.retry_attempts = _to_int(
            retry_attempts
            if retry_attempts is not None
            else os.getenv("RELATIONAL_MIGRATION_RETRY_ATTEMPTS", "2"),
            default=2,
            minimum=1,
            maximum=10,
        )
        try:
            self.retry_delay_sec = max(
                0.1,
                float(
                    retry_delay_sec
                    if retry_delay_sec is not None
                    else os.getenv("RELATIONAL_MIGRATION_RETRY_DELAY_SEC", "1.0")
                ),
            )
        except (TypeError, ValueError):
            self.retry_delay_sec = 1.0
        self.required = _to_bool(os.getenv("RELATIONAL_MIGRATION_REQUIRED", "false"), default=False)
        self.lock_enabled = _to_bool(
            os.getenv("RELATIONAL_MIGRATION_LOCK_ENABLED", "true"),
            default=True,
        )
        self.lock_required = _to_bool(
            os.getenv("RELATIONAL_MIGRATION_LOCK_REQUIRED", "true"),
            default=True,
        )
        self.lock_id = _to_int(
            os.getenv("RELATIONAL_MIGRATION_LOCK_ID", "6007001"),
            default=6007001,
            minimum=1,
        )
        try:
            self.lock_timeout_sec = max(
                0.5,
                float(os.getenv("RELATIONAL_MIGRATION_LOCK_TIMEOUT_SEC", "12.0")),
            )
        except (TypeError, ValueError):
            self.lock_timeout_sec = 12.0
        try:
            self.lock_poll_sec = max(
                0.05,
                float(os.getenv("RELATIONAL_MIGRATION_LOCK_POLL_SEC", "0.2")),
            )
        except (TypeError, ValueError):
            self.lock_poll_sec = 0.2
        self._last_snapshot: dict[str, Any] = self._base_snapshot(status="disabled")

    def _base_snapshot(self, *, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "enabled": bool(self.database_url),
            "required": bool(self.required),
            "enforce_compatibility": bool(self.enforce_compatibility),
            "allow_unknown_revisions": bool(self.allow_unknown_revisions),
            "database_url_configured": bool(self.database_url),
            "database_url_masked": mask_database_url(self.database_url),
            "migration_lock_enabled": bool(self.lock_enabled),
            "migration_lock_required": bool(self.lock_required),
            "migration_lock_id": int(self.lock_id),
            "migration_lock_timeout_sec": float(self.lock_timeout_sec),
            "migration_lock_status": "idle",
            "migration_lock_acquired": False,
            "driver_available": False,
            "connected": False,
            "revision_count": len(RELATIONAL_REVISIONS),
            "latest_known_schema_version": LATEST_RELATIONAL_SCHEMA_VERSION,
            "min_supported_schema_version": self.min_supported_schema_version,
            "max_supported_schema_version": self.max_supported_schema_version,
            "current_schema_version": 0,
            "unknown_revisions": [],
            "compatibility_status": "pending",
            "compatibility_issue_count": 0,
            "compatibility_errors": [],
            "compatibility_warnings": [],
            "unvalidated_constraint_count": 0,
            "unvalidated_constraints": [],
            "schema_revision_audit_available": False,
            "schema_revision_audit_count": 0,
            "applied_count": 0,
            "pending_count": len(RELATIONAL_REVISIONS),
            "applied_revisions": [],
            "pending_revisions": [item.revision for item in RELATIONAL_REVISIONS],
            "last_error": "",
            "last_applied_revision": "",
            "checked_at": datetime.now(UTC).isoformat(),
        }

    def _import_psycopg(self):
        try:
            import psycopg  # type: ignore
        except Exception:
            return None
        return psycopg

    def _ensure_migration_table(self, connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sixpx_schema_migrations (
                    revision TEXT PRIMARY KEY,
                    description TEXT NOT NULL DEFAULT '',
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    app_version TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def _load_applied_revisions(self, connection) -> set[str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT revision FROM sixpx_schema_migrations")
            rows = cursor.fetchall() or []
        revisions: set[str] = set()
        for row in rows:
            if not row:
                continue
            revisions.add(str(row[0]).strip())
        return revisions

    def _load_unvalidated_constraints(self, connection) -> list[dict[str, str]]:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cls.relname AS table_name, con.conname AS constraint_name
                    FROM pg_constraint con
                    JOIN pg_class cls ON cls.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
                    WHERE nsp.nspname = CURRENT_SCHEMA()
                      AND cls.relname LIKE 'sixpx\\_%' ESCAPE '\\'
                      AND NOT con.convalidated
                    ORDER BY cls.relname, con.conname
                    """
                )
                rows = cursor.fetchall() or []
        except Exception:
            return []

        constraints: list[dict[str, str]] = []
        for row in rows:
            if not row or len(row) < 2:
                continue
            table_name = str(row[0] or "").strip()
            constraint_name = str(row[1] or "").strip()
            if not table_name or not constraint_name:
                continue
            constraints.append(
                {
                    "table": table_name,
                    "constraint": constraint_name,
                }
            )
        return constraints

    def _load_schema_revision_audit_count(self, connection) -> tuple[bool, int]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('sixpx_schema_revision_audit')")
                table = cursor.fetchone()
                if not table or not table[0]:
                    return False, 0
                cursor.execute("SELECT COUNT(*) FROM sixpx_schema_revision_audit")
                row = cursor.fetchone()
                count = int(row[0]) if row and row[0] is not None else 0
                return True, max(0, count)
        except Exception:
            return False, 0

    def _acquire_migration_lock(self, connection) -> tuple[bool, str]:
        if not self.lock_enabled:
            return True, "disabled"

        deadline = monotonic() + self.lock_timeout_sec
        while monotonic() <= deadline:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", (int(self.lock_id),))
                    row = cursor.fetchone()
                    locked = bool(row[0]) if row else False
                if locked:
                    return True, "acquired"
            except Exception as error:
                return False, f"error:{error}"
            sleep(self.lock_poll_sec)
        return False, "timeout"

    def _release_migration_lock(self, connection) -> None:
        if not self.lock_enabled:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (int(self.lock_id),))
        except Exception:
            return

    def validate_constraints(
        self,
        *,
        apply: bool = False,
        limit: int = 50,
        stop_on_error: bool = False,
        app_version: str = "",
        reason: str = "",
        requested_by: str = "",
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "status": "disabled",
            "enabled": bool(self.database_url),
            "database_url_configured": bool(self.database_url),
            "database_url_masked": mask_database_url(self.database_url),
            "migration_lock_enabled": bool(self.lock_enabled),
            "migration_lock_required": bool(self.lock_required),
            "migration_lock_id": int(self.lock_id),
            "migration_lock_timeout_sec": float(self.lock_timeout_sec),
            "migration_lock_status": "idle",
            "migration_lock_acquired": False,
            "applied": bool(apply),
            "stop_on_error": bool(stop_on_error),
            "requested_limit": _to_int(limit, default=50, minimum=1, maximum=500),
            "driver_available": False,
            "connected": False,
            "attempted_count": 0,
            "validated_count": 0,
            "failed_count": 0,
            "remaining_count": 0,
            "failed": [],
            "remaining": [],
            "verify_after_apply": bool(apply),
            "verified_removed_count": 0,
            "still_pending_attempted": [],
            "checkpoint_recorded": False,
            "checkpoint_revision": "",
            "checkpoint_error": "",
            "reason": str(reason or "").strip(),
            "requested_by": str(requested_by or "").strip(),
            "last_error": "",
            "checked_at": datetime.now(UTC).isoformat(),
        }
        if not self.database_url:
            return snapshot

        psycopg = self._import_psycopg()
        if psycopg is None:
            snapshot["status"] = "error"
            snapshot["last_error"] = "psycopg driver not available"
            return snapshot
        snapshot["driver_available"] = True

        requested_limit = int(snapshot["requested_limit"])
        last_error = ""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_sec) as connection:
                    snapshot["connected"] = True
                    constraints = self._load_unvalidated_constraints(connection)
                    selected = list(constraints[:requested_limit])
                    snapshot["attempted_count"] = len(selected)

                    failures: list[dict[str, str]] = []
                    validated = 0
                    lock_acquired = False
                    if apply:
                        lock_acquired, lock_status = self._acquire_migration_lock(connection)
                        snapshot["migration_lock_status"] = lock_status
                        snapshot["migration_lock_acquired"] = bool(lock_acquired)
                        if not lock_acquired and self.lock_required:
                            snapshot["last_error"] = (
                                "Migration lock acquisition failed before constraint apply: "
                                f"{lock_status}"
                            )
                            break
                        try:
                            for item in selected:
                                table_name = str(item.get("table", "")).strip()
                                constraint_name = str(item.get("constraint", "")).strip()
                                if not table_name or not constraint_name:
                                    failures.append(
                                        {
                                            "table": table_name,
                                            "constraint": constraint_name,
                                            "error": "Missing table/constraint name",
                                        }
                                    )
                                    if stop_on_error:
                                        break
                                    continue
                                try:
                                    quoted_table = _quote_identifier(table_name)
                                    quoted_constraint = _quote_identifier(constraint_name)
                                    with connection.transaction():
                                        with connection.cursor() as cursor:
                                            cursor.execute(
                                                f"ALTER TABLE {quoted_table} "
                                                f"VALIDATE CONSTRAINT {quoted_constraint}"
                                            )
                                    validated += 1
                                except Exception as error:
                                    failures.append(
                                        {
                                            "table": table_name,
                                            "constraint": constraint_name,
                                            "error": str(error),
                                        }
                                    )
                                    if stop_on_error:
                                        break
                        finally:
                            if lock_acquired:
                                self._release_migration_lock(connection)

                    remaining = self._load_unvalidated_constraints(connection)
                    attempted_pairs = {
                        (
                            str(item.get("table", "")).strip(),
                            str(item.get("constraint", "")).strip(),
                        )
                        for item in selected
                    }
                    remaining_pairs = {
                        (
                            str(item.get("table", "")).strip(),
                            str(item.get("constraint", "")).strip(),
                        )
                        for item in remaining
                    }
                    still_pending = sorted(
                        [
                            {"table": table_name, "constraint": constraint_name}
                            for table_name, constraint_name in attempted_pairs.intersection(remaining_pairs)
                            if table_name and constraint_name
                        ],
                        key=lambda item: (item["table"], item["constraint"]),
                    )
                    snapshot["still_pending_attempted"] = still_pending
                    snapshot["verified_removed_count"] = max(
                        0,
                        int(snapshot["attempted_count"]) - len(still_pending),
                    )

                    if apply:
                        checkpoint_revision = "ops_validate_constraints_apply"
                        snapshot["checkpoint_revision"] = checkpoint_revision
                        try:
                            applied_revisions = self._load_applied_revisions(connection)
                            compatibility = self.evaluate_schema_compatibility(applied_revisions)
                            schema_version = int(compatibility.get("current_schema_version", 0))
                            snapshot["checkpoint_recorded"] = self._record_evolution_checkpoint(
                                connection,
                                revision=checkpoint_revision,
                                schema_version=schema_version,
                                app_version=str(app_version or "").strip(),
                                payload={
                                    "attempted_count": int(snapshot["attempted_count"]),
                                    "validated_count": int(validated),
                                    "failed_count": len(failures),
                                    "remaining_count": len(remaining),
                                    "still_pending_attempted": still_pending,
                                    "reason": str(reason or "").strip(),
                                    "requested_by": str(requested_by or "").strip(),
                                    "stop_on_error": bool(stop_on_error),
                                },
                            )
                        except Exception as checkpoint_error:
                            snapshot["checkpoint_error"] = str(checkpoint_error)
                    snapshot["validated_count"] = validated
                    snapshot["failed"] = failures
                    snapshot["failed_count"] = len(failures)
                    snapshot["remaining"] = remaining
                    snapshot["remaining_count"] = len(remaining)
                break
            except Exception as error:
                last_error = str(error)
                if attempt < self.retry_attempts:
                    sleep(self.retry_delay_sec)

        snapshot["last_error"] = str(snapshot.get("last_error", "") or last_error)
        if not snapshot["connected"]:
            snapshot["status"] = "error"
        elif (
            apply
            and bool(snapshot.get("migration_lock_enabled", False))
            and bool(snapshot.get("migration_lock_required", False))
            and not bool(snapshot.get("migration_lock_acquired", False))
        ):
            snapshot["status"] = "error"
        elif (
            apply
            and bool(snapshot.get("migration_lock_enabled", False))
            and not bool(snapshot.get("migration_lock_acquired", False))
        ):
            snapshot["status"] = "warn"
        elif apply and snapshot["checkpoint_error"]:
            snapshot["status"] = "warn"
        elif snapshot["failed_count"] > 0:
            snapshot["status"] = "error" if stop_on_error else "warn"
        elif apply and snapshot["still_pending_attempted"]:
            snapshot["status"] = "warn"
        elif snapshot["remaining_count"] > 0:
            snapshot["status"] = "warn"
        else:
            snapshot["status"] = "ok"
        snapshot["checked_at"] = datetime.now(UTC).isoformat()
        return snapshot

    def evaluate_schema_compatibility(self, applied_revisions: set[str]) -> dict[str, Any]:
        applied = {item for item in applied_revisions if str(item).strip()}
        unknown = sorted(item for item in applied if item not in KNOWN_RELATIONAL_REVISIONS)
        version_map = {item.revision: item.schema_version for item in RELATIONAL_REVISIONS}
        known_versions = sorted(version_map[item] for item in applied if item in version_map)
        current_schema_version = max(known_versions or [0])

        errors: list[str] = []
        warnings: list[str] = []

        if unknown:
            message = (
                "Unknown applied relational revisions detected: "
                f"{', '.join(unknown)}. "
                "This typically indicates a newer server touched the database."
            )
            if self.allow_unknown_revisions:
                warnings.append(message)
            else:
                errors.append(message)

        if current_schema_version and current_schema_version < self.min_supported_schema_version:
            errors.append(
                "Current relational schema version "
                f"{current_schema_version} is below minimum supported "
                f"{self.min_supported_schema_version}."
            )
        if current_schema_version and current_schema_version > self.max_supported_schema_version:
            errors.append(
                "Current relational schema version "
                f"{current_schema_version} exceeds maximum supported "
                f"{self.max_supported_schema_version}."
            )
        if not current_schema_version and applied:
            warnings.append(
                "Applied revisions exist but none map to known schema versions; "
                "compatibility confidence reduced."
            )

        status = "error" if errors else "warn" if warnings else "ok"
        return {
            "status": status,
            "current_schema_version": current_schema_version,
            "unknown_revisions": unknown,
            "error_count": len(errors),
            "warn_count": len(warnings),
            "issue_count": len(errors) + len(warnings),
            "errors": errors,
            "warnings": warnings,
        }

    def _revision_checksum(self, revision: RelationalRevision) -> str:
        payload = "\n".join(
            [revision.revision, revision.description, *(item for item in revision.statements)]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _record_applied_revision(self, connection, revision: RelationalRevision, app_version: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sixpx_schema_migrations (revision, description, app_version)
                VALUES (%s, %s, %s)
                ON CONFLICT (revision) DO NOTHING
                """,
                (revision.revision, revision.description, app_version),
            )
            cursor.execute(
                """
                INSERT INTO sixpx_runtime_state (state_key, state_value, updated_at)
                VALUES (
                    'relational_schema',
                    jsonb_build_object(
                        'version', %s::INTEGER,
                        'revision', %s::TEXT,
                        'app_version', %s::TEXT
                    ),
                    NOW()
                )
                ON CONFLICT (state_key)
                DO UPDATE SET
                    state_value = EXCLUDED.state_value,
                    updated_at = NOW()
                """,
                (revision.schema_version, revision.revision, app_version),
            )
        self._record_evolution_checkpoint(
            connection,
            revision=revision.revision,
            schema_version=revision.schema_version,
            app_version=app_version,
            payload={"source": "migration_apply"},
        )
        self._record_schema_revision_audit(
            connection,
            revision=revision,
            app_version=app_version,
            applied_by="migration-manager",
            source="migration_apply",
        )

    def _record_schema_revision_audit(
        self,
        connection,
        *,
        revision: RelationalRevision,
        app_version: str,
        applied_by: str,
        source: str,
    ) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('sixpx_schema_revision_audit')")
            audit_table = cursor.fetchone()
            if not audit_table or not audit_table[0]:
                return False
            cursor.execute(
                """
                INSERT INTO sixpx_schema_revision_audit (
                    revision,
                    schema_version,
                    app_version,
                    applied_by,
                    source,
                    revision_checksum,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    revision.revision,
                    revision.schema_version,
                    str(app_version or "").strip(),
                    str(applied_by or "").strip(),
                    str(source or "").strip() or "runtime",
                    self._revision_checksum(revision),
                    json.dumps(
                        {
                            "description": revision.description,
                            "statement_count": len(revision.statements),
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ),
            )
        return True

    def _record_evolution_checkpoint(
        self,
        connection,
        *,
        revision: str,
        schema_version: int,
        app_version: str,
        payload: Any,
    ) -> bool:
        if isinstance(payload, dict):
            checkpoint_payload = dict(payload)
        else:
            checkpoint_payload = {"value": str(payload)}
        payload_json = json.dumps(checkpoint_payload, separators=(",", ":"), sort_keys=True)

        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('sixpx_data_evolution_checkpoints')")
            checkpoint_table = cursor.fetchone()
            if not checkpoint_table or not checkpoint_table[0]:
                return False
            cursor.execute(
                """
                INSERT INTO sixpx_data_evolution_checkpoints (
                    revision,
                    schema_version,
                    app_version,
                    payload
                )
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    str(revision or "").strip(),
                    int(schema_version),
                    str(app_version or "").strip(),
                    payload_json,
                ),
            )
        return True

    def apply(self, *, app_version: str) -> dict[str, Any]:
        if not self.database_url:
            self._last_snapshot = self._base_snapshot(status="disabled")
            return dict(self._last_snapshot)

        snapshot = self._base_snapshot(status="pending")
        psycopg = self._import_psycopg()
        if psycopg is None:
            snapshot["status"] = "error"
            snapshot["last_error"] = "psycopg driver not available"
            self._last_snapshot = snapshot
            return dict(self._last_snapshot)
        snapshot["driver_available"] = True

        applied_revisions: set[str] = set()
        unvalidated_constraints: list[dict[str, str]] = []
        schema_revision_audit_available = False
        schema_revision_audit_count = 0
        last_error = ""
        connected = False
        lock_acquired = False
        lock_status = "idle"
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_sec) as connection:
                    connected = True
                    lock_acquired, lock_status = self._acquire_migration_lock(connection)
                    snapshot["migration_lock_status"] = lock_status
                    snapshot["migration_lock_acquired"] = bool(lock_acquired)
                    if not lock_acquired and self.lock_required:
                        last_error = (
                            "Migration lock acquisition failed before schema apply: "
                            f"{lock_status}"
                        )
                        break
                    try:
                        self._ensure_migration_table(connection)
                        connection.commit()
                        applied_revisions = self._load_applied_revisions(connection)
                        for revision in RELATIONAL_REVISIONS:
                            if revision.revision in applied_revisions:
                                continue
                            with connection.transaction():
                                for statement in revision.statements:
                                    if str(statement).strip():
                                        with connection.cursor() as cursor:
                                            cursor.execute(statement)
                                self._record_applied_revision(connection, revision, app_version)
                            applied_revisions.add(revision.revision)
                        connection.commit()
                        unvalidated_constraints = self._load_unvalidated_constraints(connection)
                        (
                            schema_revision_audit_available,
                            schema_revision_audit_count,
                        ) = self._load_schema_revision_audit_count(connection)
                    finally:
                        if lock_acquired:
                            self._release_migration_lock(connection)
                break
            except Exception as error:
                last_error = str(error)
                if attempt < self.retry_attempts:
                    sleep(self.retry_delay_sec)

        pending_revisions = [
            item.revision for item in RELATIONAL_REVISIONS if item.revision not in applied_revisions
        ]
        snapshot["connected"] = connected
        snapshot["applied_revisions"] = sorted(applied_revisions)
        snapshot["pending_revisions"] = pending_revisions
        snapshot["applied_count"] = len(applied_revisions)
        snapshot["pending_count"] = len(pending_revisions)
        snapshot["last_applied_revision"] = snapshot["applied_revisions"][-1] if snapshot["applied_revisions"] else ""

        compatibility = self.evaluate_schema_compatibility(applied_revisions)
        snapshot["current_schema_version"] = int(compatibility.get("current_schema_version", 0))
        snapshot["unknown_revisions"] = list(compatibility.get("unknown_revisions", []))
        snapshot["compatibility_status"] = str(compatibility.get("status", "error"))
        snapshot["compatibility_issue_count"] = int(compatibility.get("issue_count", 0))
        snapshot["compatibility_errors"] = list(compatibility.get("errors", []))
        snapshot["compatibility_warnings"] = list(compatibility.get("warnings", []))
        snapshot["unvalidated_constraints"] = list(unvalidated_constraints)
        snapshot["unvalidated_constraint_count"] = len(unvalidated_constraints)
        snapshot["schema_revision_audit_available"] = bool(schema_revision_audit_available)
        snapshot["schema_revision_audit_count"] = int(schema_revision_audit_count)

        snapshot["last_error"] = last_error

        has_compatibility_errors = bool(snapshot["compatibility_errors"])
        if (
            connected
            and bool(snapshot.get("migration_lock_enabled", False))
            and bool(snapshot.get("migration_lock_required", False))
            and not bool(snapshot.get("migration_lock_acquired", False))
        ):
            snapshot["status"] = "error"
        elif connected and not pending_revisions and not has_compatibility_errors:
            snapshot["status"] = "ok"
        elif connected and has_compatibility_errors:
            snapshot["status"] = "error" if self.enforce_compatibility else "warn"
        elif connected:
            snapshot["status"] = "warn"
        else:
            snapshot["status"] = "error"
        if (
            connected
            and bool(snapshot.get("migration_lock_enabled", False))
            and not bool(snapshot.get("migration_lock_required", False))
            and not bool(snapshot.get("migration_lock_acquired", False))
            and snapshot["status"] == "ok"
        ):
            snapshot["status"] = "warn"
        snapshot["checked_at"] = datetime.now(UTC).isoformat()

        self._last_snapshot = snapshot
        return dict(self._last_snapshot)

    def status(self) -> dict[str, Any]:
        return dict(self._last_snapshot)
