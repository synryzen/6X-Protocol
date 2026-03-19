import json
import os
from pathlib import Path
from typing import Any, Dict


class SettingsStore:
    ALLOWED_PROVIDERS = {"local", "openai", "anthropic"}
    ALLOWED_LOCAL_BACKENDS = {
        "ollama",
        "lm_studio",
        "openai_compatible",
        "vllm",
        "llama_cpp",
        "text_generation_webui",
        "jan",
    }
    ALLOWED_THEMES = {"system", "light", "dark"}
    ALLOWED_DENSITIES = {"comfortable", "compact"}
    ALLOWED_THEME_PRESETS = {
        "graphite",
        "indigo",
        "carbon",
        "aurora",
        "frost",
        "sunset",
        "rose",
        "amber",
    }

    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "settings.json"

        self.default_settings = {
            "local_ai_enabled": True,
            "preferred_provider": "local",
            "local_ai_backend": "ollama",
            "local_ai_endpoint": "http://localhost:11434",
            "local_ai_api_key": "",
            "ollama_url": "http://localhost:11434",
            "default_local_model": "",
            "openai_api_key": "",
            "anthropic_api_key": "",
            "slack_webhook_url": "",
            "discord_webhook_url": "",
            "telegram_bot_token": "",
            "telegram_default_chat_id": "",
            "openweather_api_key": "",
            "google_apps_script_url": "",
            "google_sheets_api_key": "",
            "google_sheets_spreadsheet_id": "",
            "google_sheets_range": "",
            "gmail_api_key": "",
            "gmail_from_address": "",
            "notion_api_key": "",
            "airtable_api_key": "",
            "hubspot_api_key": "",
            "stripe_api_key": "",
            "jira_api_key": "",
            "asana_api_key": "",
            "clickup_api_key": "",
            "trello_api_key": "",
            "monday_api_key": "",
            "zendesk_api_key": "",
            "pipedrive_api_key": "",
            "salesforce_api_key": "",
            "gitlab_api_key": "",
            "twilio_account_sid": "",
            "twilio_auth_token": "",
            "twilio_from_number": "",
            "github_api_key": "",
            "linear_api_key": "",
            "resend_api_key": "",
            "resend_from_address": "",
            "mailgun_api_key": "",
            "mailgun_domain": "",
            "mailgun_from_address": "",
            "postgres_connection_url": "",
            "mysql_connection_url": "",
            "redis_connection_url": "",
            "theme": "dark",
            "theme_preset": "graphite",
            "ui_density": "comfortable",
            "reduce_motion": False,
            "auto_save_workflows": True,
            "daemon_autostart": False,
            "tray_enabled": False,
            "canvas_minimap_x": 0,
            "canvas_minimap_y": 0,
            "canvas_minimap_user_placed": False,
        }

    def load_settings(self) -> Dict:
        if not self.file_path.exists():
            return dict(self.default_settings)

        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            return dict(self.default_settings)

        if not isinstance(data, dict):
            return dict(self.default_settings)

        return self._sanitize_settings(data)

    def save_settings(self, settings: Dict) -> None:
        merged = self._sanitize_settings(settings)

        temp_file_path = self.file_path.with_suffix(".tmp")
        with open(temp_file_path, "w", encoding="utf-8") as file:
            json.dump(merged, file, indent=2)

        os.replace(temp_file_path, self.file_path)

        try:
            os.chmod(self.file_path, 0o600)
        except OSError:
            pass

    def _sanitize_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(self.default_settings)
        raw = settings if isinstance(settings, dict) else {}

        merged["local_ai_enabled"] = bool(
            raw.get("local_ai_enabled", self.default_settings["local_ai_enabled"])
        )

        preferred_provider = str(
            raw.get("preferred_provider", self.default_settings["preferred_provider"])
        ).strip().lower()
        if preferred_provider not in self.ALLOWED_PROVIDERS:
            preferred_provider = self.default_settings["preferred_provider"]
        merged["preferred_provider"] = preferred_provider

        local_backend = str(
            raw.get("local_ai_backend", self.default_settings["local_ai_backend"])
        ).strip().lower()
        if local_backend not in self.ALLOWED_LOCAL_BACKENDS:
            local_backend = self.default_settings["local_ai_backend"]
        merged["local_ai_backend"] = local_backend

        local_endpoint_value = str(raw.get("local_ai_endpoint", "")).strip()
        if not local_endpoint_value:
            legacy_ollama_url = str(raw.get("ollama_url", "")).strip()
            if (
                local_backend != "ollama"
                and (not legacy_ollama_url or legacy_ollama_url == "http://localhost:11434")
            ):
                local_endpoint_value = self.default_endpoint_for_backend(local_backend)
            else:
                local_endpoint_value = legacy_ollama_url
        if not local_endpoint_value:
            local_endpoint_value = self.default_endpoint_for_backend(local_backend)
        local_endpoint_value = self._sanitize_local_endpoint(local_endpoint_value)
        merged["local_ai_endpoint"] = local_endpoint_value

        merged["local_ai_api_key"] = str(raw.get("local_ai_api_key", "")).strip()

        for key in [
            "ollama_url",
            "default_local_model",
            "openai_api_key",
            "anthropic_api_key",
            "slack_webhook_url",
            "discord_webhook_url",
            "telegram_bot_token",
            "telegram_default_chat_id",
            "openweather_api_key",
            "google_apps_script_url",
            "google_sheets_api_key",
            "google_sheets_spreadsheet_id",
            "google_sheets_range",
            "gmail_api_key",
            "gmail_from_address",
            "notion_api_key",
            "airtable_api_key",
            "hubspot_api_key",
            "stripe_api_key",
            "jira_api_key",
            "asana_api_key",
            "clickup_api_key",
            "trello_api_key",
            "monday_api_key",
            "zendesk_api_key",
            "pipedrive_api_key",
            "salesforce_api_key",
            "gitlab_api_key",
            "twilio_account_sid",
            "twilio_auth_token",
            "twilio_from_number",
            "github_api_key",
            "linear_api_key",
            "resend_api_key",
            "resend_from_address",
            "mailgun_api_key",
            "mailgun_domain",
            "mailgun_from_address",
            "postgres_connection_url",
            "mysql_connection_url",
            "redis_connection_url",
        ]:
            value = raw.get(key, self.default_settings[key])
            merged[key] = str(value).strip()
        merged["default_local_model"] = self._sanitize_model_name(merged["default_local_model"])
        if not merged["ollama_url"]:
            merged["ollama_url"] = merged["local_ai_endpoint"]
        merged["ollama_url"] = self._sanitize_local_endpoint(merged["ollama_url"])

        theme = str(raw.get("theme", self.default_settings["theme"])).strip().lower()
        if theme not in self.ALLOWED_THEMES:
            theme = self.default_settings["theme"]
        merged["theme"] = theme

        theme_preset = str(
            raw.get("theme_preset", self.default_settings["theme_preset"])
        ).strip().lower()
        if theme_preset not in self.ALLOWED_THEME_PRESETS:
            theme_preset = self.default_settings["theme_preset"]
        merged["theme_preset"] = theme_preset

        ui_density = str(
            raw.get("ui_density", self.default_settings["ui_density"])
        ).strip().lower()
        if ui_density not in self.ALLOWED_DENSITIES:
            ui_density = self.default_settings["ui_density"]
        merged["ui_density"] = ui_density

        merged["reduce_motion"] = bool(
            raw.get("reduce_motion", self.default_settings["reduce_motion"])
        )

        merged["auto_save_workflows"] = bool(
            raw.get("auto_save_workflows", self.default_settings["auto_save_workflows"])
        )
        merged["daemon_autostart"] = bool(
            raw.get("daemon_autostart", self.default_settings["daemon_autostart"])
        )
        merged["tray_enabled"] = bool(
            raw.get("tray_enabled", self.default_settings["tray_enabled"])
        )
        merged["canvas_minimap_x"] = max(
            0,
            self._coerce_int(
                raw.get("canvas_minimap_x", self.default_settings["canvas_minimap_x"]),
                self.default_settings["canvas_minimap_x"],
            ),
        )
        merged["canvas_minimap_y"] = max(
            0,
            self._coerce_int(
                raw.get("canvas_minimap_y", self.default_settings["canvas_minimap_y"]),
                self.default_settings["canvas_minimap_y"],
            ),
        )
        merged["canvas_minimap_user_placed"] = bool(
            raw.get(
                "canvas_minimap_user_placed",
                self.default_settings["canvas_minimap_user_placed"],
            )
        )

        return merged

    def default_endpoint_for_backend(self, backend: str) -> str:
        normalized = str(backend).strip().lower()
        if normalized == "lm_studio":
            return "http://localhost:1234/v1"
        if normalized in {"openai_compatible", "vllm"}:
            return "http://localhost:8000/v1"
        if normalized == "llama_cpp":
            return "http://localhost:8080/v1"
        if normalized == "text_generation_webui":
            return "http://localhost:5000/v1"
        if normalized == "jan":
            return "http://localhost:1337/v1"
        return "http://localhost:11434"

    def _sanitize_local_endpoint(self, endpoint: str) -> str:
        value = str(endpoint).strip()
        if not value:
            return ""
        return value.rstrip("/")

    def _sanitize_model_name(self, model: str) -> str:
        value = str(model).strip().strip("/")
        if not value:
            return ""
        lower = value.lower()
        for suffix in ["v1/chat/completions", "chat/completions", "v1/completions", "completions"]:
            if lower.endswith(suffix):
                value = value[: -len(suffix)].rstrip("/")
                break
        return value

    def _coerce_int(self, value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(fallback)
