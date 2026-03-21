"""Background run controller for scaffold execution state transitions."""

from __future__ import annotations

import concurrent.futures
import base64
import json
import os
import re
import shlex
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
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
    TRIGGER_MODE_EXECUTION_PROFILES = {
        "manual": {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 15.0},
        "schedule_interval": {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 20.0},
        "cron": {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 20.0},
        "webhook": {"retry_max": 1.0, "retry_backoff_ms": 150.0, "timeout_sec": 45.0},
        "file_watch": {"retry_max": 1.0, "retry_backoff_ms": 150.0, "timeout_sec": 45.0},
    }
    ACTION_FAST_INTEGRATIONS = {
        "slack_webhook",
        "discord_webhook",
        "teams_webhook",
        "telegram_bot",
        "twilio_sms",
        "openweather_current",
    }
    ACTION_STANDARD_INTEGRATIONS = {
        "http_post",
        "http_request",
        "google_apps_script",
        "google_sheets",
        "google_calendar_api",
        "outlook_graph",
        "notion_api",
        "airtable_api",
        "hubspot_api",
        "stripe_api",
        "github_rest",
        "gitlab_api",
        "google_drive_api",
        "dropbox_api",
        "shopify_api",
        "webflow_api",
        "supabase_api",
        "openrouter_api",
        "linear_api",
        "jira_api",
        "asana_api",
        "clickup_api",
        "trello_api",
        "monday_api",
        "zendesk_api",
        "pipedrive_api",
        "salesforce_api",
        "gmail_send",
        "resend_email",
        "mailgun_email",
    }
    ACTION_HEAVY_INTEGRATIONS = {
        "shell_command",
        "file_append",
        "postgres_sql",
        "mysql_sql",
        "sqlite_sql",
        "redis_command",
        "s3_cli",
    }

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
            nodes, node_map, outgoing_map, start_node_ids, edges, node_order = plan

            if not nodes:
                self._mark_success(run_id, "Run completed with no nodes.")
                return

            graph = workflow.get("graph", {}) if isinstance(workflow.get("graph"), dict) else {}
            graph_settings = graph.get("settings", {}) if isinstance(graph.get("settings"), dict) else {}
            max_parallel = self._safe_int(
                graph_settings.get("max_parallel", graph_settings.get("concurrency", 2)),
                2,
            )
            max_parallel = max(1, min(8, max_parallel))

            node_index = {node_id: idx for idx, node_id in enumerate(node_order)}
            incoming_total = self._build_incoming_count(node_map, edges)
            remaining_dependencies = dict(incoming_total)
            activated_inputs = {node_id: 0 for node_id in node_map}
            incoming_payloads = {node_id: [] for node_id in node_map}
            node_state = {node_id: "pending" for node_id in node_map}
            ready_queue: list[str] = []

            def queue_node(node_id: str) -> None:
                if node_state.get(node_id) != "pending":
                    return
                node_state[node_id] = "queued"
                ready_queue.append(node_id)
                ready_queue.sort(key=lambda item: node_index.get(item, 10_000))

            def prune_node(node_id: str) -> None:
                state = node_state.get(node_id)
                if state not in {"pending", "queued"}:
                    return
                node_state[node_id] = "pruned"
                node = node_map.get(node_id)
                node_name = str(node.get("name", "Node")).strip() if node else "Node"
                self._append_node_event(
                    run_id,
                    {
                        "timestamp": utc_now_iso(),
                        "node_id": node_id,
                        "node_name": node_name,
                        "status": "skipped",
                        "message": "Node skipped because branch was not selected.",
                        "attempt": "0",
                        "duration_ms": "0",
                    },
                    log_line=f"Node skipped: {node_name}",
                )
                for edge in outgoing_map.get(node_id, []):
                    target_id = str(edge.get("target_node_id", "")).strip()
                    if target_id not in remaining_dependencies:
                        continue
                    if remaining_dependencies[target_id] > 0:
                        remaining_dependencies[target_id] -= 1
                    schedule_or_prune(target_id)

            def schedule_or_prune(node_id: str) -> None:
                if node_state.get(node_id) != "pending":
                    return
                if remaining_dependencies.get(node_id, 0) > 0:
                    return
                has_input = activated_inputs.get(node_id, 0) > 0
                is_root = incoming_total.get(node_id, 0) == 0
                if node_id in start_node_ids or is_root or has_input:
                    queue_node(node_id)
                else:
                    prune_node(node_id)

            for node_id in node_order:
                schedule_or_prune(node_id)

            active_futures: dict[concurrent.futures.Future[tuple[bool, str]], tuple[str, dict[str, Any]]] = {}

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
                while ready_queue or active_futures:
                    if cancel_event.is_set():
                        self._mark_cancelled(run_id, "Run cancelled by user.")
                        return

                    while ready_queue and len(active_futures) < max_parallel:
                        node_id = ready_queue.pop(0)
                        if node_state.get(node_id) != "queued":
                            continue
                        node = node_map.get(node_id)
                        if not node:
                            node_state[node_id] = "pruned"
                            continue
                        node_state[node_id] = "running"
                        payloads = [
                            str(item).strip()
                            for item in incoming_payloads.get(node_id, [])
                            if str(item).strip()
                        ]
                        last_output = "\n".join(payloads).strip()
                        node_context: dict[str, Any] = {
                            "last_output": last_output,
                            "last_condition": None,
                            "node_attempts": {},
                        }
                        policy = self._resolve_node_policy(node, run_defaults)
                        future = pool.submit(
                            self._execute_node_with_retries,
                            run_id,
                            node,
                            policy,
                            node_context,
                            cancel_event,
                        )
                        active_futures[future] = (node_id, node_context)

                    if not active_futures:
                        continue

                    completed, _ = concurrent.futures.wait(
                        list(active_futures.keys()),
                        timeout=0.1,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    if not completed:
                        continue

                    for future in completed:
                        node_id, node_context = active_futures.pop(future)
                        node = node_map.get(node_id)
                        node_name = str(node.get("name", "Node")).strip() if node else "Node"
                        try:
                            success, failed_message = future.result()
                        except RunCancelledError:
                            self._mark_cancelled(run_id, "Run cancelled by user.")
                            return
                        except Exception as error:  # pragma: no cover - defensive safety
                            success = False
                            failed_message = str(error)

                        if not success:
                            error_policy = self._resolve_node_error_policy(node or {})
                            error_mode = str(error_policy.get("mode", "fail")).strip().lower()
                            error_target = str(error_policy.get("target_node_id", "")).strip()
                            selected_targets: set[str] = set()

                            if error_mode == "goto":
                                if not error_target:
                                    node_state[node_id] = "failed"
                                    cancel_event.set()
                                    self._mark_failed(
                                        run_id,
                                        (
                                            f"{failed_message} Error strategy requested goto but no target was set."
                                        ),
                                        last_failed_node_id=node_id,
                                        last_failed_node_name=node_name,
                                    )
                                    return
                                if error_target not in node_map:
                                    node_state[node_id] = "failed"
                                    cancel_event.set()
                                    self._mark_failed(
                                        run_id,
                                        (
                                            f"{failed_message} Error strategy target '{error_target}' was not found."
                                        ),
                                        last_failed_node_id=node_id,
                                        last_failed_node_name=node_name,
                                    )
                                    return
                                selected_targets = {error_target}
                                continue_message = (
                                    f"{failed_message} Continuing via on_error='goto:{error_target}'."
                                )
                            elif error_mode == "continue":
                                fallback_target = self._default_next_target_for_error(
                                    node_id,
                                    outgoing_map,
                                )
                                if fallback_target:
                                    selected_targets = {fallback_target}
                                    continue_message = (
                                        f"{failed_message} Continuing via on_error='continue'."
                                    )
                                else:
                                    continue_message = (
                                        f"{failed_message} on_error='continue' had no downstream edge; run will stop gracefully."
                                    )
                            else:
                                node_state[node_id] = "failed"
                                cancel_event.set()
                                self._mark_failed(
                                    run_id,
                                    failed_message,
                                    last_failed_node_id=node_id,
                                    last_failed_node_name=node_name,
                                )
                                return

                            attempt_value = 1
                            context_attempts = node_context.get("node_attempts")
                            if isinstance(context_attempts, dict):
                                attempt_value = self._safe_int(context_attempts.get(node_id, 1), 1)
                            self._append_node_event(
                                run_id,
                                {
                                    "timestamp": utc_now_iso(),
                                    "node_id": node_id,
                                    "node_name": node_name,
                                    "status": "warning",
                                    "message": continue_message,
                                    "attempt": str(max(1, attempt_value)),
                                    "duration_ms": "0",
                                },
                                log_line=continue_message,
                            )
                            node_context["last_status"] = "failed"
                            node_context["last_error"] = failed_message
                            fallback_output = str(node_context.get("last_output", "")).strip()
                            if not fallback_output:
                                fallback_output = f"error:{self._truncate_text(failed_message, 140)}"
                            node_context["last_output"] = fallback_output
                            node_state[node_id] = "completed"
                            output = fallback_output
                        else:
                            node_state[node_id] = "completed"
                            output = str(node_context.get("last_output", "")).strip()
                            next_node_ids, branch_log = self._determine_next_node_ids(
                                node or {},
                                outgoing_map,
                                node_context,
                            )
                            if branch_log:
                                self._append_log_line(run_id, branch_log)
                            selected_targets = set(next_node_ids)

                        for edge in outgoing_map.get(node_id, []):
                            target_id = str(edge.get("target_node_id", "")).strip()
                            if target_id not in remaining_dependencies:
                                continue
                            if remaining_dependencies[target_id] > 0:
                                remaining_dependencies[target_id] -= 1
                            if target_id in selected_targets:
                                activated_inputs[target_id] = activated_inputs.get(target_id, 0) + 1
                                if output:
                                    incoming_payloads.setdefault(target_id, []).append(output)
                            schedule_or_prune(target_id)

            pending = [node_id for node_id, state in node_state.items() if state in {"pending", "queued", "running"}]
            if pending:
                blocked = ", ".join(pending[:5])
                suffix = "..." if len(pending) > 5 else ""
                self._mark_failed(
                    run_id,
                    f"Run blocked by unresolved dependencies: {blocked}{suffix}",
                )
                return

            skipped_count = len([1 for state in node_state.values() if state == "pruned"])
            if skipped_count > 0:
                self._mark_success(run_id, f"Run completed successfully ({skipped_count} node(s) skipped).")
            else:
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
            trigger_mode, trigger_value = self._resolve_trigger_context(
                node=node,
                config=config,
                metadata=metadata,
            )
            if trigger_mode == "schedule_interval":
                interval_seconds = self._safe_float(trigger_value, 0.0)
                if interval_seconds <= 0.0:
                    raise NodeExecutionError(
                        "Trigger schedule_interval requires a positive trigger_value in seconds."
                    )
                interval_text = f"{int(round(interval_seconds))}s"
                output = f"trigger:schedule_interval:{interval_text}"
                context["trigger_mode"] = "schedule_interval"
                context["trigger_value"] = interval_text
                context["last_output"] = output
                return f"Trigger fired (schedule_interval:{interval_text}).", output

            if trigger_mode == "cron":
                cron_expr = str(trigger_value).strip()
                if not self._looks_like_cron(cron_expr):
                    raise NodeExecutionError(
                        f"Trigger cron expression is invalid: '{cron_expr}'."
                    )
                output = f"trigger:cron:{cron_expr}"
                context["trigger_mode"] = "cron"
                context["trigger_value"] = cron_expr
                context["last_output"] = output
                return f"Trigger fired (cron:{cron_expr}).", output

            if trigger_mode == "webhook":
                endpoint = str(trigger_value).strip() or "/incoming"
                output = f"trigger:webhook:{endpoint}"
                context["trigger_mode"] = "webhook"
                context["trigger_value"] = endpoint
                context["last_output"] = output
                return f"Trigger fired (webhook:{endpoint}).", output

            if trigger_mode == "file_watch":
                watched_path = str(trigger_value).strip() or "/tmp"
                output = f"trigger:file_watch:{watched_path}"
                context["trigger_mode"] = "file_watch"
                context["trigger_value"] = watched_path
                context["last_output"] = output
                return f"Trigger fired (file_watch:{watched_path}).", output

            output = "trigger:manual"
            context["trigger_mode"] = "manual"
            context["trigger_value"] = ""
            context["last_output"] = output
            return "Trigger fired (manual).", output

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
        ).strip().lower() or "standard"
        detail_message, output = self._execute_action_integration(
            integration=integration,
            config=config,
            context=context,
            timeout_sec=timeout_sec,
        )
        context["last_output"] = output
        return detail_message, output

    def _execute_action_integration(
        self,
        *,
        integration: str,
        config: dict[str, Any],
        context: dict[str, Any],
        timeout_sec: float,
    ) -> tuple[str, str]:
        normalized = integration.strip().lower() or "standard"
        output_text = str(
            config.get("message", config.get("detail", context.get("last_output", "")))
        ).strip()
        timeout_value = self._http_timeout(timeout_sec, config)

        if normalized in {"http_request", "http_post"}:
            method = str(config.get("method", "POST" if normalized == "http_post" else "GET")).strip().upper()
            url = self._pick_url(config)
            if not url:
                raise NodeExecutionError(f"Integration '{normalized}' requires a URL.")
            headers = self._headers_from_config(config)
            api_key = str(config.get("api_key", config.get("token", ""))).strip()
            if api_key and "authorization" not in {key.lower() for key in headers}:
                headers["Authorization"] = f"Bearer {api_key}"
            payload = str(config.get("payload", output_text)).strip()
            body = None
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                body, content_type = self._payload_bytes(payload)
                headers.setdefault("Content-Type", content_type)
            status, response_text = self._http_request(
                url=url,
                method=method,
                headers=headers,
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 120)
            return (
                f"Action executed via '{normalized}' ({method} {status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized in {"slack_webhook", "teams_webhook", "discord_webhook"}:
            url = self._pick_url(config)
            if not url:
                raise NodeExecutionError(f"Integration '{normalized}' requires a webhook URL.")
            text = output_text or "Workflow action executed."
            payload_obj: dict[str, Any]
            if normalized == "discord_webhook":
                payload_obj = {"content": text}
            else:
                payload_obj = {"text": text}
            body = json.dumps(payload_obj).encode("utf-8")
            status, response_text = self._http_request(
                url=url,
                method="POST",
                headers={"Content-Type": "application/json"},
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 100)
            return (
                f"Webhook '{normalized}' delivered ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "telegram_bot":
            payload_data = self._as_mapping(config.get("payload", ""))
            url = self._pick_url(config)
            text = str(
                config.get(
                    "message",
                    payload_data.get("text", output_text or "Workflow action executed."),
                )
            ).strip() or "Workflow action executed."
            if not url:
                bot_token = str(
                    config.get(
                        "bot_token",
                        config.get(
                            "api_key",
                            payload_data.get("bot_token", payload_data.get("api_key", "")),
                        ),
                    )
                ).strip()
                chat_id = str(config.get("chat_id", payload_data.get("chat_id", ""))).strip()
                if not bot_token or not chat_id:
                    raise NodeExecutionError(
                        "Integration 'telegram_bot' requires url or both bot_token and chat_id."
                    )
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload_obj = {"chat_id": chat_id, "text": text}
            else:
                payload_obj = {"text": text}
            body = json.dumps(payload_obj).encode("utf-8")
            status, response_text = self._http_request(
                url=url,
                method="POST",
                headers={"Content-Type": "application/json"},
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 100)
            return (
                f"Telegram message sent ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "openweather_current":
            payload_data = self._as_mapping(config.get("payload", ""))
            api_key = str(config.get("api_key", payload_data.get("api_key", ""))).strip()
            location = str(
                config.get("location", config.get("city", payload_data.get("location", payload_data.get("city", ""))))
            ).strip()
            units = str(config.get("units", "metric")).strip() or "metric"
            if not api_key or not location:
                raise NodeExecutionError(
                    "Integration 'openweather_current' requires api_key and location."
                )
            query = urllib.parse.urlencode(
                {
                    "q": location,
                    "appid": api_key,
                    "units": units,
                }
            )
            url = f"https://api.openweathermap.org/data/2.5/weather?{query}"
            status, response_text = self._http_request(
                url=url,
                method="GET",
                headers={},
                body=None,
                timeout_sec=timeout_value,
            )
            description = ""
            temperature = ""
            try:
                payload_obj = json.loads(response_text)
                weather = payload_obj.get("weather", [])
                if isinstance(weather, list) and weather and isinstance(weather[0], dict):
                    description = str(weather[0].get("description", "")).strip()
                main = payload_obj.get("main", {})
                if isinstance(main, dict):
                    temp = main.get("temp")
                    if temp is not None:
                        temperature = str(temp).strip()
            except Exception:
                pass
            weather_summary = ", ".join(
                [item for item in [temperature and f"{temperature}°", description] if item]
            ).strip(", ")
            preview = weather_summary or self._truncate_text(response_text, 96)
            return (
                f"OpenWeather query completed ({status}).",
                f"integration:{normalized} | location:{location} | {preview}",
            )

        if normalized in {
            "google_apps_script",
            "google_sheets",
            "google_calendar_api",
            "outlook_graph",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "linear_api",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
        }:
            url = self._pick_url(config) or self._default_api_endpoint(normalized)
            if not url:
                raise NodeExecutionError(f"Integration '{normalized}' requires a URL.")
            method = str(
                config.get("method", self._default_api_method(normalized))
            ).strip().upper() or "POST"
            headers = self._headers_from_config(config)
            api_key = str(config.get("api_key", config.get("token", ""))).strip()
            if api_key and "authorization" not in {key.lower() for key in headers}:
                headers["Authorization"] = f"Bearer {api_key}"
            if normalized == "notion_api":
                headers.setdefault("Notion-Version", "2022-06-28")

            body = None
            payload = str(config.get("payload", output_text)).strip()
            if method in {"POST", "PUT", "PATCH", "DELETE"} or payload:
                body, content_type = self._payload_bytes(payload)
                headers.setdefault("Content-Type", content_type)
            status, response_text = self._http_request(
                url=url,
                method=method,
                headers=headers,
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 120)
            return (
                f"Integration '{normalized}' request completed ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "twilio_sms":
            account_sid = str(config.get("account_sid", "")).strip()
            auth_token = str(config.get("auth_token", "")).strip()
            from_number = str(config.get("from", "")).strip()
            to_number = str(config.get("to", "")).strip()
            message = str(config.get("message", output_text or "Workflow action executed.")).strip()
            if not account_sid or not auth_token or not from_number or not to_number:
                raise NodeExecutionError(
                    "Integration 'twilio_sms' requires account_sid, auth_token, from, and to."
                )
            url = self._pick_url(config) or (
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            )
            token_bytes = f"{account_sid}:{auth_token}".encode("utf-8")
            basic_auth = base64.b64encode(token_bytes).decode("ascii")
            payload_obj = urllib.parse.urlencode(
                {"From": from_number, "To": to_number, "Body": message}
            ).encode("utf-8")
            status, response_text = self._http_request(
                url=url,
                method="POST",
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body=payload_obj,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 100)
            return (
                f"Twilio SMS request completed ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "gmail_send":
            api_key = str(config.get("api_key", "")).strip()
            to_value = str(config.get("to", "")).strip()
            from_value = str(config.get("from", config.get("sender", ""))).strip()
            subject_value = str(config.get("subject", "6X-Protocol Notification")).strip()
            message = str(config.get("message", output_text or "Workflow action executed.")).strip()
            if not api_key or not to_value:
                raise NodeExecutionError("Integration 'gmail_send' requires api_key and to.")
            if not from_value:
                from_value = "me"
            raw_message = (
                f"From: {from_value}\r\n"
                f"To: {to_value}\r\n"
                f"Subject: {subject_value}\r\n\r\n"
                f"{message}"
            )
            encoded_raw = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("ascii")
            url = self._pick_url(config) or "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
            body = json.dumps({"raw": encoded_raw}).encode("utf-8")
            status, response_text = self._http_request(
                url=url,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 100)
            return (
                f"Gmail send completed ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "resend_email":
            api_key = str(config.get("api_key", "")).strip()
            to_value = str(config.get("to", "")).strip()
            from_value = str(config.get("from", "")).strip()
            subject_value = str(config.get("subject", "6X-Protocol Notification")).strip()
            message = str(config.get("message", output_text or "Workflow action executed.")).strip()
            if not api_key or not to_value or not from_value:
                raise NodeExecutionError("Integration 'resend_email' requires api_key, to, and from.")
            url = self._pick_url(config) or "https://api.resend.com/emails"
            body = json.dumps(
                {"from": from_value, "to": [to_value], "subject": subject_value, "text": message}
            ).encode("utf-8")
            status, response_text = self._http_request(
                url=url,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 100)
            return (
                f"Resend email request completed ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "mailgun_email":
            api_key = str(config.get("api_key", "")).strip()
            domain = str(config.get("domain", "")).strip()
            to_value = str(config.get("to", "")).strip()
            from_value = str(config.get("from", "")).strip()
            subject_value = str(config.get("subject", "6X-Protocol Notification")).strip()
            message = str(config.get("message", output_text or "Workflow action executed.")).strip()
            if not api_key or not domain or not to_value or not from_value:
                raise NodeExecutionError(
                    "Integration 'mailgun_email' requires api_key, domain, to, and from."
                )
            url = self._pick_url(config) or f"https://api.mailgun.net/v3/{domain}/messages"
            token_bytes = f"api:{api_key}".encode("utf-8")
            basic_auth = base64.b64encode(token_bytes).decode("ascii")
            body = urllib.parse.urlencode(
                {
                    "from": from_value,
                    "to": to_value,
                    "subject": subject_value,
                    "text": message,
                }
            ).encode("utf-8")
            status, response_text = self._http_request(
                url=url,
                method="POST",
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body=body,
                timeout_sec=timeout_value,
            )
            preview = self._truncate_text(response_text, 100)
            return (
                f"Mailgun email request completed ({status}).",
                f"integration:{normalized} | status:{status} | {preview}",
            )

        if normalized == "shell_command":
            command = str(config.get("command", "")).strip()
            if not command:
                raise NodeExecutionError("Integration 'shell_command' requires command.")
            command_timeout = self._command_timeout(timeout_value, config)
            try:
                completed = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=command_timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise NodeTimeoutError(f"Shell command timed out after {command_timeout:.2f}s") from error
            except Exception as error:
                raise NodeExecutionError(f"Shell command failed to start: {error}") from error

            stdout = str(completed.stdout or "").strip()
            stderr = str(completed.stderr or "").strip()
            if completed.returncode != 0:
                detail = self._truncate_text(stderr or stdout or "command failed", 180)
                raise NodeExecutionError(
                    f"Shell command exited with code {completed.returncode}: {detail}"
                )
            preview = self._truncate_text(stdout or stderr or "(no output)", 140)
            return (
                "Shell command completed.",
                f"integration:{normalized} | exit:0 | {preview}",
            )

        if normalized == "file_append":
            path = str(config.get("path", "")).strip() or "/tmp/6x-workflow.log"
            message = str(
                config.get(
                    "message",
                    config.get("payload", output_text or context.get("last_output", "")),
                )
            ).strip()
            if not message:
                message = "Workflow action executed."
            try:
                directory = os.path.dirname(path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(f"{message}\n")
            except Exception as error:
                raise NodeExecutionError(f"File append failed for {path}: {error}") from error
            return (
                f"File append completed ({path}).",
                f"integration:{normalized} | path:{path} | {self._truncate_text(message, 96)}",
            )

        if normalized == "sqlite_sql":
            payload_data = self._as_mapping(config.get("payload", ""))
            db_path = str(
                config.get("path", payload_data.get("path", payload_data.get("db_path", "")))
            ).strip()
            sql = str(
                config.get("sql", payload_data.get("sql", payload_data.get("query", "")))
            ).strip()
            if not db_path or not sql:
                raise NodeExecutionError(
                    "Integration 'sqlite_sql' requires path and sql (or payload JSON with both)."
                )
            command_timeout = self._command_timeout(timeout_value, config)
            started = time.monotonic()
            try:
                directory = os.path.dirname(db_path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                with sqlite3.connect(db_path) as connection:
                    cursor = connection.cursor()
                    cursor.execute(sql)
                    lowered = sql.lstrip().lower()
                    if lowered.startswith("select") or lowered.startswith("pragma"):
                        rows = cursor.fetchall()
                        serialized_rows = json.dumps(rows[:25], ensure_ascii=False)
                        preview = self._truncate_text(serialized_rows, 160)
                        return (
                            f"SQLite query completed ({len(rows)} row(s)).",
                            (
                                f"integration:{normalized} | path:{db_path} | rows:{len(rows)} "
                                f"| {preview}"
                            ),
                        )
                    connection.commit()
                    affected = int(cursor.rowcount if cursor.rowcount is not None else 0)
                    return (
                        f"SQLite statement completed ({affected} row(s) affected).",
                        f"integration:{normalized} | path:{db_path} | affected:{affected}",
                    )
            except sqlite3.Error as error:
                raise NodeExecutionError(f"SQLite execution failed: {error}") from error
            finally:
                elapsed = time.monotonic() - started
                if command_timeout > 0 and elapsed > command_timeout:
                    raise NodeTimeoutError(f"SQLite query timed out after {command_timeout:.2f}s")

        if normalized == "postgres_sql":
            payload_data = self._as_mapping(config.get("payload", ""))
            connection_url = self._coalesce_fields(
                config,
                payload_data,
                ["connection_url", "url", "endpoint", "request_url"],
            )
            sql = self._coalesce_fields(config, payload_data, ["sql", "query"])
            if not connection_url or not sql:
                raise NodeExecutionError(
                    "Integration 'postgres_sql' requires connection_url and sql "
                    "(or payload JSON with both)."
                )
            command_timeout = self._command_timeout(timeout_value, config)
            args = ["psql", connection_url, "-t", "-A", "-c", sql]
            stdout = self._run_command(args, timeout_sec=command_timeout, integration=normalized)
            preview = self._truncate_text(stdout or "(no output)", 160)
            return (
                "Postgres query completed.",
                f"integration:{normalized} | {preview}",
            )

        if normalized == "mysql_sql":
            payload_data = self._as_mapping(config.get("payload", ""))
            connection_url = self._coalesce_fields(
                config,
                payload_data,
                ["connection_url", "url", "endpoint", "request_url"],
            )
            sql = self._coalesce_fields(config, payload_data, ["sql", "query"])
            if not connection_url or not sql:
                raise NodeExecutionError(
                    "Integration 'mysql_sql' requires connection_url and sql "
                    "(or payload JSON with both)."
                )
            parsed = urllib.parse.urlparse(connection_url)
            if parsed.scheme.lower() not in {"mysql", "mysql2"}:
                raise NodeExecutionError("mysql_sql connection_url must use mysql:// scheme.")
            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            user = urllib.parse.unquote(parsed.username or "")
            password = urllib.parse.unquote(parsed.password or "")
            database = (parsed.path or "").lstrip("/")
            if not user or not database:
                raise NodeExecutionError("mysql_sql connection_url must include username and database.")

            command_timeout = self._command_timeout(timeout_value, config)
            args = [
                "mysql",
                "--protocol=TCP",
                "-h",
                host,
                "-P",
                str(port),
                "-u",
                user,
                "-D",
                database,
                "-N",
                "-B",
                "-e",
                sql,
            ]
            env = dict(os.environ)
            if password:
                env["MYSQL_PWD"] = password
            stdout = self._run_command(
                args,
                timeout_sec=command_timeout,
                integration=normalized,
                env=env,
            )
            preview = self._truncate_text(stdout or "(no output)", 160)
            return (
                "MySQL query completed.",
                f"integration:{normalized} | {preview}",
            )

        if normalized == "redis_command":
            payload_data = self._as_mapping(config.get("payload", ""))
            connection_url = self._coalesce_fields(
                config,
                payload_data,
                ["connection_url", "url", "endpoint", "request_url"],
            )
            command_text = self._coalesce_fields(config, payload_data, ["command", "query"])
            if not command_text:
                raise NodeExecutionError("Integration 'redis_command' requires command.")
            command_timeout = self._command_timeout(timeout_value, config)
            args = ["redis-cli"]
            if connection_url:
                args.extend(["-u", connection_url])
            args.extend(shlex.split(command_text))
            stdout = self._run_command(args, timeout_sec=command_timeout, integration=normalized)
            preview = self._truncate_text(stdout or "(no output)", 140)
            return (
                "Redis command completed.",
                f"integration:{normalized} | {preview}",
            )

        if normalized == "s3_cli":
            payload_data = self._as_mapping(config.get("payload", ""))
            command_text = self._coalesce_fields(config, payload_data, ["command", "query"]) or "s3 ls"
            command_timeout = self._command_timeout(timeout_value, config)
            command_parts = shlex.split(command_text)
            if not command_parts:
                command_parts = ["s3", "ls"]
            if command_parts[0] == "aws":
                args = command_parts
            else:
                args = ["aws", *command_parts]
            stdout = self._run_command(args, timeout_sec=command_timeout, integration=normalized)
            preview = self._truncate_text(stdout or "(no output)", 140)
            return (
                "S3 CLI command completed.",
                f"integration:{normalized} | {preview}",
            )

        if normalized == "approval_gate":
            message = str(
                config.get("message", config.get("approval_message", "Approval gate passed."))
            ).strip() or "Approval gate passed."
            return (
                "Approval gate acknowledged.",
                f"integration:{normalized} | {self._truncate_text(message, 140)}",
            )

        output = f"integration:{normalized}"
        if output_text:
            output = f"{output} | {self._truncate_text(output_text, 96)}"
        return f"Action executed via '{normalized}'.", output

    def _http_request(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_sec: float,
    ) -> tuple[int, str]:
        request = urllib.request.Request(
            url=url,
            method=method,
            data=body,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                return int(getattr(response, "status", 200)), text
        except urllib.error.HTTPError as error:
            body_text = ""
            try:
                body_text = error.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""
            raise NodeExecutionError(
                f"HTTP {error.code} for {url}: {self._truncate_text(body_text, 160) or error.reason}"
            ) from error
        except urllib.error.URLError as error:
            raise NodeExecutionError(f"Request failed for {url}: {error.reason}") from error
        except TimeoutError as error:
            raise NodeTimeoutError(f"Request timed out for {url}") from error

    def _http_timeout(self, policy_timeout_sec: float, config: dict[str, Any]) -> float:
        config_timeout = self._safe_float(config.get("timeout_sec", 0.0), 0.0)
        values = [value for value in [policy_timeout_sec, config_timeout] if float(value) > 0]
        if values:
            return max(0.2, min(60.0, min(values)))
        return 12.0

    def _command_timeout(self, timeout_sec: float, config: dict[str, Any]) -> float:
        command_timeout = self._safe_float(config.get("timeout_sec", timeout_sec), timeout_sec)
        if command_timeout <= 0:
            return 30.0
        return max(0.2, min(180.0, float(command_timeout)))

    def _pick_url(self, config: dict[str, Any]) -> str:
        for key in ["url", "webhook_url", "script_url", "endpoint", "request_url"]:
            value = str(config.get(key, "")).strip()
            if value:
                return value
        return ""

    def _coalesce_fields(
        self,
        config: dict[str, Any],
        payload_data: dict[str, Any],
        keys: list[str],
    ) -> str:
        for key in keys:
            value = str(config.get(key, "")).strip()
            if value:
                return value
        for key in keys:
            value = str(payload_data.get(key, "")).strip()
            if value:
                return value
        return ""

    def _headers_from_config(self, config: dict[str, Any]) -> dict[str, str]:
        raw_headers = config.get("headers", "")
        if isinstance(raw_headers, dict):
            parsed = {
                str(key).strip(): str(value).strip()
                for key, value in raw_headers.items()
                if str(key).strip() and str(value).strip()
            }
            return parsed

        headers: dict[str, str] = {}
        text = str(raw_headers).strip()
        if not text:
            return headers
        for line in text.splitlines():
            item = line.strip()
            if not item or ":" not in item:
                continue
            key, value = item.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                headers[key] = value
        return headers

    def _payload_bytes(self, payload_text: str) -> tuple[bytes, str]:
        text = str(payload_text).strip()
        if not text:
            return b"{}", "application/json"
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            return text.encode("utf-8"), "application/json"
        return text.encode("utf-8"), "text/plain; charset=utf-8"

    def _default_api_endpoint(self, integration: str) -> str:
        key = str(integration).strip().lower()
        defaults = {
            "linear_api": "https://api.linear.app/graphql",
            "monday_api": "https://api.monday.com/v2",
        }
        return defaults.get(key, "")

    def _default_api_method(self, integration: str) -> str:
        key = str(integration).strip().lower()
        post_defaults = {
            "google_apps_script",
            "google_sheets",
            "linear_api",
            "monday_api",
        }
        return "POST" if key in post_defaults else "GET"

    def _as_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        text = str(value or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _parse_directives(self, text: str) -> dict[str, str]:
        directives: dict[str, str] = {}
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key:
                directives[key] = value
        return directives

    def _resolve_trigger_context(
        self,
        *,
        node: dict[str, Any],
        config: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[str, str]:
        detail_text = str(node.get("detail", "")).strip()
        detail_lower = detail_text.lower()
        directives = self._parse_directives(detail_text)

        mode = str(
            config.get(
                "trigger_mode",
                config.get(
                    "trigger",
                    metadata.get(
                        "trigger",
                        metadata.get("trigger_mode", directives.get("trigger_mode", "")),
                    ),
                ),
            )
        ).strip().lower()
        value = str(
            config.get(
                "trigger_value",
                metadata.get("trigger_value", directives.get("trigger_value", "")),
            )
        ).strip()

        if not mode:
            if detail_lower.startswith("schedule:"):
                mode = "schedule_interval"
                value = detail_text.split(":", 1)[1].strip() if ":" in detail_text else value
            elif detail_lower.startswith("webhook:"):
                mode = "webhook"
                value = detail_text.split(":", 1)[1].strip() if ":" in detail_text else value
            elif detail_lower.startswith("file_watch:"):
                mode = "file_watch"
                value = detail_text.split(":", 1)[1].strip() if ":" in detail_text else value
            elif detail_lower.startswith("cron:"):
                mode = "cron"
                value = detail_text.split(":", 1)[1].strip() if ":" in detail_text else value

        mode_aliases = {
            "schedule": "schedule_interval",
            "interval": "schedule_interval",
            "webhook_event": "webhook",
            "file": "file_watch",
            "watch": "file_watch",
        }
        mode = mode_aliases.get(mode, mode)
        if mode not in {"manual", "schedule_interval", "webhook", "file_watch", "cron"}:
            mode = "manual"

        if mode == "cron" and not value:
            value = str(config.get("cron", metadata.get("cron", directives.get("cron", "")))).strip()
        if mode == "webhook" and not value:
            value = str(config.get("webhook_url", config.get("url", directives.get("webhook", "")))).strip()
            if not value:
                value = self._pick_url(config)
        if mode == "file_watch" and not value:
            value = str(config.get("path", metadata.get("path", directives.get("path", "")))).strip()
        return mode, value

    def _looks_like_cron(self, value: str) -> bool:
        expression = str(value or "").strip()
        if not expression:
            return False
        parts = [item for item in expression.split() if item]
        if len(parts) < 5 or len(parts) > 7:
            return False
        token = re.compile(r"^[A-Za-z0-9_\-*/?,#LW]+$")
        return all(token.match(item) for item in parts)

    def _run_command(
        self,
        args: list[str],
        *,
        timeout_sec: float,
        integration: str,
        env: dict[str, str] | None = None,
    ) -> str:
        if not args:
            raise NodeExecutionError(f"Integration '{integration}' command is empty.")
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                env=env,
            )
        except FileNotFoundError as error:
            tool_name = args[0]
            raise NodeExecutionError(
                f"Integration '{integration}' requires '{tool_name}' to be installed."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise NodeTimeoutError(
                f"Integration '{integration}' command timed out after {timeout_sec:.2f}s."
            ) from error
        except Exception as error:
            raise NodeExecutionError(
                f"Integration '{integration}' command failed to start: {error}"
            ) from error

        stdout = str(completed.stdout or "").strip()
        stderr = str(completed.stderr or "").strip()
        if completed.returncode != 0:
            detail = self._truncate_text(stderr or stdout or "command failed", 180)
            raise NodeExecutionError(
                f"Integration '{integration}' command failed ({completed.returncode}): {detail}"
            )
        return stdout or stderr

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        value = str(text or "").strip().replace("\n", " ")
        if len(value) <= limit:
            return value
        return f"{value[: max(0, limit - 1)]}…"

    def _resolve_node_policy(
        self,
        node: dict[str, Any],
        run_defaults: dict[str, float | int | bool],
    ) -> dict[str, float | int]:
        config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        defaults = self._node_execution_defaults(node)

        default_retry_max = int(defaults["retry_max"])
        default_backoff_ms = int(defaults["retry_backoff_ms"])
        default_timeout_sec = float(defaults["timeout_sec"])

        use_run_retry = bool(run_defaults.get("override_retry_max", False))
        use_run_backoff = bool(run_defaults.get("override_retry_backoff_ms", False))
        use_run_timeout = bool(run_defaults.get("override_timeout_sec", False))

        fallback_retry = (
            int(run_defaults.get("retry_max", default_retry_max))
            if use_run_retry
            else default_retry_max
        )
        fallback_backoff = (
            int(run_defaults.get("retry_backoff_ms", default_backoff_ms))
            if use_run_backoff
            else default_backoff_ms
        )
        fallback_timeout = (
            float(run_defaults.get("timeout_sec", default_timeout_sec))
            if use_run_timeout
            else default_timeout_sec
        )

        retry_max = self._safe_int(
            config.get("retry_max", metadata.get("retry_max", fallback_retry)),
            fallback_retry,
        )
        backoff_ms = self._safe_int(
            config.get(
                "retry_backoff_ms",
                metadata.get("retry_backoff_ms", fallback_backoff),
            ),
            fallback_backoff,
        )
        timeout_sec = self._safe_float(
            config.get("timeout_sec", metadata.get("timeout_sec", fallback_timeout)),
            fallback_timeout,
        )

        return {
            "retry_max": max(0, min(8, retry_max)),
            "retry_backoff_ms": max(0, min(30000, backoff_ms)),
            "timeout_sec": max(0.0, min(120.0, timeout_sec)),
        }

    def _resolve_node_error_policy(self, node: dict[str, Any]) -> dict[str, str]:
        config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        detail = str(node.get("detail", "")).strip()
        directives = self._parse_directives(detail)

        raw_mode = (
            str(config.get("on_error", "")).strip()
            or str(config.get("error_mode", "")).strip()
            or str(metadata.get("on_error", "")).strip()
            or str(metadata.get("error_mode", "")).strip()
            or str(directives.get("on_error", "")).strip()
            or str(directives.get("error_mode", "")).strip()
        )
        target_node_id = (
            str(config.get("error_target_node_id", "")).strip()
            or str(config.get("on_error_target", "")).strip()
            or str(config.get("error_target", "")).strip()
            or str(metadata.get("error_target_node_id", "")).strip()
            or str(metadata.get("on_error_target", "")).strip()
            or str(metadata.get("error_target", "")).strip()
            or str(directives.get("error_target_node_id", "")).strip()
            or str(directives.get("on_error_target", "")).strip()
            or str(directives.get("error_target", "")).strip()
        )

        normalized = str(raw_mode).strip().lower()
        if ":" in normalized:
            prefix, suffix = normalized.split(":", 1)
            prefix = prefix.strip()
            suffix = suffix.strip()
            if prefix in {"goto", "route", "target"}:
                normalized = "goto"
                if suffix and not target_node_id:
                    target_node_id = suffix
            else:
                normalized = prefix

        if normalized in {"continue", "next", "skip"}:
            mode = "continue"
        elif normalized in {"goto", "route", "target"}:
            mode = "goto"
        else:
            mode = "fail"

        return {
            "mode": mode,
            "target_node_id": target_node_id,
        }

    def _default_next_target_for_error(
        self,
        source_node_id: str,
        outgoing_map: dict[str, list[dict[str, str]]],
    ) -> str:
        edges = outgoing_map.get(source_node_id, [])
        if not edges:
            return ""
        preferred = [
            edge
            for edge in edges
            if str(edge.get("condition", "")).strip().lower() in {"", "next", "default"}
        ]
        target = preferred[0] if preferred else edges[0]
        return str(target.get("target_node_id", "")).strip()

    def _node_kind(self, node_type: str) -> str:
        normalized = str(node_type).strip().lower()
        if normalized.startswith("trigger"):
            return "trigger"
        if normalized.startswith("action") or normalized.startswith("template"):
            return "action"
        if normalized.startswith("ai"):
            return "ai"
        if normalized.startswith("condition"):
            return "condition"
        return normalized

    def _node_execution_defaults(self, node: dict[str, Any]) -> dict[str, float]:
        node_kind = self._node_kind(self._node_type(node))
        config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        integration = str(
            config.get("integration", config.get("action_type", metadata.get("integration", "")))
        ).strip().lower()

        if node_kind == "trigger":
            trigger_mode, _ = self._resolve_trigger_context(
                node=node,
                config=config,
                metadata=metadata,
            )
            return dict(
                self.TRIGGER_MODE_EXECUTION_PROFILES.get(
                    trigger_mode,
                    self.TRIGGER_MODE_EXECUTION_PROFILES["manual"],
                )
            )
        if node_kind == "condition":
            return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 8.0}
        if node_kind == "ai":
            return {"retry_max": 1.0, "retry_backoff_ms": 300.0, "timeout_sec": 120.0}
        if node_kind == "action":
            if integration == "approval_gate":
                return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 0.0}
            if integration in self.ACTION_FAST_INTEGRATIONS:
                return {"retry_max": 1.0, "retry_backoff_ms": 200.0, "timeout_sec": 25.0}
            if integration in self.ACTION_HEAVY_INTEGRATIONS:
                return {"retry_max": 1.0, "retry_backoff_ms": 400.0, "timeout_sec": 90.0}
            if integration in self.ACTION_STANDARD_INTEGRATIONS:
                return {"retry_max": 1.0, "retry_backoff_ms": 250.0, "timeout_sec": 45.0}
            return {"retry_max": 1.0, "retry_backoff_ms": 250.0, "timeout_sec": 45.0}
        return {"retry_max": 1.0, "retry_backoff_ms": 250.0, "timeout_sec": 60.0}

    def _resolve_run_defaults(
        self,
        workflow: dict[str, Any],
        *,
        retry_max: int | None,
        retry_backoff_ms: int | None,
        timeout_sec: float | None,
    ) -> dict[str, float | int | bool]:
        graph = workflow.get("graph", {}) if isinstance(workflow.get("graph"), dict) else {}
        settings = graph.get("settings", {}) if isinstance(graph.get("settings"), dict) else {}
        override_retry_max = bool(retry_max is not None or "retry_max" in settings)
        override_retry_backoff_ms = bool(
            retry_backoff_ms is not None or "retry_backoff_ms" in settings
        )
        override_timeout_sec = bool(timeout_sec is not None or "timeout_sec" in settings)

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
            "override_retry_max": override_retry_max,
            "override_retry_backoff_ms": override_retry_backoff_ms,
            "override_timeout_sec": override_timeout_sec,
        }

    def _resolve_nodes(self, workflow: dict[str, Any], start_node_id: str) -> list[dict[str, Any]] | str:
        # Compatibility shim for older callers.
        plan = self._resolve_execution_plan(workflow, start_node_id)
        if isinstance(plan, str):
            return plan
        nodes, _node_map, _outgoing_map, queue, _edges, _node_order = plan
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
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, list[dict[str, str]]],
        list[str],
        list[dict[str, str]],
        list[str],
    ] | str:
        graph = workflow.get("graph", {}) if isinstance(workflow.get("graph"), dict) else {}
        raw_nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
        nodes: list[dict[str, Any]] = [item for item in raw_nodes if isinstance(item, dict)]
        full_node_map = {
            str(node.get("id", "")).strip(): node
            for node in nodes
            if str(node.get("id", "")).strip()
        }
        node_order_full = [str(node.get("id", "")).strip() for node in nodes if str(node.get("id", "")).strip()]
        if not full_node_map:
            return nodes, {}, {}, [], [], []

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

        outgoing_map_full = self._build_outgoing_map(edges)
        synthetic_chain_edges: list[dict[str, str]] = []

        planned_node_ids: set[str]
        if start_node_id:
            if start_node_id not in full_node_map:
                return f"Replay start node '{start_node_id}' was not found."
            if edges:
                planned_node_ids = set()
                stack = [start_node_id]
                while stack:
                    current = stack.pop()
                    if current in planned_node_ids:
                        continue
                    if current not in full_node_map:
                        continue
                    planned_node_ids.add(current)
                    for edge in outgoing_map_full.get(current, []):
                        target = str(edge.get("target_node_id", "")).strip()
                        if target and target not in planned_node_ids:
                            stack.append(target)
            else:
                start_index = node_order_full.index(start_node_id)
                planned_tail = node_order_full[start_index:]
                planned_node_ids = set(planned_tail)
                synthetic_chain_edges = [
                    {
                        "source_node_id": planned_tail[index],
                        "target_node_id": planned_tail[index + 1],
                        "condition": "next",
                    }
                    for index in range(len(planned_tail) - 1)
                ]
        else:
            planned_node_ids = set(node_order_full)
            if not edges:
                synthetic_chain_edges = [
                    {
                        "source_node_id": node_order_full[index],
                        "target_node_id": node_order_full[index + 1],
                        "condition": "next",
                    }
                    for index in range(len(node_order_full) - 1)
                ]

        filtered_nodes = [
            node
            for node in nodes
            if str(node.get("id", "")).strip() in planned_node_ids
        ]
        node_map = {
            str(node.get("id", "")).strip(): node
            for node in filtered_nodes
            if str(node.get("id", "")).strip()
        }
        node_order = [
            node_id
            for node_id in node_order_full
            if node_id in node_map
        ]
        candidate_edges = edges if edges else synthetic_chain_edges
        filtered_edges = [
            edge
            for edge in candidate_edges
            if edge.get("source_node_id", "") in node_map and edge.get("target_node_id", "") in node_map
        ]
        outgoing_map = self._build_outgoing_map(filtered_edges)

        if not filtered_edges:
            if start_node_id:
                start_nodes = [start_node_id] if start_node_id in node_map else []
            else:
                start_nodes = list(node_order)
            return filtered_nodes, node_map, outgoing_map, start_nodes, filtered_edges, node_order

        incoming_count = self._build_incoming_count(node_map, filtered_edges)
        start_nodes = [node_id for node_id in node_order if incoming_count.get(node_id, 0) == 0]
        if start_node_id and start_node_id in node_map:
            start_nodes = [start_node_id]
        if not start_nodes and node_order:
            start_nodes = [node_order[0]]
        return filtered_nodes, node_map, outgoing_map, start_nodes, filtered_edges, node_order

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
