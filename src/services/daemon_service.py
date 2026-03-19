import re
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional

from src.models.workflow import Workflow
from src.services.execution_engine import ExecutionEngine
from src.services.workflow_store import WorkflowStore


class WorkflowDaemonService:
    def __init__(
        self,
        workflow_store: Optional[WorkflowStore] = None,
        execution_engine: Optional[ExecutionEngine] = None,
    ):
        self.workflow_store = workflow_store or WorkflowStore()
        self.execution_engine = execution_engine or ExecutionEngine()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_run_at: Dict[str, float] = {}
        self._logs: Deque[str] = deque(maxlen=250)
        self._poll_interval_seconds = 2.0

    def start(self) -> bool:
        started = False
        with self._lock:
            if self._running:
                return False

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._running = True
            self._thread.start()
            started = True

        if started:
            self._log("Daemon started.")
        return started

    def stop(self) -> bool:
        with self._lock:
            if not self._running:
                return False

            self._stop_event.set()
            thread = self._thread
            self._running = False

        if thread:
            thread.join(timeout=4.0)

        self._log("Daemon stopped.")
        return True

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def get_logs(self, limit: int = 80) -> List[str]:
        with self._lock:
            items = list(self._logs)
        return items[-limit:]

    def get_schedule_snapshot(self) -> List[Dict]:
        workflows = self.workflow_store.load_workflows()
        now = time.time()
        snapshot: List[Dict] = []

        for workflow in workflows:
            interval = self._extract_interval_seconds(workflow)
            if interval is None:
                continue

            last = self._last_run_at.get(workflow.id, 0.0)
            remaining = max(0.0, interval - (now - last)) if last > 0 else 0.0

            snapshot.append(
                {
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "interval_seconds": interval,
                    "next_run_in_seconds": int(remaining),
                }
            )

        return sorted(snapshot, key=lambda item: item["workflow_name"].lower())

    def _run_loop(self):
        while not self._stop_event.is_set():
            workflows = self.workflow_store.load_workflows()
            now = time.time()

            for workflow in workflows:
                interval = self._extract_interval_seconds(workflow)
                if interval is None:
                    continue

                last_run = self._last_run_at.get(workflow.id, 0.0)
                if now - last_run < interval:
                    continue

                self._last_run_at[workflow.id] = now
                self._execute_workflow(workflow)

            self._stop_event.wait(self._poll_interval_seconds)

    def _execute_workflow(self, workflow: Workflow):
        try:
            run = self.execution_engine.run_workflow(workflow)
            self._log(
                f"Daemon ran workflow '{workflow.name}' -> {run.status.upper()} ({run.id[:8]})."
            )
        except Exception as error:
            self._log(f"Daemon failed workflow '{workflow.name}': {error}")

    def _extract_interval_seconds(self, workflow: Workflow) -> Optional[int]:
        trigger_text = workflow.trigger.strip().lower()
        parsed = self._parse_interval_from_text(trigger_text)
        if parsed:
            return parsed

        graph = workflow.normalized_graph()
        for item in graph.get("nodes", []):
            if not isinstance(item, dict):
                continue

            node_type = str(item.get("node_type", "")).strip().lower()
            if not node_type.startswith("trigger"):
                continue

            config = item.get("config", {})
            if isinstance(config, dict):
                from_config = self._parse_interval_from_text(
                    str(config.get("interval_seconds", "")).strip()
                )
                if from_config:
                    return from_config

            detail = str(item.get("detail", "")).strip().lower()
            from_detail = self._parse_interval_from_text(detail)
            if from_detail:
                return from_detail

        return None

    def _parse_interval_from_text(self, text: str) -> Optional[int]:
        if not text:
            return None

        raw = text.strip().lower()
        if raw.startswith("interval:"):
            value = raw.split(":", 1)[1].strip()
            if value.isdigit():
                return max(1, int(value))

        if raw.isdigit():
            return max(1, int(raw))

        match = re.search(r"every\s+(\d+)\s*([smh]?)", raw)
        if match:
            amount = int(match.group(1))
            unit = match.group(2) or "s"
            if unit == "s":
                return max(1, amount)
            if unit == "m":
                return max(1, amount * 60)
            if unit == "h":
                return max(1, amount * 3600)

        return None

    def _log(self, message: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        with self._lock:
            self._logs.append(log_line)


_daemon_instance: Optional[WorkflowDaemonService] = None


def get_daemon_service() -> WorkflowDaemonService:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = WorkflowDaemonService()
    return _daemon_instance
