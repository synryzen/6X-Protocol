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


class JsonStore:
    def __init__(self, data_dir: str | None = None) -> None:
        default_dir = Path("/data/6x-protocol")
        self.data_dir = Path(data_dir or os.getenv("SCAFFOLD_DATA_DIR") or default_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

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

    def load_workflows(self) -> list[dict[str, Any]]:
        data = self._read_json("workflows.json", [])
        return data if isinstance(data, list) else []

    def save_workflows(self, workflows: list[dict[str, Any]]) -> None:
        self._write_json("workflows.json", workflows)

    def load_runs(self) -> list[dict[str, Any]]:
        data = self._read_json("runs.json", [])
        return data if isinstance(data, list) else []

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
        return data if isinstance(data, list) else []

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
        return data if isinstance(data, list) else []

    def save_bots(self, bots: list[dict[str, Any]]) -> None:
        self._write_json("bots.json", bots)
