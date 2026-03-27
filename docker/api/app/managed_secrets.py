"""Managed secret adapter baseline for env/file/http/vault secret resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Any

SECRET_REF_PREFIX = "secret://"
SUPPORTED_SECRET_PROVIDERS = ("env", "file", "http", "vault")


def _normalize_ref(value: str) -> str:
    return str(value or "").strip()


def is_secret_reference(value: Any) -> bool:
    text = _normalize_ref(str(value or ""))
    if not text:
        return False
    lowered = text.lower()
    return (
        lowered.startswith(SECRET_REF_PREFIX)
        or lowered.startswith("env:")
        or lowered.startswith("file:")
        or lowered.startswith("http:")
        or lowered.startswith("vault:")
        or lowered.startswith("chain:")
    )


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
    if lowered.startswith("http:"):
        key = text.split(":", 1)[1].strip()
        return ("http", key) if key else None
    if lowered.startswith("vault:"):
        key = text.split(":", 1)[1].strip()
        return ("vault", key) if key else None
    if lowered.startswith("chain:"):
        key = text.split(":", 1)[1].strip()
        return ("chain", key) if key else None
    if lowered.startswith(SECRET_REF_PREFIX):
        remainder = text[len(SECRET_REF_PREFIX) :].strip()
        if not remainder:
            return None
        if "/" not in remainder:
            return ("chain", remainder)
        provider, key = remainder.split("/", 1)
        provider = provider.strip().lower()
        key = key.strip()
        if provider in {*(SUPPORTED_SECRET_PROVIDERS), "chain"} and key:
            return provider, key
    return None


def _parse_chain_order(value: str) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return SUPPORTED_SECRET_PROVIDERS
    items = [item.strip().lower() for item in raw.split(",")]
    deduped: list[str] = []
    for item in items:
        if item in SUPPORTED_SECRET_PROVIDERS and item not in deduped:
            deduped.append(item)
    return tuple(deduped) if deduped else SUPPORTED_SECRET_PROVIDERS


class ManagedSecretResolver:
    """Resolve reference values from supported secret adapters."""

    def __init__(
        self,
        *,
        mode: str = "disabled",
        file_path: str = "",
        env_prefix: str = "",
        http_url: str = "",
        http_auth_token: str = "",
        http_timeout_sec: float = 3.0,
        http_allow_insecure: bool = False,
        vault_url: str = "",
        vault_auth_token: str = "",
        vault_timeout_sec: float = 3.0,
        vault_allow_insecure: bool = False,
        chain_order: str = "",
    ) -> None:
        normalized_mode = str(mode or "disabled").strip().lower()
        if normalized_mode not in {"disabled", "env", "file", "http", "vault", "chain"}:
            normalized_mode = "disabled"
        self.mode = normalized_mode
        self.file_path = str(file_path or "").strip()
        self.env_prefix = str(env_prefix or "").strip()
        self.http_url = str(http_url or "").strip()
        self.http_auth_token = str(http_auth_token or "").strip()
        try:
            self.http_timeout_sec = max(0.5, float(http_timeout_sec))
        except (TypeError, ValueError):
            self.http_timeout_sec = 3.0
        self.http_allow_insecure = bool(http_allow_insecure)
        self.vault_url = str(vault_url or "").strip()
        self.vault_auth_token = str(vault_auth_token or "").strip()
        try:
            self.vault_timeout_sec = max(0.5, float(vault_timeout_sec))
        except (TypeError, ValueError):
            self.vault_timeout_sec = 3.0
        self.vault_allow_insecure = bool(vault_allow_insecure)
        self._chain_order = _parse_chain_order(chain_order)
        self._file_cache: dict[str, Any] | None = None
        self._file_loaded = False
        self._file_error = ""
        self._http_cache: dict[str, Any] | None = None
        self._http_loaded = False
        self._http_error = ""
        self._vault_cache: dict[str, Any] | None = None
        self._vault_loaded = False
        self._vault_error = ""
        self._env_error = ""

    @classmethod
    def from_env(cls) -> "ManagedSecretResolver":
        allow_insecure_raw = str(
            os.getenv("SECRET_PROVIDER_HTTP_ALLOW_INSECURE", "false") or "false"
        ).strip().lower()
        vault_allow_insecure_raw = str(
            os.getenv("SECRET_PROVIDER_VAULT_ALLOW_INSECURE", "false") or "false"
        ).strip().lower()
        return cls(
            mode=str(os.getenv("SECRET_PROVIDER_MODE", "disabled") or "disabled"),
            file_path=str(os.getenv("SECRET_PROVIDER_FILE", "") or ""),
            env_prefix=str(os.getenv("SECRET_PROVIDER_ENV_PREFIX", "") or ""),
            http_url=str(os.getenv("SECRET_PROVIDER_HTTP_URL", "") or ""),
            http_auth_token=str(os.getenv("SECRET_PROVIDER_HTTP_AUTH_TOKEN", "") or ""),
            http_timeout_sec=str(os.getenv("SECRET_PROVIDER_HTTP_TIMEOUT_SEC", "3.0") or "3.0"),
            http_allow_insecure=allow_insecure_raw in {"1", "true", "yes", "on"},
            vault_url=str(os.getenv("SECRET_PROVIDER_VAULT_URL", "") or ""),
            vault_auth_token=str(os.getenv("SECRET_PROVIDER_VAULT_AUTH_TOKEN", "") or ""),
            vault_timeout_sec=str(
                os.getenv("SECRET_PROVIDER_VAULT_TIMEOUT_SEC", "3.0") or "3.0"
            ),
            vault_allow_insecure=vault_allow_insecure_raw in {"1", "true", "yes", "on"},
            chain_order=str(os.getenv("SECRET_PROVIDER_CHAIN_ORDER", "") or ""),
        )

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def file_loaded(self) -> bool:
        return self._file_loaded

    @property
    def http_loaded(self) -> bool:
        return self._http_loaded

    @property
    def vault_loaded(self) -> bool:
        return self._vault_loaded

    def _load_file_secrets(self) -> dict[str, Any]:
        if self._file_cache is not None:
            return self._file_cache
        self._file_error = ""
        if not self.file_path:
            self._file_cache = {}
            self._file_loaded = False
            self._file_error = "SECRET_PROVIDER_FILE is not configured."
            return self._file_cache
        path = Path(self.file_path).expanduser()
        if not path.exists():
            self._file_cache = {}
            self._file_loaded = False
            self._file_error = f"File not found: {path}"
            return self._file_cache
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._file_cache = raw if isinstance(raw, dict) else {}
            self._file_loaded = True
        except Exception:
            self._file_cache = {}
            self._file_loaded = False
            self._file_error = "Failed to parse JSON secret file."
        return self._file_cache

    def _load_http_secrets(self) -> dict[str, Any]:
        if self._http_cache is not None:
            return self._http_cache
        self._http_error = ""
        if not self.http_url:
            self._http_cache = {}
            self._http_loaded = False
            self._http_error = "SECRET_PROVIDER_HTTP_URL is not configured."
            return self._http_cache
        parsed = urlparse(self.http_url)
        if parsed.scheme not in {"https", "http"}:
            self._http_cache = {}
            self._http_loaded = False
            self._http_error = "HTTP secret URL must use http or https."
            return self._http_cache
        if parsed.scheme == "http" and not self.http_allow_insecure:
            self._http_cache = {}
            self._http_loaded = False
            self._http_error = "Insecure HTTP is blocked (set SECRET_PROVIDER_HTTP_ALLOW_INSECURE=true)."
            return self._http_cache
        headers = {"Accept": "application/json"}
        token = self.http_auth_token
        if token:
            header_value = token if token.lower().startswith("bearer ") else f"Bearer {token}"
            headers["Authorization"] = header_value
        request = Request(self.http_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.http_timeout_sec) as response:
                payload = response.read().decode("utf-8")
            raw = json.loads(payload)
            self._http_cache = raw if isinstance(raw, dict) else {}
            self._http_loaded = True
        except Exception:
            self._http_cache = {}
            self._http_loaded = False
            self._http_error = "Failed to load HTTP secret payload."
        return self._http_cache

    def _normalize_vault_payload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        first = payload.get("data")
        if isinstance(first, dict):
            second = first.get("data")
            if isinstance(second, dict):
                return second
            return first
        return payload

    def _load_vault_secrets(self) -> dict[str, Any]:
        if self._vault_cache is not None:
            return self._vault_cache
        self._vault_error = ""
        if not self.vault_url:
            self._vault_cache = {}
            self._vault_loaded = False
            self._vault_error = "SECRET_PROVIDER_VAULT_URL is not configured."
            return self._vault_cache
        parsed = urlparse(self.vault_url)
        if parsed.scheme not in {"https", "http"}:
            self._vault_cache = {}
            self._vault_loaded = False
            self._vault_error = "Vault URL must use http or https."
            return self._vault_cache
        if parsed.scheme == "http" and not self.vault_allow_insecure:
            self._vault_cache = {}
            self._vault_loaded = False
            self._vault_error = "Insecure Vault HTTP is blocked (set SECRET_PROVIDER_VAULT_ALLOW_INSECURE=true)."
            return self._vault_cache
        headers = {"Accept": "application/json"}
        token = self.vault_auth_token
        if token:
            headers["X-Vault-Token"] = token
        request = Request(self.vault_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.vault_timeout_sec) as response:
                payload = response.read().decode("utf-8")
            raw = json.loads(payload)
            self._vault_cache = self._normalize_vault_payload(raw)
            self._vault_loaded = bool(self._vault_cache)
        except Exception:
            self._vault_cache = {}
            self._vault_loaded = False
            self._vault_error = "Failed to load Vault secret payload."
        return self._vault_cache

    def _resolve_from_env(self, key: str) -> str | None:
        target = str(key or "").strip()
        if not target:
            return None
        self._env_error = ""
        direct = os.getenv(target)
        if direct is not None and str(direct).strip():
            return str(direct)
        if self.env_prefix:
            prefixed = os.getenv(f"{self.env_prefix}{target}")
            if prefixed is not None and str(prefixed).strip():
                return str(prefixed)
        self._env_error = f"Environment secret not found for key '{target}'."
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

    def _resolve_from_http(self, key_path: str) -> str | None:
        key = str(key_path or "").strip()
        if not key:
            return None
        current: Any = self._load_http_secrets()
        for part in key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if current is None:
            return None
        resolved = str(current).strip()
        return resolved or None

    def _resolve_from_vault(self, key_path: str) -> str | None:
        key = str(key_path or "").strip()
        if not key:
            return None
        current: Any = self._load_vault_secrets()
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
        if self.mode == "http":
            return self._resolve_from_http(key) if provider == "http" else None
        if self.mode == "vault":
            return self._resolve_from_vault(key) if provider == "vault" else None
        # chain mode
        if provider == "chain":
            return self._resolve_from_chain(key)
        if provider == "env":
            return self._resolve_from_env(key)
        if provider == "file":
            return self._resolve_from_file(key)
        if provider == "http":
            return self._resolve_from_http(key)
        if provider == "vault":
            return self._resolve_from_vault(key)
        return None

    def _resolve_from_chain(self, key: str) -> str | None:
        target = str(key or "").strip()
        if not target:
            return None
        for provider in self._chain_order:
            if provider == "env":
                resolved = self._resolve_from_env(target)
            elif provider == "file":
                resolved = self._resolve_from_file(target)
            elif provider == "http":
                resolved = self._resolve_from_http(target)
            elif provider == "vault":
                resolved = self._resolve_from_vault(target)
            else:
                resolved = None
            if resolved is not None:
                return resolved
        return None

    def adapter_snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": bool(self.enabled),
            "chain_order": list(self._chain_order),
            "adapters": {
                "env": {
                    "configured": True,
                    "loaded": True,
                    "last_error": self._env_error,
                },
                "file": {
                    "configured": bool(self.file_path),
                    "loaded": bool(self._file_loaded),
                    "last_error": self._file_error,
                    "path": self.file_path,
                },
                "http": {
                    "configured": bool(self.http_url),
                    "loaded": bool(self._http_loaded),
                    "last_error": self._http_error,
                    "url": self.http_url,
                },
                "vault": {
                    "configured": bool(self.vault_url),
                    "loaded": bool(self._vault_loaded),
                    "last_error": self._vault_error,
                    "url": self.vault_url,
                },
            },
        }

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
