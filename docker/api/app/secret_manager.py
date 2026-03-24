"""Optional secret encryption helpers for server-side JSON persistence."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

SECRET_PREFIX = "enc:v1:"

_SECRET_FIELD_MARKERS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "webhook_url",
    "connection_url",
    "auth",
)


def _is_secret_field(field_name: str) -> bool:
    key = str(field_name or "").strip().lower()
    if not key:
        return False
    return any(marker in key for marker in _SECRET_FIELD_MARKERS)


class SecretManager:
    def __init__(self, key_material: str = "") -> None:
        self.key_material = str(key_material or "").strip()
        self.enabled = bool(self.key_material)
        self._fernet = None
        if not self.enabled:
            return
        try:
            from cryptography.fernet import Fernet
        except ImportError as error:
            raise RuntimeError(
                "SECRET_ENCRYPTION_KEY is set but 'cryptography' is not installed."
            ) from error

        if self.key_material.startswith("fernet:"):
            key = self.key_material.split(":", 1)[1].strip().encode("utf-8")
        else:
            digest = hashlib.sha256(self.key_material.encode("utf-8")).digest()
            key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key)

    def encrypt_text(self, value: Any) -> str:
        text = str(value or "")
        if not self.enabled or not text:
            return text
        if text.startswith(SECRET_PREFIX):
            return text
        assert self._fernet is not None
        token = self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")
        return f"{SECRET_PREFIX}{token}"

    def decrypt_text(self, value: Any) -> str:
        text = str(value or "")
        if not text or not text.startswith(SECRET_PREFIX):
            return text
        if not self.enabled:
            # Keep encrypted payload intact when no key is provided.
            return text
        token = text[len(SECRET_PREFIX) :].strip()
        if not token:
            return ""
        try:
            assert self._fernet is not None
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception:
            # Leave unreadable ciphertext untouched instead of destroying data.
            return text

    def encrypt_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(settings, dict):
            return {}
        encrypted = dict(settings)
        for key in (
            "local_ai_api_key",
            "openai_api_key",
            "anthropic_api_key",
        ):
            if key in encrypted:
                encrypted[key] = self.encrypt_text(encrypted.get(key))
        return encrypted

    def decrypt_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(settings, dict):
            return {}
        decrypted = dict(settings)
        for key in (
            "local_ai_api_key",
            "openai_api_key",
            "anthropic_api_key",
        ):
            if key in decrypted:
                decrypted[key] = self.decrypt_text(decrypted.get(key))
        return decrypted

    def encrypt_integration_profiles(self, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(profiles, list):
            return []
        encrypted: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            item = dict(profile)
            config = item.get("config")
            if isinstance(config, dict):
                item["config"] = self._encrypt_mapping(config)
            encrypted.append(item)
        return encrypted

    def decrypt_integration_profiles(self, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(profiles, list):
            return []
        decrypted: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            item = dict(profile)
            config = item.get("config")
            if isinstance(config, dict):
                item["config"] = self._decrypt_mapping(config)
            decrypted.append(item)
        return decrypted

    def _encrypt_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        encrypted: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key)
            if isinstance(value, dict):
                encrypted[normalized_key] = self._encrypt_mapping(value)
            elif isinstance(value, list):
                encrypted[normalized_key] = self._encrypt_list(value)
            elif _is_secret_field(normalized_key):
                encrypted[normalized_key] = self.encrypt_text(value)
            else:
                encrypted[normalized_key] = value
        return encrypted

    def _decrypt_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        decrypted: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key)
            if isinstance(value, dict):
                decrypted[normalized_key] = self._decrypt_mapping(value)
            elif isinstance(value, list):
                decrypted[normalized_key] = self._decrypt_list(value)
            elif isinstance(value, str):
                decrypted[normalized_key] = self.decrypt_text(value)
            else:
                decrypted[normalized_key] = value
        return decrypted

    def _encrypt_list(self, payload: list[Any]) -> list[Any]:
        encrypted: list[Any] = []
        for item in payload:
            if isinstance(item, dict):
                encrypted.append(self._encrypt_mapping(item))
            elif isinstance(item, list):
                encrypted.append(self._encrypt_list(item))
            else:
                encrypted.append(item)
        return encrypted

    def _decrypt_list(self, payload: list[Any]) -> list[Any]:
        decrypted: list[Any] = []
        for item in payload:
            if isinstance(item, dict):
                decrypted.append(self._decrypt_mapping(item))
            elif isinstance(item, list):
                decrypted.append(self._decrypt_list(item))
            elif isinstance(item, str):
                decrypted.append(self.decrypt_text(item))
            else:
                decrypted.append(item)
        return decrypted

    @staticmethod
    def contains_encrypted_payload(payload: Any) -> bool:
        if isinstance(payload, str):
            return payload.startswith(SECRET_PREFIX)
        if isinstance(payload, dict):
            return any(SecretManager.contains_encrypted_payload(value) for value in payload.values())
        if isinstance(payload, list):
            return any(SecretManager.contains_encrypted_payload(item) for item in payload)
        return False
