import json
import os
import threading
from pathlib import Path
from typing import List, Optional

from src.models.run_record import RunRecord


class RunStore:
    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "runs.json"
        self._lock = threading.RLock()

    def load_runs(self) -> List[RunRecord]:
        with self._lock:
            if not self.file_path.exists():
                return []

            try:
                with open(self.file_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                if not isinstance(data, list):
                    return []
                return [RunRecord.from_dict(item) for item in data if isinstance(item, dict)]
            except Exception:
                return []

    def save_runs(self, runs: List[RunRecord]) -> None:
        with self._lock:
            data = [run.to_dict() for run in runs]
            temp_file_path = self.file_path.with_suffix(".tmp")
            with open(temp_file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            os.replace(temp_file_path, self.file_path)
            try:
                os.chmod(self.file_path, 0o600)
            except OSError:
                pass

    def add_run(self, run: RunRecord) -> None:
        with self._lock:
            runs = self.load_runs()
            runs.insert(0, run)
            self.save_runs(runs)

    def update_run(self, run_id: str, updated_run: RunRecord) -> bool:
        with self._lock:
            runs = self.load_runs()

            for index, run in enumerate(runs):
                if run.id == run_id:
                    runs[index] = updated_run
                    self.save_runs(runs)
                    return True

            return False

    def get_run_by_id(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            runs = self.load_runs()
            for run in runs:
                if run.id == run_id:
                    return run
            return None
