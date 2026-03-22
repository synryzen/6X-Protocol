"""Simple JSON storage layer for the web-edition API scaffold.

This intentionally uses JSON files for fast iteration. The schema is stable enough
that we can later swap this for Postgres repositories behind the same interface.
"""

from __future__ import annotations

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
        tmp_path = file_path.with_suffix(".tmp")
        with self._lock:
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

    def load_bots(self) -> list[dict[str, Any]]:
        data = self._read_json("bots.json", [])
        return data if isinstance(data, list) else []

    def save_bots(self, bots: list[dict[str, Any]]) -> None:
        self._write_json("bots.json", bots)
