"""Simple JSON storage layer for the web-edition API scaffold.

This intentionally uses JSON files for fast iteration. The schema is stable enough
that we can later swap this for Postgres repositories behind the same interface.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
import threading
from pathlib import Path
from typing import Any

STORE_SCHEMA_VERSION = 2


class JsonStore:
    def __init__(self, data_dir: str | None = None) -> None:
        default_dir = Path("/data/6x-protocol")
        self.data_dir = Path(data_dir or os.getenv("SCAFFOLD_DATA_DIR") or default_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.schema_version = STORE_SCHEMA_VERSION
        self.ensure_schema()

    def _iso_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _coerce_int(self, value: Any, default: int = 0, minimum: int | None = None) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        if minimum is not None:
            return max(minimum, parsed)
        return parsed

    def _coerce_float(self, value: Any, default: float = 0.0, minimum: float | None = None) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        if minimum is not None:
            return max(minimum, parsed)
        return parsed

    def _ensure_string(self, value: Any) -> str:
        return str(value or "").strip()

    def _ensure_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return bool(default)
        if isinstance(value, (int, float)):
            return value != 0
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "on", "y"}:
            return True
        if normalized in {"false", "0", "no", "off", "n", ""}:
            return False
        return bool(default)

    def _sanitize_list_of_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _read_schema_meta(self) -> dict[str, Any]:
        data = self._read_json("schema_meta.json", {})
        return data if isinstance(data, dict) else {}

    def _write_schema_meta(self, payload: dict[str, Any]) -> None:
        normalized = dict(payload)
        normalized["schema_version"] = self._coerce_int(
            normalized.get("schema_version", 1),
            default=1,
            minimum=1,
        )
        normalized["updated_at"] = self._ensure_string(normalized.get("updated_at")) or self._iso_now()
        self._write_json("schema_meta.json", normalized)

    def ensure_schema(self) -> None:
        meta = self._read_schema_meta()
        try:
            version = int(meta.get("schema_version", 1))
        except (TypeError, ValueError):
            version = 1
        version = max(1, version)

        if version < 2:
            self._migrate_v1_to_v2(meta)
            version = 2

        if version < STORE_SCHEMA_VERSION:
            version = STORE_SCHEMA_VERSION

        now = self._iso_now()
        initialized_at = self._ensure_string(meta.get("initialized_at"))
        if not initialized_at:
            initialized_at = now
        self._write_schema_meta(
            {
                "schema_version": version,
                "initialized_at": initialized_at,
                "updated_at": now,
            }
        )
        self.schema_version = version

    def _migrate_v1_to_v2(self, existing_meta: dict[str, Any]) -> None:
        now = self._iso_now()
        migration_log = {
            "from_version": 1,
            "to_version": 2,
            "migrated_at": now,
            "notes": "Normalize legacy JSON payloads and seed run execution defaults.",
        }

        workflows = self._sanitize_workflows_v2(self._read_json("workflows.json", []))
        runs = self._sanitize_runs_v2(self._read_json("runs.json", []))
        settings = self._sanitize_settings_v2(self._read_json("settings.json", {}))
        integrations = self._sanitize_integrations_v2(self._read_json("integrations.json", []))
        bots = self._sanitize_bots_v2(self._read_json("bots.json", []))

        self._write_json("workflows.json", workflows)
        self._write_json("runs.json", runs)
        self._write_json("settings.json", settings)
        self._write_json("integrations.json", integrations)
        self._write_json("bots.json", bots)

        history = self._read_json("schema_migrations.json", [])
        migration_entries = history if isinstance(history, list) else []
        migration_entries.append(migration_log)
        self._write_json("schema_migrations.json", migration_entries)

        initialized_at = self._ensure_string(existing_meta.get("initialized_at")) or now
        self._write_schema_meta(
            {
                "schema_version": 2,
                "initialized_at": initialized_at,
                "updated_at": now,
                "last_migration": "v1_to_v2",
            }
        )

    def _sanitize_workflows_v2(self, payload: Any) -> list[dict[str, Any]]:
        workflows = self._sanitize_list_of_dicts(payload)
        normalized: list[dict[str, Any]] = []
        for item in workflows:
            entry = dict(item)
            entry["id"] = self._ensure_string(entry.get("id"))
            entry["name"] = self._ensure_string(entry.get("name"))
            if not entry["id"] or not entry["name"]:
                continue
            graph = entry.get("graph")
            entry["graph"] = graph if isinstance(graph, dict) else {}
            entry["description"] = self._ensure_string(entry.get("description"))
            entry["status"] = self._ensure_string(entry.get("status")) or "draft"
            tags = entry.get("tags")
            entry["tags"] = [str(tag).strip() for tag in tags] if isinstance(tags, list) else []
            entry["created_at"] = self._ensure_string(entry.get("created_at")) or self._iso_now()
            entry["updated_at"] = self._ensure_string(entry.get("updated_at")) or entry["created_at"]
            normalized.append(entry)
        return normalized

    def _sanitize_runs_v2(self, payload: Any) -> list[dict[str, Any]]:
        runs = self._sanitize_list_of_dicts(payload)
        normalized: list[dict[str, Any]] = []
        for item in runs:
            entry = dict(item)
            entry["id"] = self._ensure_string(entry.get("id"))
            entry["workflow_id"] = self._ensure_string(entry.get("workflow_id"))
            if not entry["id"] or not entry["workflow_id"]:
                continue
            entry["workflow_name"] = self._ensure_string(entry.get("workflow_name"))
            entry["status"] = self._ensure_string(entry.get("status")) or "queued"
            entry["trigger"] = self._ensure_string(entry.get("trigger")) or "manual"
            entry["log"] = self._ensure_string(entry.get("log"))
            entry["summary"] = self._ensure_string(entry.get("summary"))
            entry["finished_at"] = self._ensure_string(entry.get("finished_at"))
            node_results = entry.get("node_results")
            if not isinstance(node_results, list):
                node_results = entry.get("timeline")
            entry["node_results"] = self._sanitize_list_of_dicts(node_results)
            entry["attempt"] = self._coerce_int(entry.get("attempt"), default=1, minimum=1)
            entry["retry_count"] = self._coerce_int(entry.get("retry_count"), default=0, minimum=0)
            entry["replay_of_run_id"] = self._ensure_string(entry.get("replay_of_run_id"))
            entry["idempotency_key"] = self._ensure_string(entry.get("idempotency_key"))
            entry["cancellation_requested"] = self._ensure_bool(
                entry.get("cancellation_requested"),
                False,
            )
            entry["approval_required"] = self._ensure_bool(entry.get("approval_required"), False)
            entry["pending_approval_node_id"] = self._ensure_string(entry.get("pending_approval_node_id"))
            entry["pending_approval_node_name"] = self._ensure_string(entry.get("pending_approval_node_name"))
            entry["pending_approval_message"] = self._ensure_string(entry.get("pending_approval_message"))
            entry["pending_approval_requested_at"] = self._ensure_string(
                entry.get("pending_approval_requested_at")
            )
            entry["pending_approval_resumed_at"] = self._ensure_string(
                entry.get("pending_approval_resumed_at")
            )
            entry["last_failed_node_id"] = self._ensure_string(entry.get("last_failed_node_id"))
            entry["last_failed_node_name"] = self._ensure_string(entry.get("last_failed_node_name"))
            entry["execution_retry_max"] = self._coerce_int(
                entry.get("execution_retry_max"),
                default=0,
                minimum=0,
            )
            entry["execution_backoff_ms"] = self._coerce_int(
                entry.get("execution_backoff_ms"),
                default=0,
                minimum=0,
            )
            entry["execution_timeout_sec"] = self._coerce_float(
                entry.get("execution_timeout_sec"),
                default=0.0,
                minimum=0.0,
            )
            entry["created_at"] = self._ensure_string(entry.get("created_at")) or self._iso_now()
            entry["updated_at"] = self._ensure_string(entry.get("updated_at")) or entry["created_at"]
            normalized.append(entry)
        return normalized

    def _sanitize_settings_v2(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return dict(payload)

    def _sanitize_integrations_v2(self, payload: Any) -> list[dict[str, Any]]:
        items = self._sanitize_list_of_dicts(payload)
        normalized: list[dict[str, Any]] = []
        for item in items:
            profile = dict(item)
            profile["id"] = self._ensure_string(profile.get("id"))
            profile["key"] = self._ensure_string(profile.get("key")).lower()
            profile["name"] = self._ensure_string(profile.get("name"))
            if not profile["id"] or not profile["key"] or not profile["name"]:
                continue
            profile["description"] = self._ensure_string(profile.get("description"))
            config = profile.get("config")
            profile["config"] = config if isinstance(config, dict) else {}
            tags = profile.get("tags")
            profile["tags"] = [str(tag).strip() for tag in tags] if isinstance(tags, list) else []
            profile["enabled"] = self._ensure_bool(profile.get("enabled"), True)
            profile["last_test_status"] = self._ensure_string(profile.get("last_test_status"))
            profile["last_test_message"] = self._ensure_string(profile.get("last_test_message"))
            profile["last_tested_at"] = self._ensure_string(profile.get("last_tested_at"))
            profile["created_at"] = self._ensure_string(profile.get("created_at")) or self._iso_now()
            profile["updated_at"] = self._ensure_string(profile.get("updated_at")) or profile["created_at"]
            normalized.append(profile)
        return normalized

    def _sanitize_bots_v2(self, payload: Any) -> list[dict[str, Any]]:
        items = self._sanitize_list_of_dicts(payload)
        normalized: list[dict[str, Any]] = []
        for item in items:
            bot = dict(item)
            bot["id"] = self._ensure_string(bot.get("id"))
            bot["name"] = self._ensure_string(bot.get("name"))
            if not bot["id"] or not bot["name"]:
                continue
            bot["role"] = self._ensure_string(bot.get("role"))
            bot["provider"] = self._ensure_string(bot.get("provider")) or "local"
            bot["model"] = self._ensure_string(bot.get("model"))
            temperature = bot.get("temperature")
            bot["temperature"] = (
                self._coerce_float(temperature, default=0.2, minimum=0.0)
                if temperature is not None and str(temperature).strip() != ""
                else None
            )
            max_tokens = bot.get("max_tokens")
            bot["max_tokens"] = (
                self._coerce_int(max_tokens, default=1, minimum=1)
                if max_tokens is not None and str(max_tokens).strip() != ""
                else None
            )
            bot["system_prompt"] = self._ensure_string(bot.get("system_prompt"))
            bot["enabled"] = self._ensure_bool(bot.get("enabled"), True)
            tags = bot.get("tags")
            bot["tags"] = [str(tag).strip() for tag in tags] if isinstance(tags, list) else []
            bot["last_test_status"] = self._ensure_string(bot.get("last_test_status"))
            bot["last_test_message"] = self._ensure_string(bot.get("last_test_message"))
            bot["last_test_output"] = self._ensure_string(bot.get("last_test_output"))
            bot["last_tested_at"] = self._ensure_string(bot.get("last_tested_at"))
            bot["created_at"] = self._ensure_string(bot.get("created_at")) or self._iso_now()
            bot["updated_at"] = self._ensure_string(bot.get("updated_at")) or bot["created_at"]
            normalized.append(bot)
        return normalized

    def _read_json(self, file_name: str, fallback: Any) -> Any:
        file_path = self.data_dir / file_name
        return self._read_json_path(file_path, fallback)

    def _read_json_path(self, file_path: Path, fallback: Any) -> Any:
        with self._lock:
            if not file_path.exists():
                return fallback
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                return data
            except Exception:
                return fallback

    def _write_json(self, file_name: str, payload: Any) -> None:
        file_path = self.data_dir / file_name
        self._write_json_path(file_path, payload)

    def _write_json_path(self, file_path: Path, payload: Any) -> None:
        tmp_path = file_path.with_suffix(".tmp")
        with self._lock:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
            os.replace(tmp_path, file_path)
            try:
                os.chmod(file_path, 0o600)
            except OSError:
                pass

    def default_backup_path(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return self.data_dir / f"backup-{timestamp}.json"

    def export_backup(
        self,
        destination_path: str | Path | None = None,
    ) -> tuple[Path, dict[str, int]]:
        export_path = (
            Path(destination_path).expanduser()
            if destination_path
            else self.default_backup_path()
        )
        workflows = self.load_workflows()
        runs = self.load_runs()
        integrations = self.load_integrations()
        bots = self.load_bots()
        settings = self.load_settings({})
        schema_meta = self._read_schema_meta()
        schema_migrations = self._read_json("schema_migrations.json", [])
        if not isinstance(schema_migrations, list):
            schema_migrations = []

        counts = {
            "workflows": len(workflows),
            "runs": len(runs),
            "integrations": len(integrations),
            "bots": len(bots),
            "schema_migrations": len(schema_migrations),
        }
        payload = {
            "format": "6x-protocol.backup.v1",
            "exported_at": self._iso_now(),
            "schema_version": int(self.schema_version),
            "counts": counts,
            "data": {
                "workflows": workflows,
                "runs": runs,
                "settings": settings if isinstance(settings, dict) else {},
                "integrations": integrations,
                "bots": bots,
                "schema_meta": schema_meta if isinstance(schema_meta, dict) else {},
                "schema_migrations": schema_migrations,
            },
        }
        self._write_json_path(export_path, payload)
        return export_path, counts

    def restore_backup(
        self,
        source_path: str | Path,
        *,
        merge: bool = False,
    ) -> dict[str, int]:
        import_path = Path(source_path).expanduser()
        if not import_path.exists():
            raise FileNotFoundError(f"Backup bundle not found: {import_path}")

        raw = self._read_json_path(import_path, None)
        if raw is None or not isinstance(raw, dict):
            raise ValueError("Invalid backup payload.")

        data = raw.get("data")
        if not isinstance(data, dict):
            # Backwards-compatible fallback if data was written at root.
            data = raw

        incoming_workflows = self._sanitize_workflows_v2(data.get("workflows", []))
        incoming_runs = self._sanitize_runs_v2(data.get("runs", []))
        incoming_integrations = self._sanitize_integrations_v2(data.get("integrations", []))
        incoming_bots = self._sanitize_bots_v2(data.get("bots", []))
        incoming_settings = data.get("settings", {})
        if not isinstance(incoming_settings, dict):
            incoming_settings = {}
        incoming_schema_meta = data.get("schema_meta", {})
        if not isinstance(incoming_schema_meta, dict):
            incoming_schema_meta = {}
        incoming_schema_migrations = data.get("schema_migrations", [])
        if not isinstance(incoming_schema_migrations, list):
            incoming_schema_migrations = []

        if merge:
            workflows = self._merge_records_by_id(self.load_workflows(), incoming_workflows)
            runs = self._merge_records_by_id(self.load_runs(), incoming_runs)
            integrations = self._merge_records_by_id(self.load_integrations(), incoming_integrations)
            bots = self._merge_records_by_id(self.load_bots(), incoming_bots)
            settings = self.load_settings({})
            settings.update(incoming_settings)
        else:
            workflows = incoming_workflows
            runs = incoming_runs
            integrations = incoming_integrations
            bots = incoming_bots
            settings = incoming_settings

        self.save_workflows(workflows)
        self.save_runs(runs)
        self.save_integrations(integrations)
        self.save_bots(bots)
        self.save_settings(settings if isinstance(settings, dict) else {})

        if incoming_schema_meta:
            self._write_schema_meta(incoming_schema_meta)
        if incoming_schema_migrations:
            self._write_json("schema_migrations.json", incoming_schema_migrations)

        # Ensure imported schema artifacts are valid for the active store version.
        self.ensure_schema()
        return {
            "workflows": len(workflows),
            "runs": len(runs),
            "integrations": len(integrations),
            "bots": len(bots),
        }

    def _merge_records_by_id(
        self,
        existing: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in existing:
            item_id = self._ensure_string(item.get("id"))
            if not item_id:
                continue
            merged[item_id] = dict(item)
            order.append(item_id)
        for item in incoming:
            item_id = self._ensure_string(item.get("id"))
            if not item_id:
                continue
            if item_id not in merged:
                order.append(item_id)
            merged[item_id] = dict(item)
        return [merged[item_id] for item_id in order if item_id in merged]

    def load_workflows(self) -> list[dict[str, Any]]:
        data = self._read_json("workflows.json", [])
        return self._sanitize_workflows_v2(data)

    def save_workflows(self, workflows: list[dict[str, Any]]) -> None:
        self._write_json("workflows.json", workflows)

    def load_runs(self) -> list[dict[str, Any]]:
        data = self._read_json("runs.json", [])
        return self._sanitize_runs_v2(data)

    def save_runs(self, runs: list[dict[str, Any]]) -> None:
        self._write_json("runs.json", runs)

    def load_settings(self, defaults: dict[str, Any]) -> dict[str, Any]:
        data = self._read_json("settings.json", defaults)
        if not isinstance(data, dict):
            return dict(defaults)
        merged = dict(defaults)
        merged.update(data)
        return merged

    def save_settings(self, settings: dict[str, Any]) -> None:
        self._write_json("settings.json", settings)

    def load_integrations(self) -> list[dict[str, Any]]:
        data = self._read_json("integrations.json", [])
        return self._sanitize_integrations_v2(data)

    def save_integrations(self, integrations: list[dict[str, Any]]) -> None:
        self._write_json("integrations.json", integrations)

    def default_integration_bundle_path(self) -> Path:
        return self.data_dir / "integration-profiles-bundle.json"

    def export_integrations(
        self,
        destination_path: str | Path | None = None,
    ) -> tuple[Path, int]:
        export_path = (
            Path(destination_path).expanduser()
            if destination_path
            else self.default_integration_bundle_path()
        )
        profiles = [self._sanitize_integration_profile(item) for item in self.load_integrations()]
        payload = {
            "format": "6x-protocol.integration-profiles.v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "profile_count": len(profiles),
            "profiles": profiles,
        }
        self._write_json_path(export_path, payload)
        return export_path, len(profiles)

    def import_integrations(
        self,
        source_path: str | Path,
        *,
        merge: bool = True,
    ) -> tuple[int, int]:
        import_path = Path(source_path).expanduser()
        if not import_path.exists():
            raise FileNotFoundError(f"Integration profile bundle not found: {import_path}")

        raw = self._read_json_path(import_path, None)
        if raw is None:
            raise ValueError("Invalid integration profile bundle payload.")

        imported_profiles = self._normalize_imported_profiles(raw)
        if merge:
            current = [self._sanitize_integration_profile(item) for item in self.load_integrations()]
            by_id: dict[str, dict[str, Any]] = {}
            ordered_ids: list[str] = []
            for item in current:
                item_id = str(item.get("id", "")).strip()
                if not item_id:
                    continue
                by_id[item_id] = item
                ordered_ids.append(item_id)
            for item in imported_profiles:
                item_id = str(item.get("id", "")).strip()
                if not item_id:
                    continue
                if item_id not in by_id:
                    ordered_ids.append(item_id)
                by_id[item_id] = item
            merged_profiles = [by_id[item_id] for item_id in ordered_ids if item_id in by_id]
            self.save_integrations(merged_profiles)
            return len(imported_profiles), len(merged_profiles)

        self.save_integrations(imported_profiles)
        return len(imported_profiles), len(imported_profiles)

    def _normalize_imported_profiles(self, raw: Any) -> list[dict[str, Any]]:
        profiles_raw: Any = raw
        if isinstance(raw, dict):
            profiles_raw = raw.get("profiles")
        if not isinstance(profiles_raw, list):
            raise ValueError("Invalid integration profile bundle format.")

        normalized: list[dict[str, Any]] = []
        for item in profiles_raw:
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("id", "")).strip()
            key = str(item.get("key", "")).strip().lower()
            name = str(item.get("name", "")).strip()
            if not profile_id or not key or not name:
                continue
            normalized.append(self._sanitize_integration_profile(item))
        return normalized

    def _sanitize_integration_profile(self, item: dict[str, Any]) -> dict[str, Any]:
        profile = dict(item)
        profile["id"] = str(profile.get("id", "")).strip()
        profile["key"] = str(profile.get("key", "")).strip().lower()
        profile["name"] = str(profile.get("name", "")).strip()
        profile["description"] = str(profile.get("description", "")).strip()
        profile["enabled"] = bool(profile.get("enabled", True))
        config = profile.get("config")
        profile["config"] = config if isinstance(config, dict) else {}
        tags = profile.get("tags")
        profile["tags"] = [str(tag).strip() for tag in tags] if isinstance(tags, list) else []
        for field in (
            "last_test_status",
            "last_test_message",
            "last_tested_at",
            "created_at",
            "updated_at",
        ):
            profile[field] = str(profile.get(field, "")).strip()
        return profile

    def load_bots(self) -> list[dict[str, Any]]:
        data = self._read_json("bots.json", [])
        return self._sanitize_bots_v2(data)

    def save_bots(self, bots: list[dict[str, Any]]) -> None:
        self._write_json("bots.json", bots)
