"""Background run controller for scaffold execution state transitions."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from app.schemas import utc_now_iso
from app.storage import JsonStore

TERMINAL_STATUSES = {"success", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running", "cancelling"}


class RunController:
    def __init__(self, store: JsonStore) -> None:
        self.store = store
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._active_threads: dict[str, threading.Thread] = {}
        self._step_delay_seconds = 0.25

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        runs = self.store.load_runs()
        for run in runs:
            if str(run.get("id", "")) == run_id:
                return run
        return None

    def start(
        self,
        workflow: dict[str, Any],
        *,
        trigger: str = "manual",
        replay_of_run_id: str = "",
        attempt: int = 1,
        retry_count: int = 0,
        start_node_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        workflow_id = str(workflow.get("id", "")).strip()
        workflow_name = str(workflow.get("name", "Untitled Workflow")).strip() or "Untitled Workflow"
        key = idempotency_key.strip()

        with self._lock:
            runs = self.store.load_runs()
            if key:
                for existing in runs:
                    if str(existing.get("idempotency_key", "")).strip() != key:
                        continue
                    if str(existing.get("status", "")).strip().lower() in ACTIVE_STATUSES:
                        return existing

            run_id = str(uuid.uuid4())
            run = {
                "id": run_id,
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "status": "running",
                "trigger": trigger.strip() or "manual",
                "log": "Run started.",
                "summary": "Run started.",
                "node_results": [],
                "timeline": [],
                "last_failed_node_id": "",
                "last_failed_node_name": "",
                "created_at": now,
                "updated_at": now,
                "finished_at": "",
                "attempt": max(1, int(attempt)),
                "retry_count": max(0, int(retry_count)),
                "replay_of_run_id": replay_of_run_id.strip(),
                "idempotency_key": key or run_id,
                "cancellation_requested": False,
            }
            runs.insert(0, run)
            self.store.save_runs(runs)

            cancel_event = threading.Event()
            worker = threading.Thread(
                target=self._execute_run,
                args=(run_id, workflow, cancel_event, start_node_id.strip()),
                daemon=True,
            )
            self._cancel_events[run_id] = cancel_event
            self._active_threads[run_id] = worker
            worker.start()
            return run

    def cancel(self, run_id: str) -> tuple[bool, str, dict[str, Any] | None]:
        with self._lock:
            runs = self.store.load_runs()
            index = self._run_index(runs, run_id)
            if index < 0:
                return False, "Run not found.", None

            run = dict(runs[index])
            status = str(run.get("status", "")).strip().lower()
            if status in TERMINAL_STATUSES:
                return False, f"Run already {status}.", run
            if status == "cancelling":
                return False, "Cancel already requested.", run

            run["cancellation_requested"] = True
            if status == "queued":
                run["status"] = "cancelled"
                run["summary"] = "Run cancelled before execution."
                run["finished_at"] = utc_now_iso()
            else:
                run["status"] = "cancelling"
                run["summary"] = "Cancel requested."
            run["updated_at"] = utc_now_iso()
            runs[index] = run
            self.store.save_runs(runs)

            cancel_event = self._cancel_events.get(run_id)
            if cancel_event:
                cancel_event.set()
            return True, "Cancel requested.", run

    def _execute_run(
        self,
        run_id: str,
        workflow: dict[str, Any],
        cancel_event: threading.Event,
        start_node_id: str,
    ) -> None:
        try:
            nodes = self._resolve_nodes(workflow, start_node_id)
            if isinstance(nodes, str):
                self._mark_failed(run_id, nodes, last_failed_node_id=start_node_id, last_failed_node_name="Replay")
                return

            if not nodes:
                self._mark_success(run_id, "Run completed with no nodes.")
                return

            for node in nodes:
                if cancel_event.is_set():
                    self._mark_cancelled(run_id, "Run cancelled by user.")
                    return

                node_id = str(node.get("id", "")).strip()
                node_name = str(node.get("name", "Node")).strip() or "Node"
                node_type = str(node.get("type", "action")).strip().lower() or "action"

                self._append_node_event(
                    run_id,
                    {
                        "timestamp": utc_now_iso(),
                        "node_id": node_id,
                        "node_name": node_name,
                        "status": "running",
                        "message": f"Executing {node_type} node '{node_name}'.",
                        "attempt": "1",
                        "duration_ms": "0",
                    },
                    log_line=f"Running node: {node_name}",
                )

                time.sleep(self._step_delay_seconds)

                if cancel_event.is_set():
                    self._mark_cancelled(run_id, f"Run cancelled during '{node_name}'.")
                    return

                metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
                should_fail = bool(metadata.get("simulate_failure", False))
                if should_fail:
                    self._append_node_event(
                        run_id,
                        {
                            "timestamp": utc_now_iso(),
                            "node_id": node_id,
                            "node_name": node_name,
                            "status": "failed",
                            "message": "Simulated node failure.",
                            "attempt": "1",
                            "duration_ms": str(int(self._step_delay_seconds * 1000)),
                        },
                        log_line=f"Node failed: {node_name}",
                    )
                    self._mark_failed(
                        run_id,
                        f"Node '{node_name}' failed.",
                        last_failed_node_id=node_id,
                        last_failed_node_name=node_name,
                    )
                    return

                self._append_node_event(
                    run_id,
                    {
                        "timestamp": utc_now_iso(),
                        "node_id": node_id,
                        "node_name": node_name,
                        "status": "success",
                        "message": f"Node '{node_name}' completed.",
                        "attempt": "1",
                        "duration_ms": str(int(self._step_delay_seconds * 1000)),
                    },
                    log_line=f"Node completed: {node_name}",
                )

            self._mark_success(run_id, "Run completed successfully.")
        finally:
            with self._lock:
                self._cancel_events.pop(run_id, None)
                self._active_threads.pop(run_id, None)

    def _resolve_nodes(self, workflow: dict[str, Any], start_node_id: str) -> list[dict[str, Any]] | str:
        graph = workflow.get("graph", {}) if isinstance(workflow.get("graph"), dict) else {}
        nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
        normalized: list[dict[str, Any]] = [item for item in nodes if isinstance(item, dict)]

        if not start_node_id:
            return normalized

        for index, node in enumerate(normalized):
            if str(node.get("id", "")).strip() == start_node_id:
                return normalized[index:]
        return f"Replay start node '{start_node_id}' was not found."

    def _append_node_event(self, run_id: str, event: dict[str, Any], *, log_line: str = "") -> None:
        with self._lock:
            runs = self.store.load_runs()
            index = self._run_index(runs, run_id)
            if index < 0:
                return
            run = dict(runs[index])
            node_results = run.get("node_results", [])
            if not isinstance(node_results, list):
                node_results = []
            node_results.append(event)
            run["node_results"] = node_results
            if log_line:
                current_log = str(run.get("log", ""))
                run["log"] = f"{current_log}\n{log_line}".strip()
            run["updated_at"] = utc_now_iso()
            runs[index] = run
            self.store.save_runs(runs)

    def _mark_success(self, run_id: str, summary: str) -> None:
        self._set_terminal(run_id, "success", summary)

    def _mark_failed(
        self,
        run_id: str,
        summary: str,
        *,
        last_failed_node_id: str = "",
        last_failed_node_name: str = "",
    ) -> None:
        self._set_terminal(
            run_id,
            "failed",
            summary,
            last_failed_node_id=last_failed_node_id,
            last_failed_node_name=last_failed_node_name,
        )

    def _mark_cancelled(self, run_id: str, summary: str) -> None:
        self._set_terminal(run_id, "cancelled", summary)

    def _set_terminal(
        self,
        run_id: str,
        status: str,
        summary: str,
        *,
        last_failed_node_id: str = "",
        last_failed_node_name: str = "",
    ) -> None:
        with self._lock:
            runs = self.store.load_runs()
            index = self._run_index(runs, run_id)
            if index < 0:
                return
            run = dict(runs[index])
            run["status"] = status
            run["summary"] = summary
            run["finished_at"] = utc_now_iso()
            run["updated_at"] = utc_now_iso()
            if last_failed_node_id:
                run["last_failed_node_id"] = last_failed_node_id
            if last_failed_node_name:
                run["last_failed_node_name"] = last_failed_node_name
            runs[index] = run
            self.store.save_runs(runs)

    @staticmethod
    def _run_index(runs: list[dict[str, Any]], run_id: str) -> int:
        for idx, run in enumerate(runs):
            if str(run.get("id", "")).strip() == run_id:
                return idx
        return -1
