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


class NodeExecutionError(RuntimeError):
    pass


class NodeTimeoutError(NodeExecutionError):
    pass


class RunCancelledError(RuntimeError):
    pass


class RunController:
    def __init__(self, store: JsonStore) -> None:
        self.store = store
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._active_threads: dict[str, threading.Thread] = {}
        self._type_delay_ms = {
            "trigger": 50,
            "condition": 90,
            "ai": 320,
            "action": 220,
            "template": 220,
        }

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
        retry_max: int | None = None,
        retry_backoff_ms: int | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        workflow_id = str(workflow.get("id", "")).strip()
        workflow_name = str(workflow.get("name", "Untitled Workflow")).strip() or "Untitled Workflow"
        key = idempotency_key.strip()
        run_defaults = self._resolve_run_defaults(
            workflow,
            retry_max=retry_max,
            retry_backoff_ms=retry_backoff_ms,
            timeout_sec=timeout_sec,
        )

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
                "execution_retry_max": int(run_defaults["retry_max"]),
                "execution_backoff_ms": int(run_defaults["retry_backoff_ms"]),
                "execution_timeout_sec": float(run_defaults["timeout_sec"]),
            }
            runs.insert(0, run)
            self.store.save_runs(runs)

            cancel_event = threading.Event()
            worker = threading.Thread(
                target=self._execute_run,
                args=(run_id, workflow, cancel_event, start_node_id.strip(), run_defaults),
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
        run_defaults: dict[str, float | int],
    ) -> None:
        context: dict[str, Any] = {
            "last_output": "",
            "last_condition": None,
            "node_attempts": {},
        }

        try:
            plan = self._resolve_execution_plan(workflow, start_node_id)
            if isinstance(plan, str):
                self._mark_failed(
                    run_id,
                    plan,
                    last_failed_node_id=start_node_id,
                    last_failed_node_name="Replay",
                )
                return
            nodes, node_map, outgoing_map, queued_node_ids = plan

            if not nodes:
                self._mark_success(run_id, "Run completed with no nodes.")
                return

            queued = set(queued_node_ids)
            executed: set[str] = set()

            while queued_node_ids:
                if cancel_event.is_set():
                    self._mark_cancelled(run_id, "Run cancelled by user.")
                    return

                node_id = queued_node_ids.pop(0)
                queued.discard(node_id)
                if node_id in executed:
                    continue
                node = node_map.get(node_id)
                if not node:
                    continue

                node_id = str(node.get("id", "")).strip()
                node_name = str(node.get("name", "Node")).strip() or "Node"
                policy = self._resolve_node_policy(node, run_defaults)

                success, failed_message = self._execute_node_with_retries(
                    run_id,
                    node,
                    policy,
                    context,
                    cancel_event,
                )
                if not success:
                    self._mark_failed(
                        run_id,
                        failed_message,
                        last_failed_node_id=node_id,
                        last_failed_node_name=node_name,
                    )
                    return

                executed.add(node_id)
                next_node_ids, branch_log = self._determine_next_node_ids(node, outgoing_map, context)
                if branch_log:
                    self._append_log_line(run_id, branch_log)

                for next_node_id in next_node_ids:
                    if next_node_id in executed or next_node_id in queued:
                        continue
                    if next_node_id not in node_map:
                        self._mark_failed(
                            run_id,
                            f"Graph contains unknown edge target '{next_node_id}'.",
                            last_failed_node_id=node_id,
                            last_failed_node_name=node_name,
                        )
                        return
                    queued_node_ids.append(next_node_id)
                    queued.add(next_node_id)

            self._mark_success(run_id, "Run completed successfully.")
        except RunCancelledError:
            self._mark_cancelled(run_id, "Run cancelled by user.")
        finally:
            with self._lock:
                self._cancel_events.pop(run_id, None)
                self._active_threads.pop(run_id, None)

    def _execute_node_with_retries(
        self,
        run_id: str,
        node: dict[str, Any],
        policy: dict[str, float | int],
        context: dict[str, Any],
        cancel_event: threading.Event,
    ) -> tuple[bool, str]:
        node_id = str(node.get("id", "")).strip()
        node_name = str(node.get("name", "Node")).strip() or "Node"
        node_type = self._node_type(node)
        retry_max = int(policy["retry_max"])
        backoff_ms = int(policy["retry_backoff_ms"])

        for attempt in range(1, retry_max + 2):
            context_attempts = context.get("node_attempts")
            if isinstance(context_attempts, dict):
                context_attempts[node_id] = attempt

            self._append_node_event(
                run_id,
                {
                    "timestamp": utc_now_iso(),
                    "node_id": node_id,
                    "node_name": node_name,
                    "status": "running",
                    "message": f"Executing {node_type} node '{node_name}'.",
                    "attempt": str(attempt),
                    "duration_ms": "0",
                },
                log_line=f"Running node: {node_name} (attempt {attempt})",
            )

            started = time.monotonic()
            try:
                detail_message, output_preview = self._execute_single_node(
                    node,
                    policy,
                    context,
                    cancel_event,
                    attempt,
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                self._append_node_event(
                    run_id,
                    {
                        "timestamp": utc_now_iso(),
                        "node_id": node_id,
                        "node_name": node_name,
                        "status": "success",
                        "message": detail_message,
                        "attempt": str(attempt),
                        "duration_ms": str(duration_ms),
                        "output_preview": output_preview,
                    },
                    log_line=f"Node completed: {node_name}",
                )
                return True, ""
            except RunCancelledError:
                raise
            except (NodeExecutionError, NodeTimeoutError) as error:
                duration_ms = int((time.monotonic() - started) * 1000)
                self._append_node_event(
                    run_id,
                    {
                        "timestamp": utc_now_iso(),
                        "node_id": node_id,
                        "node_name": node_name,
                        "status": "failed",
                        "message": str(error),
                        "attempt": str(attempt),
                        "duration_ms": str(duration_ms),
                    },
                    log_line=f"Node attempt failed: {node_name} ({error})",
                )

                if attempt > retry_max:
                    return False, f"Node '{node_name}' failed after {attempt} attempt(s): {error}"

                retry_msg = (
                    f"Retrying '{node_name}' in {backoff_ms}ms "
                    f"(attempt {attempt + 1}/{retry_max + 1})."
                )
                self._append_node_event(
                    run_id,
                    {
                        "timestamp": utc_now_iso(),
                        "node_id": node_id,
                        "node_name": node_name,
                        "status": "retrying",
                        "message": retry_msg,
                        "attempt": str(attempt),
                        "duration_ms": "0",
                    },
                    log_line=retry_msg,
                )
                if backoff_ms > 0:
                    self._sleep_with_cancel(cancel_event, backoff_ms / 1000.0)

        return False, f"Node '{node_name}' failed."

    def _execute_single_node(
        self,
        node: dict[str, Any],
        policy: dict[str, float | int],
        context: dict[str, Any],
        cancel_event: threading.Event,
        attempt: int,
    ) -> tuple[str, str]:
        node_id = str(node.get("id", "")).strip()
        node_name = str(node.get("name", "Node")).strip() or "Node"
        node_type = self._node_type(node)
        config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}

        timeout_sec = float(policy["timeout_sec"])
        delay_ms = self._resolve_node_delay_ms(node_type, config, metadata)

        if timeout_sec > 0 and delay_ms > int(timeout_sec * 1000):
            self._sleep_with_cancel(cancel_event, timeout_sec)
            raise NodeTimeoutError(f"Timed out after {timeout_sec:.2f}s")

        if delay_ms > 0:
            self._sleep_with_cancel(cancel_event, delay_ms / 1000.0)

        fail_attempts = self._safe_int(
            metadata.get("simulate_failure_attempts", config.get("simulate_failure_attempts", 0)),
            0,
        )
        should_fail = bool(metadata.get("simulate_failure", config.get("simulate_failure", False)))
        if should_fail or (fail_attempts > 0 and attempt <= fail_attempts):
            raise NodeExecutionError("Simulated node failure.")

        if node_type == "trigger":
            trigger_mode = str(
                config.get("trigger_mode", config.get("trigger", metadata.get("trigger", "manual")))
            ).strip() or "manual"
            output = f"trigger:{trigger_mode}"
            context["last_output"] = output
            return f"Trigger fired ({trigger_mode}).", output

        if node_type == "condition":
            expression = str(
                config.get("condition", config.get("expression", config.get("rule", "always_true")))
            ).strip() or "always_true"
            result = self._evaluate_condition(expression, context)
            context["last_condition"] = result
            output = f"condition:{str(result).lower()}"
            context["last_output"] = output
            return f"Condition evaluated {str(result).lower()} ({expression}).", output

        if node_type == "ai":
            model = str(config.get("model", metadata.get("model", "local/default"))).strip() or "local/default"
            prompt = str(config.get("prompt", metadata.get("prompt", ""))).strip()
            if not prompt:
                prompt = f"Process node '{node_name}'."
            output = f"[{model}] {prompt[:80]}"
            context["last_output"] = output
            return f"AI node completed with model '{model}'.", output

        # action + template + fallback path
        integration = str(
            config.get("integration", config.get("action_type", metadata.get("integration", "standard")))
        ).strip() or "standard"
        action_text = str(config.get("message", config.get("detail", ""))).strip()
        output = f"integration:{integration}"
        if action_text:
            output = f"{output} | {action_text[:80]}"
        context["last_output"] = output
        return f"Action executed via '{integration}'.", output

    def _resolve_node_policy(
        self,
        node: dict[str, Any],
        run_defaults: dict[str, float | int],
    ) -> dict[str, float | int]:
        config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}

        retry_max = self._safe_int(
            config.get("retry_max", metadata.get("retry_max", run_defaults["retry_max"])),
            int(run_defaults["retry_max"]),
        )
        backoff_ms = self._safe_int(
            config.get(
                "retry_backoff_ms",
                metadata.get("retry_backoff_ms", run_defaults["retry_backoff_ms"]),
            ),
            int(run_defaults["retry_backoff_ms"]),
        )
        timeout_sec = self._safe_float(
            config.get("timeout_sec", metadata.get("timeout_sec", run_defaults["timeout_sec"])),
            float(run_defaults["timeout_sec"]),
        )

        return {
            "retry_max": max(0, min(8, retry_max)),
            "retry_backoff_ms": max(0, min(30000, backoff_ms)),
            "timeout_sec": max(0.0, min(120.0, timeout_sec)),
        }

    def _resolve_run_defaults(
        self,
        workflow: dict[str, Any],
        *,
        retry_max: int | None,
        retry_backoff_ms: int | None,
        timeout_sec: float | None,
    ) -> dict[str, float | int]:
        graph = workflow.get("graph", {}) if isinstance(workflow.get("graph"), dict) else {}
        settings = graph.get("settings", {}) if isinstance(graph.get("settings"), dict) else {}

        resolved_retry_max = self._safe_int(
            retry_max if retry_max is not None else settings.get("retry_max", 0),
            0,
        )
        resolved_backoff_ms = self._safe_int(
            retry_backoff_ms if retry_backoff_ms is not None else settings.get("retry_backoff_ms", 0),
            0,
        )
        resolved_timeout_sec = self._safe_float(
            timeout_sec if timeout_sec is not None else settings.get("timeout_sec", 0.0),
            0.0,
        )

        return {
            "retry_max": max(0, min(8, resolved_retry_max)),
            "retry_backoff_ms": max(0, min(30000, resolved_backoff_ms)),
            "timeout_sec": max(0.0, min(120.0, resolved_timeout_sec)),
        }

    def _resolve_nodes(self, workflow: dict[str, Any], start_node_id: str) -> list[dict[str, Any]] | str:
        # Compatibility shim for older callers.
        plan = self._resolve_execution_plan(workflow, start_node_id)
        if isinstance(plan, str):
            return plan
        nodes, _node_map, _outgoing_map, queue = plan
        if not start_node_id:
            return nodes
        node_lookup = {
            str(node.get("id", "")).strip(): node
            for node in nodes
            if str(node.get("id", "")).strip()
        }
        ordered: list[dict[str, Any]] = []
        for node_id in queue:
            node = node_lookup.get(node_id)
            if node:
                ordered.append(node)
        return ordered

    def _resolve_execution_plan(
        self,
        workflow: dict[str, Any],
        start_node_id: str,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, str]]], list[str]] | str:
        graph = workflow.get("graph", {}) if isinstance(workflow.get("graph"), dict) else {}
        raw_nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
        nodes: list[dict[str, Any]] = [item for item in raw_nodes if isinstance(item, dict)]
        node_map = {
            str(node.get("id", "")).strip(): node
            for node in nodes
            if str(node.get("id", "")).strip()
        }
        if not node_map:
            return nodes, {}, {}, []

        raw_edges = graph.get("edges", [])
        if not isinstance(raw_edges, list):
            raw_edges = []
        legacy_links = graph.get("links", [])
        if isinstance(legacy_links, list):
            raw_edges = [*raw_edges, *legacy_links]

        edges: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            source = str(
                item.get("source_node_id")
                or item.get("source")
                or item.get("source_id")
                or item.get("from")
                or ""
            ).strip()
            target = str(
                item.get("target_node_id")
                or item.get("target")
                or item.get("target_id")
                or item.get("to")
                or ""
            ).strip()
            if not source or not target:
                continue
            condition = self._normalize_edge_condition(
                item.get("condition") or item.get("link_type") or item.get("type") or ""
            )
            signature = (source, target, condition)
            if signature in seen:
                continue
            seen.add(signature)
            edges.append(
                {
                    "source_node_id": source,
                    "target_node_id": target,
                    "condition": condition,
                }
            )

        node_order = list(node_map)
        outgoing_map = self._build_outgoing_map(edges)

        if start_node_id:
            if start_node_id not in node_map:
                return f"Replay start node '{start_node_id}' was not found."
            return nodes, node_map, outgoing_map, [start_node_id]

        if not edges:
            return nodes, node_map, outgoing_map, node_order

        incoming_count = self._build_incoming_count(node_map, edges)
        start_nodes = [node_id for node_id in node_order if incoming_count.get(node_id, 0) == 0]
        if not start_nodes and node_order:
            start_nodes = [node_order[0]]
        return nodes, node_map, outgoing_map, start_nodes

    def _determine_next_node_ids(
        self,
        node: dict[str, Any],
        outgoing_map: dict[str, list[dict[str, str]]],
        context: dict[str, Any],
    ) -> tuple[list[str], str]:
        node_id = str(node.get("id", "")).strip()
        edges = outgoing_map.get(node_id, [])
        if not edges:
            return [], ""

        node_type = self._node_type(node)
        if node_type == "condition":
            branch = "true" if bool(context.get("last_condition", False)) else "false"
            direct = [edge for edge in edges if edge.get("condition", "") == branch]
            if direct:
                return [str(direct[0].get("target_node_id", "")).strip()], (
                    f"Condition branch '{branch}' selected."
                )
            fallback = [
                edge
                for edge in edges
                if edge.get("condition", "") in {"", "next"}
            ]
            if fallback:
                return [str(fallback[0].get("target_node_id", "")).strip()], (
                    f"Condition branch '{branch}' fell back to default path."
                )
            return [], f"Condition branch '{branch}' had no matching path."

        preferred = [edge for edge in edges if edge.get("condition", "") in {"", "next"}]
        selected = preferred if preferred else edges
        next_ids = [str(edge.get("target_node_id", "")).strip() for edge in selected]
        return [item for item in next_ids if item], ""

    def _build_outgoing_map(
        self,
        edges: list[dict[str, str]],
    ) -> dict[str, list[dict[str, str]]]:
        outgoing: dict[str, list[dict[str, str]]] = {}
        for edge in edges:
            source = str(edge.get("source_node_id", "")).strip()
            target = str(edge.get("target_node_id", "")).strip()
            if not source or not target:
                continue
            outgoing.setdefault(source, []).append(edge)
        return outgoing

    def _build_incoming_count(
        self,
        node_map: dict[str, dict[str, Any]],
        edges: list[dict[str, str]],
    ) -> dict[str, int]:
        counts = {node_id: 0 for node_id in node_map}
        for edge in edges:
            target = str(edge.get("target_node_id", "")).strip()
            if target in counts:
                counts[target] += 1
        return counts

    def _append_log_line(self, run_id: str, line: str) -> None:
        message = str(line).strip()
        if not message:
            return
        with self._lock:
            runs = self.store.load_runs()
            index = self._run_index(runs, run_id)
            if index < 0:
                return
            run = dict(runs[index])
            current_log = str(run.get("log", ""))
            run["log"] = f"{current_log}\n{message}".strip()
            run["updated_at"] = utc_now_iso()
            runs[index] = run
            self.store.save_runs(runs)

    @staticmethod
    def _normalize_edge_condition(raw_value: Any) -> str:
        value = str(raw_value).strip().lower()
        if not value:
            return ""
        if value in {"next", "default"}:
            return "next"
        if value in {"true", "if_true", "on_true", "success"}:
            return "true"
        if value in {"false", "if_false", "on_false", "fail", "failure"}:
            return "false"
        return ""

    def _resolve_node_delay_ms(
        self,
        node_type: str,
        config: dict[str, Any],
        metadata: dict[str, Any],
    ) -> int:
        candidate = (
            config.get("simulate_delay_ms")
            or config.get("delay_ms")
            or config.get("duration_ms")
            or metadata.get("simulate_delay_ms")
            or metadata.get("delay_ms")
            or metadata.get("duration_ms")
        )
        if candidate is not None:
            return max(0, min(45000, self._safe_int(candidate, 0)))
        return int(self._type_delay_ms.get(node_type, 180))

    def _evaluate_condition(self, expression: str, context: dict[str, Any]) -> bool:
        normalized = expression.strip().lower()
        if normalized in {"", "always_true", "true", "pass"}:
            return True
        if normalized in {"always_false", "false", "fail"}:
            return False

        last_output = str(context.get("last_output", ""))
        if normalized == "has_output":
            return bool(last_output.strip())
        if normalized == "no_output":
            return not bool(last_output.strip())

        if normalized.startswith("contains:"):
            needle = normalized.split(":", 1)[1].strip()
            return needle in last_output.lower()
        if normalized.startswith("equals:"):
            target = normalized.split(":", 1)[1].strip()
            return last_output.strip().lower() == target

        # Fallback: non-empty expression means pass for scaffold mode.
        return True

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
            run["timeline"] = node_results
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

    def _sleep_with_cancel(self, cancel_event: threading.Event, seconds: float) -> None:
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            if cancel_event.is_set():
                raise RunCancelledError()
            chunk = min(0.05, remaining)
            time.sleep(chunk)
            remaining -= chunk

    @staticmethod
    def _node_type(node: dict[str, Any]) -> str:
        return str(node.get("type", "action")).strip().lower() or "action"

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _run_index(runs: list[dict[str, Any]], run_id: str) -> int:
        for idx, run in enumerate(runs):
            if str(run.get("id", "")).strip() == run_id:
                return idx
        return -1
