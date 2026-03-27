"""Postgres relational migration scaffolds + compatibility guardrails."""

from __future__ import annotations

from datetime import UTC, datetime
import os
import re
from time import sleep
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


def revision_schema_version(revision: str) -> int:
    matched = _REVISION_SCHEMA_RE.match(str(revision or "").strip())
    if not matched:
        return 0
    return max(0, int(matched.group(1)))


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
        last_error = ""
        connected = False
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_sec) as connection:
                    connected = True
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

        snapshot["last_error"] = last_error

        has_compatibility_errors = bool(snapshot["compatibility_errors"])
        if connected and not pending_revisions and not has_compatibility_errors:
            snapshot["status"] = "ok"
        elif connected and has_compatibility_errors:
            snapshot["status"] = "error" if self.enforce_compatibility else "warn"
        elif connected:
            snapshot["status"] = "warn"
        else:
            snapshot["status"] = "error"
        snapshot["checked_at"] = datetime.now(UTC).isoformat()

        self._last_snapshot = snapshot
        return dict(self._last_snapshot)

    def status(self) -> dict[str, Any]:
        return dict(self._last_snapshot)
