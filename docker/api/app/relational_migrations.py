"""Postgres relational migration scaffold for Docker runtime GA hardening."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from time import sleep
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class RelationalRevision:
    def __init__(self, revision: str, description: str, statements: tuple[str, ...]) -> None:
        self.revision = str(revision)
        self.description = str(description)
        self.statements = tuple(statements)


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
)


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
            "database_url_configured": bool(self.database_url),
            "database_url_masked": mask_database_url(self.database_url),
            "driver_available": False,
            "connected": False,
            "revision_count": len(RELATIONAL_REVISIONS),
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
        snapshot["last_error"] = last_error
        if connected and not pending_revisions:
            snapshot["status"] = "ok"
        elif connected:
            snapshot["status"] = "warn"
        else:
            snapshot["status"] = "error"
        snapshot["checked_at"] = datetime.now(UTC).isoformat()

        self._last_snapshot = snapshot
        return dict(self._last_snapshot)

    def status(self) -> dict[str, Any]:
        return dict(self._last_snapshot)
