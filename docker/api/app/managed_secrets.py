"""Managed secret adapter baseline for env/file-backed secret resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SECRET_REF_PREFIX = "secret://"


def _normalize_ref(value: str) -> str:
    return str(value or "").strip()


def is_secret_reference(value: Any) -> bool:
    text = _normalize_ref(str(value or ""))
    if not text:
        return False
    lowered = text.lower()
    return lowered.startswith(SECRET_REF_PREFIX) or lowered.startswith("env:") or lowered.startswith("file:")


def parse_secret_reference(value: str) -> tuple[str, str] | None:
    text = _normalize_ref(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("env:"):
        key = text.split(":", 1)[1].strip()
        return ("env", key) if key else None
    if lowered.startswith("file:"):
        key = text.split(":", 1)[1].strip()
        return ("file", key) if key else None
    if lowered.startswith(SECRET_REF_PREFIX):
        remainder = text[len(SECRET_REF_PREFIX) :].strip()
        if "/" not in remainder:
            return None
        provider, key = remainder.split("/", 1)
        provider = provider.strip().lower()
        key = key.strip()
        if provider in {"env", "file"} and key:
            return provider, key
    return None


class ManagedSecretResolver:
    """Resolve reference values from supported secret adapters."""

    def __init__(
        self,
        *,
        mode: str = "disabled",
        file_path: str = "",
        env_prefix: str = "",
    ) -> None:
        normalized_mode = str(mode or "disabled").strip().lower()
        if normalized_mode not in {"disabled", "env", "file", "chain"}:
            normalized_mode = "disabled"
        self.mode = normalized_mode
        self.file_path = str(file_path or "").strip()
        self.env_prefix = str(env_prefix or "").strip()
        self._file_cache: dict[str, Any] | None = None
        self._file_loaded = False

    @classmethod
    def from_env(cls) -> "ManagedSecretResolver":
        return cls(
            mode=str(os.getenv("SECRET_PROVIDER_MODE", "disabled") or "disabled"),
            file_path=str(os.getenv("SECRET_PROVIDER_FILE", "") or ""),
            env_prefix=str(os.getenv("SECRET_PROVIDER_ENV_PREFIX", "") or ""),
        )

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def file_loaded(self) -> bool:
        return self._file_loaded

    def _load_file_secrets(self) -> dict[str, Any]:
        if self._file_cache is not None:
            return self._file_cache
        if not self.file_path:
            self._file_cache = {}
            self._file_loaded = False
            return self._file_cache
        path = Path(self.file_path).expanduser()
        if not path.exists():
            self._file_cache = {}
            self._file_loaded = False
            return self._file_cache
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._file_cache = raw if isinstance(raw, dict) else {}
            self._file_loaded = True
        except Exception:
            self._file_cache = {}
            self._file_loaded = False
        return self._file_cache

    def _resolve_from_env(self, key: str) -> str | None:
        target = str(key or "").strip()
        if not target:
            return None
        direct = os.getenv(target)
        if direct is not None and str(direct).strip():
            return str(direct)
        if self.env_prefix:
            prefixed = os.getenv(f"{self.env_prefix}{target}")
            if prefixed is not None and str(prefixed).strip():
                return str(prefixed)
        return None

    def _resolve_from_file(self, key_path: str) -> str | None:
        key = str(key_path or "").strip()
        if not key:
            return None
        current: Any = self._load_file_secrets()
        for part in key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if current is None:
            return None
        resolved = str(current).strip()
        return resolved or None

    def resolve_reference(self, reference: str) -> str | None:
        parsed = parse_secret_reference(reference)
        if parsed is None:
            return None
        provider, key = parsed

        if self.mode == "disabled":
            return None
        if self.mode == "env":
            return self._resolve_from_env(key) if provider == "env" else None
        if self.mode == "file":
            return self._resolve_from_file(key) if provider == "file" else None
        # chain mode
        if provider == "env":
            return self._resolve_from_env(key)
        if provider == "file":
            return self._resolve_from_file(key)
        return None

    def resolve_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(settings, dict):
            return {}
        resolved = dict(settings)
        secret_key_fields = (
            "local_ai_api_key",
            "openai_api_key",
            "anthropic_api_key",
        )
        for field in secret_key_fields:
            ref_field = f"{field}_ref"
            if ref_field in resolved and str(resolved.get(ref_field, "")).strip():
                secret = self.resolve_reference(str(resolved.get(ref_field, "")).strip())
                if secret is not None:
                    resolved[field] = secret
                continue
            current_value = str(resolved.get(field, "")).strip()
            if is_secret_reference(current_value):
                secret = self.resolve_reference(current_value)
                if secret is not None:
                    resolved[field] = secret
        return resolved

    def resolve_integration_profiles(
        self,
        profiles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(profiles, list):
            return []
        resolved: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            item = dict(profile)
            config = item.get("config")
            if isinstance(config, dict):
                item["config"] = self._resolve_mapping(config)
            resolved.append(item)
        return resolved

    def _resolve_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, dict):
                resolved[str(key)] = self._resolve_mapping(value)
            elif isinstance(value, list):
                resolved[str(key)] = self._resolve_list(value)
            elif isinstance(value, str) and is_secret_reference(value):
                secret = self.resolve_reference(value)
                resolved[str(key)] = secret if secret is not None else value
            else:
                resolved[str(key)] = value
        return resolved

    def _resolve_list(self, payload: list[Any]) -> list[Any]:
        values: list[Any] = []
        for item in payload:
            if isinstance(item, dict):
                values.append(self._resolve_mapping(item))
            elif isinstance(item, list):
                values.append(self._resolve_list(item))
            elif isinstance(item, str) and is_secret_reference(item):
                secret = self.resolve_reference(item)
                values.append(secret if secret is not None else item)
            else:
                values.append(item)
        return values
