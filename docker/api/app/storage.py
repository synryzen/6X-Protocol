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

from app.secret_manager import SecretManager

MIN_STORE_SCHEMA_VERSION = 1
STORE_SCHEMA_VERSION = 3


class JsonStore:
    def __init__(self, data_dir: str | None = None) -> None:
        default_dir = Path("/data/6x-protocol")
        self.data_dir = Path(data_dir or os.getenv("SCAFFOLD_DATA_DIR") or default_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.secrets = SecretManager(str(os.getenv("SECRET_ENCRYPTION_KEY", "") or ""))
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
            normalized.get("schema_version", MIN_STORE_SCHEMA_VERSION),
            default=MIN_STORE_SCHEMA_VERSION,
            minimum=MIN_STORE_SCHEMA_VERSION,
        )
        normalized["updated_at"] = self._ensure_string(normalized.get("updated_at")) or self._iso_now()
        self._write_json("schema_meta.json", normalized)

    def _read_schema_version(self, meta: dict[str, Any]) -> int:
        return self._coerce_int(
            meta.get("schema_version", MIN_STORE_SCHEMA_VERSION),
            default=MIN_STORE_SCHEMA_VERSION,
            minimum=MIN_STORE_SCHEMA_VERSION,
        )

    def _append_migration_history(self, migration_log: dict[str, Any]) -> None:
        history = self._read_json("schema_migrations.json", [])
        migration_entries = history if isinstance(history, list) else []
        migration_entries.append(migration_log)
        self._write_json("schema_migrations.json", migration_entries)

    def _capture_migration_snapshot(self, from_version: int, to_version: int) -> Path:
        snapshot_dir = self.data_dir / "migration_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_name = (
            f"schema-v{from_version}-to-v{to_version}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        snapshot_path = snapshot_dir / snapshot_name
        files = [
            "workflows.json",
            "runs.json",
            "settings.json",
            "integrations.json",
            "bots.json",
            "schema_meta.json",
            "schema_migrations.json",
        ]
        payload: dict[str, Any] = {
            "captured_at": self._iso_now(),
            "from_version": int(from_version),
            "to_version": int(to_version),
            "files": {},
        }
        for file_name in files:
            file_path = self.data_dir / file_name
            if not file_path.exists():
                continue
            payload["files"][file_name] = self._read_json(file_name, None)
        self._write_json_path(snapshot_path, payload)
        return snapshot_path

    def ensure_schema(self) -> None:
        meta = self._read_schema_meta()
        version = self._read_schema_version(meta)
        if version > STORE_SCHEMA_VERSION:
            raise RuntimeError(
                "Stored data schema version is newer than this server build "
                f"(data=v{version}, supported<=v{STORE_SCHEMA_VERSION}). "
                "Upgrade server image before using this data directory."
            )

        migration_steps = {
            1: self._migrate_v1_to_v2,
            2: self._migrate_v2_to_v3,
        }
        while version < STORE_SCHEMA_VERSION:
            migrate = migration_steps.get(version)
            if migrate is None:
                raise RuntimeError(
                    f"No migration path available from schema v{version} "
                    f"to v{STORE_SCHEMA_VERSION}."
                )
            target_version = version + 1
            snapshot = self._capture_migration_snapshot(version, target_version)
            migrate(meta)
            meta = self._read_schema_meta()
            migrated_version = self._read_schema_version(meta)
            if migrated_version < target_version:
                raise RuntimeError(
                    f"Migration to schema v{target_version} did not complete "
                    f"(current=v{migrated_version})."
                )
            version = migrated_version
            meta["last_snapshot_path"] = str(snapshot)

        now = self._iso_now()
        initialized_at = self._ensure_string(meta.get("initialized_at"))
        if not initialized_at:
            initialized_at = now
        self._write_schema_meta(
            {
                "schema_version": version,
                "initialized_at": initialized_at,
                "last_migration": self._ensure_string(meta.get("last_migration")),
                "last_snapshot_path": self._ensure_string(meta.get("last_snapshot_path")),
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

        self._append_migration_history(migration_log)

        initialized_at = self._ensure_string(existing_meta.get("initialized_at")) or now
        self._write_schema_meta(
            {
                "schema_version": 2,
                "initialized_at": initialized_at,
                "updated_at": now,
                "last_migration": "v1_to_v2",
            }
        )

    def _migrate_v2_to_v3(self, existing_meta: dict[str, Any]) -> None:
        now = self._iso_now()
        migration_log = {
            "from_version": 2,
            "to_version": 3,
            "migrated_at": now,
            "notes": (
                "Enforce graph schema boundaries and timeline parity fields for safer data evolution."
            ),
        }

        workflows = self._sanitize_workflows_v3(self._read_json("workflows.json", []))
        runs = self._sanitize_runs_v3(self._read_json("runs.json", []))
        settings = self._sanitize_settings_v3(self._read_json("settings.json", {}))
        integrations = self._sanitize_integrations_v2(self._read_json("integrations.json", []))
        bots = self._sanitize_bots_v2(self._read_json("bots.json", []))

        self._write_json("workflows.json", workflows)
        self._write_json("runs.json", runs)
        self._write_json("settings.json", settings)
        self._write_json("integrations.json", integrations)
        self._write_json("bots.json", bots)

        self._append_migration_history(migration_log)

        initialized_at = self._ensure_string(existing_meta.get("initialized_at")) or now
        self._write_schema_meta(
            {
                "schema_version": 3,
                "initialized_at": initialized_at,
                "updated_at": now,
                "last_migration": "v2_to_v3",
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

    def _sanitize_graph_nodes_v3(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            return []
        nodes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            node = dict(item)
            node_id = self._ensure_string(node.get("id")) or f"node_{index + 1}"
            if node_id in seen:
                continue
            seen.add(node_id)
            node_type = self._ensure_string(node.get("type")).lower() or "action"
            if node_type not in {"trigger", "action", "ai", "condition"}:
                node_type = "action"
            config = node.get("config")
            metadata = node.get("metadata")
            position = node.get("position")
            x_candidate = node.get("x")
            y_candidate = node.get("y")
            if isinstance(position, dict):
                x_candidate = position.get("x", x_candidate)
                y_candidate = position.get("y", y_candidate)
            x = int(round(self._coerce_float(x_candidate, default=80.0)))
            y = int(round(self._coerce_float(y_candidate, default=80.0)))
            width = int(round(self._coerce_float(node.get("width"), default=220.0, minimum=120.0)))
            height = int(round(self._coerce_float(node.get("height"), default=120.0, minimum=80.0)))
            normalized = dict(node)
            normalized["id"] = node_id
            normalized["name"] = self._ensure_string(node.get("name")) or f"{node_type.title()} Node"
            normalized["type"] = node_type
            normalized["x"] = x
            normalized["y"] = y
            normalized["position"] = {"x": x, "y": y}
            normalized["width"] = width
            normalized["height"] = height
            normalized["config"] = config if isinstance(config, dict) else {}
            normalized["metadata"] = metadata if isinstance(metadata, dict) else {}
            nodes.append(normalized)
        return nodes

    def _sanitize_graph_edges_v3(
        self,
        payload: Any,
        node_ids: set[str],
    ) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            return []
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            edge = dict(item)
            source = self._ensure_string(edge.get("source"))
            target = self._ensure_string(edge.get("target"))
            if not source or not target or source not in node_ids or target not in node_ids:
                continue
            edge_type = self._ensure_string(edge.get("type")).lower() or "next"
            condition = self._ensure_string(edge.get("condition")).lower() or edge_type
            key = (source, target, edge_type)
            if key in seen:
                continue
            seen.add(key)
            normalized = dict(edge)
            normalized["id"] = self._ensure_string(edge.get("id")) or f"edge_{index + 1}"
            normalized["source"] = source
            normalized["target"] = target
            normalized["source_node_id"] = source
            normalized["target_node_id"] = target
            normalized["type"] = edge_type
            normalized["condition"] = condition
            normalized["link_type"] = condition
            normalized["label"] = self._ensure_string(edge.get("label"))
            edges.append(normalized)
        return edges

    def _normalize_graph_v3(self, payload: Any) -> dict[str, Any]:
        graph = dict(payload) if isinstance(payload, dict) else {}
        node_payload = graph.get("nodes")
        edge_payload = graph.get("edges")
        if not isinstance(edge_payload, list):
            edge_payload = graph.get("links")
        nodes = self._sanitize_graph_nodes_v3(node_payload)
        node_ids = {str(item.get("id", "")) for item in nodes if str(item.get("id", "")).strip()}
        edges = self._sanitize_graph_edges_v3(edge_payload, node_ids)
        viewport = graph.get("viewport")
        if not isinstance(viewport, dict):
            viewport = {}
        entry_node_id = self._ensure_string(graph.get("entry_node_id"))
        if entry_node_id not in node_ids:
            entry_node_id = nodes[0]["id"] if nodes else ""

        normalized = dict(graph)
        normalized["schema_version"] = 3
        normalized["nodes"] = nodes
        normalized["edges"] = edges
        # Keep links mirrored for compatibility with legacy editor/runtime consumers.
        normalized["links"] = [dict(edge) for edge in edges]
        normalized["entry_node_id"] = entry_node_id
        normalized["viewport"] = {
            "x": self._coerce_float(viewport.get("x"), default=0.0),
            "y": self._coerce_float(viewport.get("y"), default=0.0),
            "zoom": self._coerce_float(viewport.get("zoom"), default=1.0, minimum=0.05),
        }
        return normalized

    def _sanitize_workflows_v3(self, payload: Any) -> list[dict[str, Any]]:
        workflows = self._sanitize_workflows_v2(payload)
        normalized: list[dict[str, Any]] = []
        for item in workflows:
            entry = dict(item)
            entry["graph"] = self._normalize_graph_v3(entry.get("graph"))
            execution_defaults = entry.get("execution_defaults")
            if not isinstance(execution_defaults, dict):
                execution_defaults = {}
            entry["execution_defaults"] = {
                "retry_max": self._coerce_int(execution_defaults.get("retry_max"), default=0, minimum=0),
                "retry_backoff_ms": self._coerce_int(
                    execution_defaults.get("retry_backoff_ms"),
                    default=0,
                    minimum=0,
                ),
                "timeout_sec": self._coerce_float(
                    execution_defaults.get("timeout_sec"),
                    default=0.0,
                    minimum=0.0,
                ),
            }
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

    def _sanitize_runs_v3(self, payload: Any) -> list[dict[str, Any]]:
        runs = self._sanitize_runs_v2(payload)
        normalized: list[dict[str, Any]] = []
        for item in runs:
            entry = dict(item)
            timeline = entry.get("timeline")
            if not isinstance(timeline, list):
                timeline = entry.get("node_results", [])
            node_results = self._sanitize_list_of_dicts(timeline)
            entry["node_results"] = node_results
            entry["timeline"] = node_results
            if not self._ensure_string(entry.get("finished_at")) and str(entry.get("status", "")).lower() in {
                "success",
                "failed",
                "cancelled",
            }:
                entry["finished_at"] = self._ensure_string(entry.get("updated_at")) or self._iso_now()
            normalized.append(entry)
        return normalized

    def _sanitize_settings_v2(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return dict(payload)

    def _sanitize_settings_v3(self, payload: Any) -> dict[str, Any]:
        settings = self._sanitize_settings_v2(payload)
        if "canvas_minimap_x" in settings:
            settings["canvas_minimap_x"] = self._coerce_int(settings.get("canvas_minimap_x"), default=0)
        if "canvas_minimap_y" in settings:
            settings["canvas_minimap_y"] = self._coerce_int(settings.get("canvas_minimap_y"), default=0)
        if "reduce_motion" in settings:
            settings["reduce_motion"] = self._ensure_bool(settings.get("reduce_motion"), False)
        if "local_ai_enabled" in settings:
            settings["local_ai_enabled"] = self._ensure_bool(settings.get("local_ai_enabled"), True)
        return settings

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

        incoming_workflows = self._sanitize_workflows_v3(data.get("workflows", []))
        incoming_runs = self._sanitize_runs_v3(data.get("runs", []))
        incoming_integrations = self._sanitize_integrations_v2(data.get("integrations", []))
        incoming_bots = self._sanitize_bots_v2(data.get("bots", []))
        incoming_settings = self._sanitize_settings_v3(data.get("settings", {}))
        incoming_schema_meta = data.get("schema_meta", {})
        if not isinstance(incoming_schema_meta, dict):
            incoming_schema_meta = {}
        incoming_schema_migrations = data.get("schema_migrations", [])
        if not isinstance(incoming_schema_migrations, list):
            incoming_schema_migrations = []
        format_name = self._ensure_string(raw.get("format")) or "6x-protocol.backup.v1"
        if format_name not in {"6x-protocol.backup.v1"}:
            raise ValueError(f"Unsupported backup format: {format_name}")
        backup_schema_version = self._coerce_int(
            raw.get("schema_version", incoming_schema_meta.get("schema_version", self.schema_version)),
            default=self.schema_version,
            minimum=MIN_STORE_SCHEMA_VERSION,
        )
        if backup_schema_version > STORE_SCHEMA_VERSION:
            raise ValueError(
                "Backup schema is newer than this server build "
                f"(backup=v{backup_schema_version}, supported<=v{STORE_SCHEMA_VERSION})."
            )

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

    def rotate_secret_encryption(self, new_key_material: str) -> dict[str, int]:
        new_key = str(new_key_material or "").strip()
        if not new_key:
            raise ValueError("new_key_material is required")

        settings = self.load_settings({})
        integrations = self.load_integrations()
        if SecretManager.contains_encrypted_payload(settings) or SecretManager.contains_encrypted_payload(
            integrations
        ):
            raise ValueError(
                "Cannot rotate secrets: existing encrypted values could not be decrypted with current key."
            )

        self.secrets = SecretManager(new_key)
        self.save_settings(settings)
        self.save_integrations(integrations)
        return {
            "settings": 1,
            "integration_profiles": len(integrations),
        }

    def load_workflows(self) -> list[dict[str, Any]]:
        data = self._read_json("workflows.json", [])
        return self._sanitize_workflows_v3(data)

    def save_workflows(self, workflows: list[dict[str, Any]]) -> None:
        self._write_json("workflows.json", self._sanitize_workflows_v3(workflows))

    def load_runs(self) -> list[dict[str, Any]]:
        data = self._read_json("runs.json", [])
        return self._sanitize_runs_v3(data)

    def save_runs(self, runs: list[dict[str, Any]]) -> None:
        self._write_json("runs.json", self._sanitize_runs_v3(runs))

    def load_settings(self, defaults: dict[str, Any]) -> dict[str, Any]:
        data = self._read_json("settings.json", defaults)
        if not isinstance(data, dict):
            return dict(defaults)
        data = self._sanitize_settings_v3(self.secrets.decrypt_settings(data))
        merged = dict(defaults)
        merged.update(data)
        return merged

    def save_settings(self, settings: dict[str, Any]) -> None:
        encrypted = self.secrets.encrypt_settings(
            self._sanitize_settings_v3(settings if isinstance(settings, dict) else {})
        )
        self._write_json("settings.json", encrypted)

    def load_integrations(self) -> list[dict[str, Any]]:
        data = self._read_json("integrations.json", [])
        sanitized = self._sanitize_integrations_v2(data)
        return self.secrets.decrypt_integration_profiles(sanitized)

    def save_integrations(self, integrations: list[dict[str, Any]]) -> None:
        sanitized = self._sanitize_integrations_v2(integrations)
        encrypted = self.secrets.encrypt_integration_profiles(sanitized)
        self._write_json("integrations.json", encrypted)

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
