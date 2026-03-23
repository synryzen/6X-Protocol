import json
from pathlib import Path
from typing import Dict


class IntegrationSettingsStore:
    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "integration-settings.json"

    def default_export_path(self) -> Path:
        return self.data_dir / "integration-test-profiles.json"

    def load_all(self) -> Dict[str, Dict[str, str]]:
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                raw = json.load(file)
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}

        normalized: Dict[str, Dict[str, str]] = {}
        for key, value in raw.items():
            integration_key = str(key).strip().lower()
            if not integration_key or not isinstance(value, dict):
                continue
            normalized[integration_key] = self._sanitize_profile(value)
        return normalized

    def get_profile(self, integration_key: str) -> Dict[str, str]:
        key = integration_key.strip().lower()
        if not key:
            return {}
        return dict(self.load_all().get(key, {}))

    def save_profile(self, integration_key: str, profile: Dict[str, str]) -> None:
        key = integration_key.strip().lower()
        if not key:
            return

        all_profiles = self.load_all()
        all_profiles[key] = self._sanitize_profile(profile)
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(all_profiles, file, indent=2)

    def delete_profile(self, integration_key: str) -> None:
        key = integration_key.strip().lower()
        if not key:
            return

        all_profiles = self.load_all()
        if key not in all_profiles:
            return
        del all_profiles[key]
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(all_profiles, file, indent=2)

    def export_profiles(self, destination_path: str | Path | None = None) -> tuple[Path, int]:
        export_path = (
            Path(destination_path).expanduser()
            if destination_path
            else self.default_export_path()
        )
        export_path.parent.mkdir(parents=True, exist_ok=True)
        profiles = self.load_all()
        with open(export_path, "w", encoding="utf-8") as file:
            json.dump(profiles, file, indent=2)
        return export_path, len(profiles)

    def import_profiles(
        self,
        source_path: str | Path,
        *,
        merge: bool = True,
    ) -> tuple[int, int]:
        import_path = Path(source_path).expanduser()
        if not import_path.exists():
            raise FileNotFoundError(f"Profile bundle not found: {import_path}")

        with open(import_path, "r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict):
            raise ValueError("Invalid profile bundle format. Expected an object map.")

        imported: Dict[str, Dict[str, str]] = {}
        for key, value in raw.items():
            integration_key = str(key).strip().lower()
            if not integration_key or not isinstance(value, dict):
                continue
            imported[integration_key] = self._sanitize_profile(value)

        if merge:
            all_profiles = self.load_all()
            all_profiles.update(imported)
        else:
            all_profiles = dict(imported)

        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(all_profiles, file, indent=2)

        return len(imported), len(all_profiles)

    def _sanitize_profile(self, profile: Dict[str, str]) -> Dict[str, str]:
        return {
            "input_context": str(profile.get("input_context", "")).strip(),
            "directives": str(profile.get("directives", "")).strip(),
        }
