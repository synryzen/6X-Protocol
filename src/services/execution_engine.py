import re
import uuid
import json
import time
import os
import base64
import sqlite3
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.models.canvas_edge import CanvasEdge
from src.models.canvas_node import CanvasNode
from src.models.run_record import RunRecord
from src.models.workflow import Workflow
from src.services.ai_service import AIService
from src.services.bot_store import BotStore
from src.services.integration_registry_service import IntegrationRegistryService
from src.services.run_store import RunStore
from src.services.settings_store import SettingsStore


class ApprovalRequiredError(RuntimeError):
    def __init__(self, node_id: str, node_name: str, message: str):
        super().__init__(message)
        self.node_id = node_id
        self.node_name = node_name


class ExecutionEngine:
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

    def __init__(
        self,
        run_store: Optional[RunStore] = None,
        bot_store: Optional[BotStore] = None,
        ai_service: Optional[AIService] = None,
        integration_registry: Optional[IntegrationRegistryService] = None,
        settings_store: Optional[SettingsStore] = None,
    ):
        self.run_store = run_store or RunStore()
        self.bot_store = bot_store or BotStore()
        self.ai_service = ai_service or AIService()
        self.integration_registry = integration_registry or IntegrationRegistryService()
        self.settings_store = settings_store or SettingsStore()

    def run_workflow(
        self,
        workflow: Workflow,
        run_id: Optional[str] = None,
        persist: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
        initial_steps: Optional[List[str]] = None,
        start_node_id: Optional[str] = None,
        initial_context: Optional[Dict[str, object]] = None,
        replay_of_run_id: str = "",
        attempt: int = 1,
        retry_count: int = 0,
        idempotency_key: str = "",
    ) -> RunRecord:
        started_at = self._timestamp()
        execution = self._execute_graph(
            workflow,
            cancel_check=cancel_check,
            start_node_id=start_node_id,
            initial_context=initial_context,
        )
        finished_at = self._timestamp()
        merged_steps: List[str] = []
        if initial_steps:
            merged_steps.extend([str(step) for step in initial_steps if str(step).strip()])
        merged_steps.extend(execution["steps"])

        run = RunRecord(
            id=run_id or str(uuid.uuid4()),
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            status=execution["status"],
            started_at=started_at,
            finished_at=finished_at,
            summary=execution["summary"],
            steps=merged_steps,
            timeline=execution["timeline"],
            last_failed_node_id=execution["last_failed_node_id"],
            last_failed_node_name=execution["last_failed_node_name"],
            pending_approval_node_id=execution["pending_approval_node_id"],
            pending_approval_node_name=execution["pending_approval_node_name"],
            replay_of_run_id=replay_of_run_id,
            attempt=attempt,
            retry_count=retry_count,
            idempotency_key=idempotency_key or (run_id or str(uuid.uuid4())),
        )
        if persist:
            if run_id:
                updated = self.run_store.update_run(run.id, run)
                if not updated:
                    self.run_store.add_run(run)
            else:
                self.run_store.add_run(run)
        return run

    def _execute_graph(
        self,
        workflow: Workflow,
        cancel_check: Optional[Callable[[], bool]] = None,
        start_node_id: Optional[str] = None,
        initial_context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        timeline: List[Dict[str, str]] = []

        def finish(
            status: str,
            summary: str,
            steps: List[str],
            *,
            last_failed_node_id: str = "",
            last_failed_node_name: str = "",
            pending_approval_node_id: str = "",
            pending_approval_node_name: str = "",
        ) -> Dict[str, object]:
            return {
                "status": status,
                "summary": summary,
                "steps": steps,
                "timeline": timeline,
                "last_failed_node_id": last_failed_node_id,
                "last_failed_node_name": last_failed_node_name,
                "pending_approval_node_id": pending_approval_node_id,
                "pending_approval_node_name": pending_approval_node_name,
            }

        if cancel_check and cancel_check():
            steps = ["Run cancelled before execution."]
            timeline.append(
                self._timeline_event("", "Workflow", "cancelled", steps[0], attempt=1, duration_ms=0)
            )
            return finish("cancelled", "Run cancelled by user.", steps)

        graph = workflow.normalized_graph()
        graph_settings = graph.get("settings", {}) if isinstance(graph.get("settings", {}), dict) else {}
        nodes = self._parse_nodes(graph)
        edges = self._parse_edges(graph)

        if not nodes:
            if cancel_check and cancel_check():
                steps = ["Run cancelled before fallback flow."]
                timeline.append(
                    self._timeline_event("", "Workflow", "cancelled", steps[0], attempt=1, duration_ms=0)
                )
                return finish("cancelled", "Run cancelled by user.", steps)
            steps = [
                f"Trigger: {workflow.trigger}",
                f"Action: {workflow.action}",
            ]
            timeline.append(
                self._timeline_event(
                    "",
                    "Fallback Flow",
                    "success",
                    "Workflow executed with fallback trigger/action flow.",
                    attempt=1,
                    duration_ms=0,
                )
            )
            return finish("success", "Workflow executed with fallback trigger/action flow.", steps)

        node_map = {node.id: node for node in nodes}
        outgoing_map = self._build_outgoing_map(edges)
        incoming_count = self._build_incoming_count(nodes, edges)

        start_node: Optional[CanvasNode] = None
        if start_node_id:
            start_node = node_map.get(start_node_id)
            if not start_node:
                steps = [f"Replay start node '{start_node_id}' was not found."]
                timeline.append(
                    self._timeline_event(
                        start_node_id,
                        "Replay",
                        "failed",
                        steps[0],
                        attempt=1,
                        duration_ms=0,
                    )
                )
                return finish(
                    "failed",
                    steps[0],
                    steps,
                    last_failed_node_id=start_node_id,
                    last_failed_node_name="Replay",
                )
        else:
            start_node = self._find_start_node(nodes, incoming_count)

        if not start_node:
            steps = ["Unable to find a start node."]
            timeline.append(
                self._timeline_event("", "Workflow", "failed", steps[0], attempt=1, duration_ms=0)
            )
            return finish("failed", steps[0], steps)

        steps: List[str] = []
        context: Dict[str, object] = {
            "workflow_name": workflow.name,
            "last_output": "",
            "last_status": "success",
            "approved_node_ids": set(),
        }
        if initial_context and isinstance(initial_context, dict):
            context.update(initial_context)
            approved_nodes = context.get("approved_node_ids")
            if isinstance(approved_nodes, list):
                context["approved_node_ids"] = {
                    str(item).strip() for item in approved_nodes if str(item).strip()
                }
            if not isinstance(context.get("approved_node_ids"), set):
                context["approved_node_ids"] = set()

        visit_count: Dict[str, int] = {}
        current_node = start_node

        while current_node:
            if cancel_check and cancel_check():
                message = "Run cancelled by user."
                steps.append(message)
                timeline.append(
                    self._timeline_event(
                        current_node.id,
                        current_node.name,
                        "cancelled",
                        message,
                        attempt=1,
                        duration_ms=0,
                        context=context,
                    )
                )
                return finish("cancelled", message, steps)

            visit_count[current_node.id] = visit_count.get(current_node.id, 0) + 1
            if visit_count[current_node.id] > 3:
                message = (
                    f"Node '{current_node.name}' was visited too many times. "
                    "Possible loop detected."
                )
                steps.append(message)
                timeline.append(
                    self._timeline_event(
                        current_node.id,
                        current_node.name,
                        "failed",
                        message,
                        attempt=visit_count[current_node.id],
                        duration_ms=0,
                        context=context,
                    )
                )
                return finish(
                    "failed",
                    message,
                    steps,
                    last_failed_node_id=current_node.id,
                    last_failed_node_name=current_node.name,
                )

            try:
                policy = self._resolve_node_execution_policy(current_node, graph_settings)
                outcome = self._execute_node_with_policy(
                    node=current_node,
                    context=context,
                    outgoing_map=outgoing_map,
                    policy=policy,
                    cancel_check=cancel_check,
                )
                step_logs = outcome["logs"]
                forced_next_id = outcome["forced_next_id"]
                attempts_used = outcome["attempts"]
                duration_ms = outcome["duration_ms"]
                steps.extend(step_logs)
                timeline.append(
                    self._timeline_event(
                        current_node.id,
                        current_node.name,
                        "success",
                        step_logs[-1] if step_logs else f"Node '{current_node.name}' completed.",
                        attempt=attempts_used,
                        duration_ms=duration_ms,
                        context=context,
                    )
                )
            except ApprovalRequiredError as approval:
                message = str(approval)
                steps.append(message)
                timeline.append(
                    self._timeline_event(
                        current_node.id,
                        current_node.name,
                        "waiting_approval",
                        message,
                        attempt=1,
                        duration_ms=0,
                        context=context,
                    )
                )
                return finish(
                    "waiting_approval",
                    message,
                    steps,
                    pending_approval_node_id=current_node.id,
                    pending_approval_node_name=current_node.name,
                )
            except Exception as error:
                if cancel_check and cancel_check():
                    cancel_message = f"Node '{current_node.name}' cancelled."
                    steps.append(cancel_message)
                    timeline.append(
                        self._timeline_event(
                            current_node.id,
                            current_node.name,
                            "cancelled",
                            cancel_message,
                            attempt=1,
                            duration_ms=0,
                            context=context,
                        )
                    )
                    return finish("cancelled", "Run cancelled by user.", steps)
                error_message = f"Node '{current_node.name}' failed: {error}"
                steps.append(error_message)
                timeline.append(
                    self._timeline_event(
                        current_node.id,
                        current_node.name,
                        "failed",
                        error_message,
                        attempt=1,
                        duration_ms=0,
                        context=context,
                    )
                )
                return finish(
                    "failed",
                    error_message,
                    steps,
                    last_failed_node_id=current_node.id,
                    last_failed_node_name=current_node.name,
                )

            if cancel_check and cancel_check():
                message = "Run cancelled by user."
                steps.append(message)
                timeline.append(
                    self._timeline_event(
                        current_node.id,
                        current_node.name,
                        "cancelled",
                        message,
                        attempt=1,
                        duration_ms=0,
                        context=context,
                    )
                )
                return finish("cancelled", message, steps)

            next_node = None
            if forced_next_id:
                next_node = node_map.get(forced_next_id)
                if not next_node:
                    message = f"Condition branch target '{forced_next_id}' was not found."
                    steps.append(message)
                    timeline.append(
                        self._timeline_event(
                            current_node.id,
                            current_node.name,
                            "failed",
                            message,
                            attempt=1,
                            duration_ms=0,
                            context=context,
                        )
                    )
                    return finish(
                        "failed",
                        message,
                        steps,
                        last_failed_node_id=current_node.id,
                        last_failed_node_name=current_node.name,
                    )
            else:
                outgoing = outgoing_map.get(current_node.id, [])
                if outgoing:
                    next_node = node_map.get(outgoing[0].target_node_id)

            current_node = next_node

        summary = f"Executed {len(steps)} step(s) successfully."
        timeline.append(
            self._timeline_event(
                "",
                "Workflow",
                "success",
                summary,
                attempt=1,
                duration_ms=0,
                context=context,
            )
        )
        return finish("success", summary, steps)

    def _execute_node_with_policy(
        self,
        node: CanvasNode,
        context: Dict[str, object],
        outgoing_map: Dict[str, List[CanvasEdge]],
        policy: Dict[str, float],
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, object]:
        retry_max = int(policy.get("retry_max", 0))
        backoff_ms = int(policy.get("retry_backoff_ms", 250))
        timeout_sec = float(policy.get("timeout_sec", 0.0))
        total_attempts = max(1, retry_max + 1)
        attempt_index = 1
        last_error: Exception | None = None

        while attempt_index <= total_attempts:
            if cancel_check and cancel_check():
                raise RuntimeError("Run cancelled by user.")

            started = time.perf_counter()
            try:
                logs, forced_next_id = self._execute_node(
                    node=node,
                    context=context,
                    outgoing_map=outgoing_map,
                    cancel_check=cancel_check,
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                if timeout_sec > 0 and duration_ms > int(timeout_sec * 1000):
                    raise TimeoutError(
                        f"Node exceeded timeout ({duration_ms}ms > {int(timeout_sec * 1000)}ms)."
                    )
                if attempt_index > 1:
                    logs = [
                        f"Node '{node.name}' succeeded on retry attempt {attempt_index}.",
                        *logs,
                    ]
                return {
                    "logs": logs,
                    "forced_next_id": forced_next_id,
                    "attempts": attempt_index,
                    "duration_ms": duration_ms,
                }
            except ApprovalRequiredError:
                raise
            except Exception as error:
                last_error = error
                if attempt_index >= total_attempts:
                    break
                if cancel_check and cancel_check():
                    raise RuntimeError("Run cancelled by user.") from error
                delay = (backoff_ms * attempt_index) / 1000.0
                time.sleep(max(0.0, delay))
                attempt_index += 1
                continue

        raise RuntimeError(
            f"{last_error or 'Node failed'} after {total_attempts} attempt(s)."
        )

    def _execute_node(
        self,
        node: CanvasNode,
        context: Dict[str, object],
        outgoing_map: Dict[str, List[CanvasEdge]],
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Tuple[List[str], Optional[str]]:
        node_type = node.node_type.strip().lower()

        if "trigger" in node_type:
            return self._execute_trigger_node(node, context), None

        if "condition" in node_type:
            return self._execute_condition_node(node, context, outgoing_map)

        if "ai" in node_type:
            return self._execute_ai_node(node, context), None

        return self._execute_action_node(node, context, cancel_check=cancel_check), None

    def _execute_trigger_node(self, node: CanvasNode, context: Dict[str, object]) -> List[str]:
        parsed = self._parse_directives(node.detail)
        config = dict(parsed)
        config.update(node.config)

        mode = str(config.get("trigger_mode", "")).strip().lower()
        value = str(config.get("trigger_value", "")).strip()
        detail_text = str(node.detail).strip()
        detail_lower = detail_text.lower()

        if not mode:
            if detail_lower.startswith("trigger:manual"):
                mode = "manual"
            elif detail_lower.startswith("schedule:"):
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

        mode = mode or "manual"

        if mode == "schedule_interval":
            interval_seconds = self._parse_positive_float(value, 0.0)
            if interval_seconds <= 0:
                raise ValueError(
                    f"Trigger node '{node.name}' needs a positive interval in seconds."
                )
            message = (
                f"Trigger node '{node.name}' fired on interval "
                f"{int(round(interval_seconds))}s."
            )
        elif mode == "cron":
            cron_expr = value or str(config.get("cron", "")).strip()
            if not self._looks_like_cron(cron_expr):
                raise ValueError(
                    f"Trigger node '{node.name}' has invalid cron expression '{cron_expr}'."
                )
            value = cron_expr
            message = f"Trigger node '{node.name}' fired on cron '{cron_expr}'."
        elif mode == "webhook":
            endpoint = value or "/incoming"
            value = endpoint
            message = (
                f"Trigger node '{node.name}' received webhook event at '{endpoint}'."
            )
        elif mode == "file_watch":
            watched_path = value or "/tmp"
            value = watched_path
            message = (
                f"Trigger node '{node.name}' detected file change at '{watched_path}'."
            )
        else:
            mode = "manual"
            message = f"Trigger node '{node.name}' activated manually."

        context["trigger_mode"] = mode
        context["trigger_value"] = value
        context["last_output"] = message
        context["last_status"] = "success"
        return [message]

    def _execute_condition_node(
        self,
        node: CanvasNode,
        context: Dict[str, object],
        outgoing_map: Dict[str, List[CanvasEdge]],
    ) -> Tuple[List[str], Optional[str]]:
        expression = str(node.config.get("expression", "")).strip() or node.detail.strip()
        result = self._evaluate_condition(expression, context.get("last_output", ""))

        outcome_text = "true" if result else "false"
        logs = [f"Condition node '{node.name}' evaluated to {outcome_text}."]

        branch_target_id = self._choose_condition_edge(
            outgoing=outgoing_map.get(node.id, []),
            condition_result=result,
        )
        if branch_target_id:
            logs.append(f"Condition branch selected: {outcome_text}.")
            context["last_output"] = outcome_text
            context["last_status"] = "success"
            return logs, branch_target_id

        logs.append("Condition had no matching branch. Continuing default flow.")
        context["last_output"] = outcome_text
        context["last_status"] = "success"
        return logs, None

    def _execute_ai_node(self, node: CanvasNode, context: Dict[str, object]) -> List[str]:
        parsed = self._parse_directives(node.detail)
        config = dict(parsed)
        config.update(node.config)

        prompt = config.get("prompt", "").strip()
        if not prompt:
            prompt = node.summary.strip()
        if not prompt:
            prompt = "Process the latest workflow context."

        prior_output = str(context.get("last_output", "")).strip()
        if prior_output:
            prompt = f"{prompt}\n\nContext from previous node:\n{prior_output}"

        system_prompt = str(config.get("system", "")).strip()
        bot_chain = self._parse_bot_chain(config.get("bot_chain", ""))
        single_bot_name = str(config.get("bot", "")).strip()

        logs = []
        if bot_chain:
            response = self._run_bot_chain(bot_chain, prompt, config, logs, system_prompt)
        elif single_bot_name:
            bot = self.bot_store.get_bot_by_name(single_bot_name)
            if not bot:
                raise ValueError(f"Bot '{single_bot_name}' was not found.")
            response = self.ai_service.generate(
                prompt=prompt,
                node_config=config,
                bot=bot,
                system_prompt=system_prompt,
            )
            logs.append(
                f"AI node '{node.name}' executed using bot '{bot.name}' on provider '{bot.provider}'."
            )
        else:
            response = self.ai_service.generate(
                prompt=prompt,
                node_config=config,
                system_prompt=system_prompt,
            )
            logs.append(f"AI node '{node.name}' executed with configured provider.")

        context["last_output"] = response
        context["last_status"] = "success"
        logs.append(f"AI output: {self._truncate(response, 220)}")
        return logs

    def _execute_action_node(
        self,
        node: CanvasNode,
        context: Dict[str, object],
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> List[str]:
        parsed = self._parse_directives(node.detail)
        config = dict(parsed)
        config.update(node.config)
        app_settings = self.settings_store.load_settings()

        def app_value(key: str) -> str:
            return str(app_settings.get(key, "")).strip()

        integration = str(config.get("integration", "")).strip().lower() or "standard"
        integration_definition = self.integration_registry.get_integration(integration)
        if not integration_definition:
            raise ValueError(f"Integration '{integration}' is not installed.")
        integration_handler = str(
            integration_definition.get("handler", integration)
        ).strip().lower() or integration

        output = str(context.get("last_output", ""))

        if integration_handler == "handoff":
            chain = self._parse_bot_chain(str(config.get("bot_chain", "")))
            if not chain:
                raise ValueError("Action handoff requires 'bot_chain: BotA > BotB'.")
            logs: List[str] = []
            handoff_response = self._run_bot_chain(
                chain,
                output or "Continue this workflow.",
                config,
                logs,
                system_prompt=str(config.get("system", "")).strip(),
            )
            logs.append(f"Action handoff output: {self._truncate(handoff_response, 220)}")
            context["last_output"] = handoff_response
            context["last_status"] = "success"
            return [f"Action node '{node.name}' completed via bot handoff.", *logs]

        if integration_handler == "http_post":
            url = str(config.get("url", "")).strip()
            if not url:
                raise ValueError("Action http_post requires a 'url:' value.")
            payload_text = str(config.get("payload", "")).strip() or output or "{}"
            timeout_seconds = self._parse_positive_float(config.get("timeout_sec", ""), 45.0)
            response_text = self._integration_http_post(
                url,
                payload_text,
                timeout_seconds=timeout_seconds,
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent HTTP POST to {url}.",
                f"HTTP response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "http_request":
            url = str(config.get("url", "")).strip()
            if not url:
                raise ValueError("Action http_request requires a 'url:' value.")
            method = str(config.get("method", "")).strip().upper() or "POST"
            payload_text = str(config.get("payload", "")).strip() or output
            headers = self._headers_from_config(config)
            api_key = str(config.get("api_key", "")).strip()
            if api_key and "authorization" not in {item.lower() for item in headers.keys()}:
                headers["Authorization"] = f"Bearer {api_key}"
                headers.setdefault("x-api-key", api_key)
                headers.setdefault("api-key", api_key)
            timeout_seconds = self._parse_positive_float(config.get("timeout_sec", ""), 45.0)
            response_text = self._integration_http_request(
                method=method,
                url=url,
                payload_text=payload_text,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent {method} request to {url}.",
                f"HTTP response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "slack_webhook":
            webhook_url = (
                str(config.get("webhook_url", "")).strip()
                or str(config.get("url", "")).strip()
                or str(app_settings.get("slack_webhook_url", "")).strip()
                or os.environ.get("SLACK_WEBHOOK_URL", "").strip()
            )
            if not webhook_url:
                raise ValueError("Action slack_webhook requires a 'webhook_url:' value.")
            payload = {
                "text": str(config.get("text", "")).strip() or output or "Workflow message",
            }
            username = str(config.get("username", "")).strip()
            if username:
                payload["username"] = username
            icon_emoji = str(config.get("icon_emoji", "")).strip()
            if icon_emoji:
                payload["icon_emoji"] = icon_emoji
            response_text = self._integration_http_post(
                webhook_url,
                json.dumps(payload),
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text or "ok"
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' posted to Slack webhook.",
                f"Slack response: {self._truncate(response_text or 'ok', 220)}",
            ]

        if integration_handler == "discord_webhook":
            webhook_url = (
                str(config.get("webhook_url", "")).strip()
                or str(config.get("url", "")).strip()
                or str(app_settings.get("discord_webhook_url", "")).strip()
                or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
            )
            if not webhook_url:
                raise ValueError("Action discord_webhook requires a 'webhook_url:' value.")
            payload = {
                "content": str(config.get("content", "")).strip() or output or "Workflow message",
            }
            username = str(config.get("username", "")).strip()
            if username:
                payload["username"] = username
            response_text = self._integration_http_post(
                webhook_url,
                json.dumps(payload),
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text or "ok"
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' posted to Discord webhook.",
                f"Discord response: {self._truncate(response_text or 'ok', 220)}",
            ]

        if integration_handler == "teams_webhook":
            webhook_url = (
                str(config.get("webhook_url", "")).strip()
                or str(config.get("url", "")).strip()
                or str(app_settings.get("teams_webhook_url", "")).strip()
                or os.environ.get("TEAMS_WEBHOOK_URL", "").strip()
            )
            if not webhook_url:
                raise ValueError("Action teams_webhook requires a 'webhook_url:' value.")
            payload = {
                "text": str(config.get("text", "")).strip() or output or "Workflow message",
            }
            response_text = self._integration_http_post(
                webhook_url,
                json.dumps(payload),
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text or "ok"
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' posted to Teams webhook.",
                f"Teams response: {self._truncate(response_text or 'ok', 220)}",
            ]

        if integration_handler == "openweather_current":
            api_key = str(config.get("api_key", "")).strip() or os.environ.get(
                "OPENWEATHER_API_KEY",
            ).strip()
            if not api_key:
                api_key = str(app_settings.get("openweather_api_key", "")).strip()
            location = (
                str(config.get("location", "")).strip()
                or str(app_settings.get("openweather_default_location", "")).strip()
            )
            units = str(config.get("units", "")).strip() or "metric"
            if not api_key:
                raise ValueError("Action openweather_current requires an 'api_key:' value.")
            if not location:
                raise ValueError("Action openweather_current requires a 'location:' value.")
            query = urllib.parse.urlencode(
                {"q": location, "appid": api_key, "units": units},
                quote_via=urllib.parse.quote_plus,
            )
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?{query}"
            response_text = self._integration_http_get(
                weather_url,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 20.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' fetched weather for {location}.",
                f"Weather response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "google_apps_script":
            script_url = (
                str(config.get("script_url", "")).strip()
                or str(config.get("url", "")).strip()
                or str(app_settings.get("google_apps_script_url", "")).strip()
                or os.environ.get("GOOGLE_APPS_SCRIPT_URL", "").strip()
            )
            if not script_url:
                raise ValueError("Action google_apps_script requires a 'script_url:' value.")
            payload_text = str(config.get("payload", "")).strip()
            if not payload_text:
                payload_text = json.dumps(
                    {
                        "text": output,
                        "workflow_name": str(context.get("workflow_name", "")),
                        "node_name": node.name,
                    }
                )
            response_text = self._integration_http_post(
                script_url,
                payload_text,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent payload to Google Apps Script.",
                f"Script response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "telegram_bot":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            token = str(config.get("api_key", "")).strip() or os.environ.get(
                "TELEGRAM_BOT_TOKEN", ""
            ).strip()
            if not token:
                token = app_value("telegram_bot_token")
            chat_id = str(config.get("chat_id", "")).strip() or str(payload.get("chat_id", "")).strip()
            if not chat_id:
                chat_id = app_value("telegram_default_chat_id")
            text = (
                str(config.get("message", "")).strip()
                or str(payload.get("text", "")).strip()
                or output
                or "Workflow message"
            )
            if not token:
                raise ValueError("Action telegram_bot requires an 'api_key:' bot token.")
            if not chat_id:
                raise ValueError("Action telegram_bot requires a 'chat_id:' value.")
            endpoint = (
                str(config.get("url", "")).strip()
                or f"https://api.telegram.org/bot{token}/sendMessage"
            )
            request_payload = {"chat_id": chat_id, "text": text}
            response_text = self._integration_http_request(
                method="POST",
                url=endpoint,
                payload_text=json.dumps(request_payload),
                headers={"Content-Type": "application/json"},
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent Telegram message to chat '{chat_id}'.",
                f"Telegram response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "gmail_send":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            bearer = str(config.get("api_key", "")).strip()
            if not bearer:
                bearer = app_value("gmail_api_key")
            to_address = str(config.get("to", "")).strip() or str(payload.get("to", "")).strip()
            subject = (
                str(config.get("subject", "")).strip()
                or str(payload.get("subject", "")).strip()
                or "Workflow Message"
            )
            from_address = str(config.get("from", "")).strip() or str(payload.get("from", "")).strip() or "me"
            if from_address == "me":
                configured_from = app_value("gmail_from_address")
                if configured_from:
                    from_address = configured_from
            body_text = (
                str(config.get("message", "")).strip()
                or str(payload.get("text", "")).strip()
                or str(payload.get("body", "")).strip()
                or output
                or "Workflow message"
            )
            if not bearer:
                raise ValueError("Action gmail_send requires an OAuth bearer token in 'api_key:'.")
            if not to_address:
                raise ValueError("Action gmail_send requires a 'to:' address.")
            raw_email = self._build_simple_email(
                from_address=from_address,
                to_address=to_address,
                subject=subject,
                body=body_text,
            )
            encoded_email = base64.urlsafe_b64encode(raw_email.encode("utf-8")).decode("utf-8")
            endpoint = (
                str(config.get("url", "")).strip()
                or "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
            )
            payload = {"raw": encoded_email}
            response_text = self._integration_http_request(
                method="POST",
                url=endpoint,
                payload_text=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {bearer}",
                },
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent Gmail message to {to_address}.",
                f"Gmail response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "google_sheets":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            bearer = str(config.get("api_key", "")).strip()
            if not bearer:
                bearer = app_value("google_sheets_api_key")
            spreadsheet_id = (
                str(config.get("spreadsheet_id", "")).strip()
                or str(payload.get("spreadsheet_id", "")).strip()
            )
            if not spreadsheet_id:
                spreadsheet_id = app_value("google_sheets_spreadsheet_id")
            range_value = str(config.get("range", "")).strip() or str(payload.get("range", "")).strip()
            if not range_value:
                range_value = app_value("google_sheets_range")
            if not bearer:
                raise ValueError("Action google_sheets requires OAuth bearer token in 'api_key:'.")
            if not spreadsheet_id:
                raise ValueError("Action google_sheets requires 'spreadsheet_id:'.")
            if not range_value:
                raise ValueError("Action google_sheets requires 'range:'.")
            if payload_text:
                payload_obj = self._json_payload_from_text(payload_text)
            else:
                payload_obj = {"values": [[output or ""]]}
            endpoint = (
                str(config.get("url", "")).strip()
                or (
                    "https://sheets.googleapis.com/v4/spreadsheets/"
                    f"{spreadsheet_id}/values/{urllib.parse.quote(range_value, safe='!:$')}:append"
                    "?valueInputOption=USER_ENTERED"
                )
            )
            response_text = self._integration_http_request(
                method="POST",
                url=endpoint,
                payload_text=json.dumps(payload_obj),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {bearer}",
                },
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' wrote to Google Sheets range '{range_value}'.",
                f"Sheets response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler in {
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "google_calendar_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "gitlab_api",
        }:
            url = str(config.get("url", "")).strip()
            method = str(config.get("method", "")).strip().upper() or "POST"
            payload_text = str(config.get("payload", "")).strip() or output
            api_key = str(config.get("api_key", "")).strip()
            if not url:
                url_map = {
                    "notion_api": "notion_api_url",
                    "airtable_api": "airtable_api_url",
                    "hubspot_api": "hubspot_api_url",
                    "stripe_api": "stripe_api_url",
                    "github_rest": "github_api_url",
                    "google_calendar_api": "google_calendar_api_url",
                    "outlook_graph": "outlook_api_url",
                    "jira_api": "jira_api_url",
                    "asana_api": "asana_api_url",
                    "clickup_api": "clickup_api_url",
                    "trello_api": "trello_api_url",
                    "monday_api": "monday_api_url",
                    "zendesk_api": "zendesk_api_url",
                    "pipedrive_api": "pipedrive_api_url",
                    "salesforce_api": "salesforce_api_url",
                    "gitlab_api": "gitlab_api_url",
                }
                url = app_value(url_map.get(integration_handler, ""))
            if not api_key:
                key_map = {
                    "notion_api": "notion_api_key",
                    "airtable_api": "airtable_api_key",
                    "hubspot_api": "hubspot_api_key",
                    "stripe_api": "stripe_api_key",
                    "github_rest": "github_api_key",
                    "google_calendar_api": "google_calendar_api_key",
                    "outlook_graph": "outlook_api_key",
                    "jira_api": "jira_api_key",
                    "asana_api": "asana_api_key",
                    "clickup_api": "clickup_api_key",
                    "trello_api": "trello_api_key",
                    "monday_api": "monday_api_key",
                    "zendesk_api": "zendesk_api_key",
                    "pipedrive_api": "pipedrive_api_key",
                    "salesforce_api": "salesforce_api_key",
                    "gitlab_api": "gitlab_api_key",
                }
                api_key = app_value(key_map.get(integration_handler, ""))
            if not url:
                raise ValueError(f"Action {integration_handler} requires a 'url:' value.")
            if not api_key:
                raise ValueError(f"Action {integration_handler} requires an 'api_key:' value.")
            headers = self._headers_from_config(config)
            headers.setdefault("Authorization", f"Bearer {api_key}")
            if integration_handler == "notion_api":
                headers.setdefault("Notion-Version", str(config.get("notion_version", "2022-06-28")).strip())
            response_text = self._integration_http_request(
                method=method,
                url=url,
                payload_text=payload_text,
                headers=headers,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 45.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' completed {integration_handler} request.",
                f"Response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "linear_api":
            api_key = str(config.get("api_key", "")).strip()
            if not api_key:
                api_key = app_value("linear_api_key")
            query = str(config.get("query", "")).strip()
            payload_text = str(config.get("payload", "")).strip()
            endpoint = str(config.get("url", "")).strip() or "https://api.linear.app/graphql"
            if not api_key:
                raise ValueError("Action linear_api requires an 'api_key:' value.")
            if not query and not payload_text:
                raise ValueError("Action linear_api requires 'query:' or 'payload:'.")
            if payload_text:
                payload = self._json_payload_from_text(payload_text)
            else:
                payload = {"query": query}
            response_text = self._integration_http_request(
                method="POST",
                url=endpoint,
                payload_text=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": api_key,
                },
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 45.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' completed Linear GraphQL request.",
                f"Linear response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "twilio_sms":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            account_sid = str(config.get("account_sid", "")).strip()
            auth_token = str(config.get("auth_token", "")).strip()
            from_number = str(config.get("from", "")).strip() or str(payload.get("from", "")).strip()
            to_number = str(config.get("to", "")).strip() or str(payload.get("to", "")).strip()
            message = (
                str(config.get("message", "")).strip()
                or str(payload.get("message", "")).strip()
                or output
                or "Workflow message"
            )
            if not account_sid:
                account_sid = str(payload.get("account_sid", "")).strip()
            if not auth_token:
                auth_token = str(payload.get("auth_token", "")).strip()
            if not account_sid:
                account_sid = app_value("twilio_account_sid")
            if not auth_token:
                auth_token = app_value("twilio_auth_token")
            if not from_number:
                from_number = app_value("twilio_from_number")
            if not account_sid:
                raise ValueError("Action twilio_sms requires 'account_sid:'.")
            if not auth_token:
                raise ValueError("Action twilio_sms requires 'auth_token:'.")
            if not from_number or not to_number:
                raise ValueError("Action twilio_sms requires both 'from:' and 'to:'.")
            endpoint = (
                str(config.get("url", "")).strip()
                or f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            )
            response_text = self._integration_http_form_post(
                endpoint,
                form_values={"From": from_number, "To": to_number, "Body": message},
                basic_auth_username=account_sid,
                basic_auth_password=auth_token,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent Twilio SMS to {to_number}.",
                f"Twilio response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "resend_email":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            api_key = str(config.get("api_key", "")).strip()
            if not api_key:
                api_key = app_value("resend_api_key")
            from_address = str(config.get("from", "")).strip() or str(payload.get("from", "")).strip()
            if not from_address:
                from_address = app_value("resend_from_address")
            to_address = str(config.get("to", "")).strip() or str(payload.get("to", "")).strip()
            subject = (
                str(config.get("subject", "")).strip()
                or str(payload.get("subject", "")).strip()
                or "Workflow Message"
            )
            body_text = (
                str(config.get("message", "")).strip()
                or str(payload.get("text", "")).strip()
                or output
                or "Workflow message"
            )
            if not api_key:
                raise ValueError("Action resend_email requires 'api_key:'.")
            if not from_address or not to_address:
                raise ValueError("Action resend_email requires both 'from:' and 'to:'.")
            endpoint = str(config.get("url", "")).strip() or "https://api.resend.com/emails"
            payload = {
                "from": from_address,
                "to": [to_address],
                "subject": subject,
                "text": body_text,
            }
            response_text = self._integration_http_request(
                method="POST",
                url=endpoint,
                payload_text=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent email via Resend to {to_address}.",
                f"Resend response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "mailgun_email":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            api_key = str(config.get("api_key", "")).strip()
            if not api_key:
                api_key = app_value("mailgun_api_key")
            domain = str(config.get("domain", "")).strip() or str(payload.get("domain", "")).strip()
            if not domain:
                domain = app_value("mailgun_domain")
            from_address = str(config.get("from", "")).strip() or str(payload.get("from", "")).strip()
            if not from_address:
                from_address = app_value("mailgun_from_address")
            to_address = str(config.get("to", "")).strip() or str(payload.get("to", "")).strip()
            subject = (
                str(config.get("subject", "")).strip()
                or str(payload.get("subject", "")).strip()
                or "Workflow Message"
            )
            body_text = (
                str(config.get("message", "")).strip()
                or str(payload.get("text", "")).strip()
                or output
                or "Workflow message"
            )
            if not api_key:
                raise ValueError("Action mailgun_email requires 'api_key:'.")
            if not domain:
                raise ValueError("Action mailgun_email requires 'domain:'.")
            if not from_address or not to_address:
                raise ValueError("Action mailgun_email requires both 'from:' and 'to:'.")
            endpoint = (
                str(config.get("url", "")).strip()
                or f"https://api.mailgun.net/v3/{domain}/messages"
            )
            response_text = self._integration_http_form_post(
                endpoint,
                form_values={
                    "from": from_address,
                    "to": to_address,
                    "subject": subject,
                    "text": body_text,
                },
                basic_auth_username="api",
                basic_auth_password=api_key,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 30.0),
            )
            context["last_output"] = response_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' sent email via Mailgun to {to_address}.",
                f"Mailgun response: {self._truncate(response_text, 220)}",
            ]

        if integration_handler == "postgres_sql":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._payload_mapping(payload_text)
            sql = self._coalesce_config_value(config, payload, ["sql", "query"]) or output
            connection_url = self._coalesce_config_value(
                config,
                payload,
                ["connection_url", "url", "endpoint", "request_url"],
            )
            if not connection_url:
                connection_url = app_value("postgres_connection_url")
            if not sql:
                raise ValueError("Action postgres_sql requires 'sql:'.")
            if not connection_url:
                raise ValueError("Action postgres_sql requires 'connection_url:'.")
            command = f'psql "{connection_url}" -At -c "{sql.replace(chr(34), chr(92) + chr(34))}"'
            result_text = self._integration_shell_command(
                command,
                "",
                cancel_check=cancel_check,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 60.0),
            )
            context["last_output"] = result_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' executed Postgres SQL.",
                f"Postgres result: {self._truncate(result_text, 220)}",
            ]

        if integration_handler == "mysql_sql":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._payload_mapping(payload_text)
            sql = self._coalesce_config_value(config, payload, ["sql", "query"]) or output
            connection_url = self._coalesce_config_value(
                config,
                payload,
                ["connection_url", "url", "endpoint", "request_url"],
            )
            if not connection_url:
                connection_url = app_value("mysql_connection_url")
            if not sql:
                raise ValueError("Action mysql_sql requires 'sql:'.")
            if not connection_url:
                raise ValueError("Action mysql_sql requires 'connection_url:'.")
            command = (
                f'mysql --uri="{connection_url}" --batch --raw --skip-column-names '
                f'-e "{sql.replace(chr(34), chr(92) + chr(34))}"'
            )
            result_text = self._integration_shell_command(
                command,
                "",
                cancel_check=cancel_check,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 60.0),
            )
            context["last_output"] = result_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' executed MySQL SQL.",
                f"MySQL result: {self._truncate(result_text, 220)}",
            ]

        if integration_handler == "sqlite_sql":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._json_payload_from_text(payload_text) if payload_text else {}
            db_path = str(config.get("path", "")).strip()
            if not db_path:
                db_path = str(payload.get("path", "")).strip()
            sql = str(config.get("sql", "")).strip() or str(payload.get("sql", "")).strip() or output
            if not db_path:
                raise ValueError("Action sqlite_sql requires 'path:'.")
            if not sql:
                raise ValueError("Action sqlite_sql requires 'sql:'.")
            result_text = self._integration_sqlite_query(db_path, sql)
            context["last_output"] = result_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' executed SQLite SQL.",
                f"SQLite result: {self._truncate(result_text, 220)}",
            ]

        if integration_handler == "redis_command":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._payload_mapping(payload_text)
            command = self._coalesce_config_value(config, payload, ["command", "query"])
            redis_url = self._coalesce_config_value(
                config,
                payload,
                ["connection_url", "url", "endpoint", "request_url"],
            )
            if not redis_url:
                redis_url = app_value("redis_connection_url")
            if not command:
                raise ValueError("Action redis_command requires 'command:'.")
            prefix = "redis-cli"
            if redis_url:
                prefix = f'redis-cli -u "{redis_url}"'
            result_text = self._integration_shell_command(
                f"{prefix} {command}",
                "",
                cancel_check=cancel_check,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 45.0),
            )
            context["last_output"] = result_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' executed Redis command.",
                f"Redis result: {self._truncate(result_text, 220)}",
            ]

        if integration_handler == "s3_cli":
            payload_text = str(config.get("payload", "")).strip()
            payload = self._payload_mapping(payload_text)
            command = self._coalesce_config_value(config, payload, ["command", "query"]) or "s3 ls"
            result_text = self._integration_shell_command(
                f"aws {command}",
                "",
                cancel_check=cancel_check,
                timeout_seconds=self._parse_positive_float(config.get("timeout_sec", ""), 60.0),
            )
            context["last_output"] = result_text
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' executed AWS CLI command.",
                f"AWS result: {self._truncate(result_text, 220)}",
            ]

        if integration_handler == "file_append":
            path_value = str(config.get("path", "")).strip()
            if not path_value:
                raise ValueError("Action file_append requires a 'path:' value.")
            content = str(config.get("content", "")).strip() or output
            written_path = self._integration_file_append(path_value, content)
            context["last_output"] = content
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' appended output to {written_path}.",
            ]

        if integration_handler == "shell_command":
            command = str(config.get("command", "")).strip()
            if not command:
                raise ValueError("Action shell_command requires a 'command:' value.")
            timeout_seconds = self._parse_positive_float(config.get("timeout_sec", ""), 60.0)
            command_output = self._integration_shell_command(
                command,
                output,
                cancel_check=cancel_check,
                timeout_seconds=timeout_seconds,
            )
            context["last_output"] = command_output
            context["last_status"] = "success"
            return [
                f"Action node '{node.name}' executed shell command.",
                f"Command output: {self._truncate(command_output, 220)}",
            ]

        if integration_handler == "approval_gate":
            configured_message = str(config.get("approval_message", "")).strip()
            message = (
                configured_message
                or node.summary.strip()
                or f"Approval required for node '{node.name}'."
            )
            approved_nodes = context.get("approved_node_ids", set())
            if isinstance(approved_nodes, set) and node.id in approved_nodes:
                context["last_output"] = "approved"
                context["last_status"] = "success"
                return [
                    f"Approval gate '{node.name}' was approved. Continuing execution.",
                ]
            raise ApprovalRequiredError(
                node.id,
                node.name,
                message,
            )

        message = f"Action node '{node.name}' completed."
        if output:
            message = f"Action node '{node.name}' completed with context payload."

        context["last_output"] = output
        context["last_status"] = "success"
        return [message]

    def execute_action_node_for_test(
        self,
        node: CanvasNode,
        input_context: str = "",
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Tuple[List[str], str]:
        context = {
            "workflow_name": "Integration Test",
            "last_output": input_context,
            "last_status": "success",
        }
        logs = self._execute_action_node(node, context, cancel_check=cancel_check)
        output = str(context.get("last_output", "")).strip()
        return logs, output

    def _run_bot_chain(
        self,
        bot_names: List[str],
        initial_prompt: str,
        config: Dict[str, Any],
        logs: List[str],
        system_prompt: str = "",
    ) -> str:
        current_prompt = initial_prompt
        last_output = ""

        for bot_name in bot_names:
            bot = self.bot_store.get_bot_by_name(bot_name)
            if not bot:
                raise ValueError(f"Bot '{bot_name}' was not found for bot chain execution.")

            last_output = self.ai_service.generate(
                prompt=current_prompt,
                node_config=config,
                bot=bot,
                system_prompt=system_prompt,
            )
            logs.append(
                f"Bot chain step '{bot.name}' completed on provider '{bot.provider}'."
            )
            current_prompt = (
                "Take this output from the previous bot and continue:\n\n"
                f"{last_output}"
            )

        return last_output

    def _evaluate_condition(self, expression: str, input_text: str) -> bool:
        text = str(input_text).strip()
        expr = expression.strip()

        if not expr:
            return bool(text)

        lower_expr = expr.lower()
        lower_text = text.lower()

        if lower_expr in {"true", "yes", "1"}:
            return True
        if lower_expr in {"false", "no", "0"}:
            return False

        if lower_expr.startswith("contains:"):
            target = lower_expr.split(":", 1)[1].strip()
            return bool(target) and target in lower_text

        if lower_expr.startswith("equals:"):
            target = lower_expr.split(":", 1)[1].strip()
            return lower_text == target

        if lower_expr.startswith("not_contains:"):
            target = lower_expr.split(":", 1)[1].strip()
            return bool(target) and target not in lower_text

        if lower_expr.startswith("regex:"):
            pattern = expr.split(":", 1)[1].strip()
            if not pattern:
                return False
            return re.search(pattern, text) is not None

        if lower_expr.startswith("min_len:"):
            raw_threshold = lower_expr.split(":", 1)[1].strip()
            if not raw_threshold:
                return False
            try:
                threshold = int(raw_threshold)
            except ValueError:
                return False
            return len(text) >= threshold

        return bool(text)

    def _choose_condition_edge(
        self, outgoing: List[CanvasEdge], condition_result: bool
    ) -> Optional[str]:
        expected = "true" if condition_result else "false"

        for edge in outgoing:
            if edge.condition == expected:
                return edge.target_node_id

        unlabeled = [edge for edge in outgoing if not edge.condition]
        if condition_result:
            if unlabeled:
                return unlabeled[0].target_node_id
        else:
            if len(unlabeled) > 1:
                return unlabeled[1].target_node_id
            if unlabeled:
                return unlabeled[0].target_node_id

        if outgoing:
            return outgoing[0].target_node_id

        return None

    def _parse_nodes(self, graph: Dict) -> List[CanvasNode]:
        parsed_nodes: List[CanvasNode] = []
        for item in graph.get("nodes", []):
            if not isinstance(item, dict):
                continue
            node = CanvasNode.from_dict(item)
            if node.id:
                parsed_nodes.append(node)
        return parsed_nodes

    def _parse_edges(self, graph: Dict) -> List[CanvasEdge]:
        parsed_edges: List[CanvasEdge] = []
        for item in graph.get("edges", []):
            if not isinstance(item, dict):
                continue
            edge = CanvasEdge.from_dict(item)
            if edge.source_node_id and edge.target_node_id:
                parsed_edges.append(edge)
        return parsed_edges

    def _build_outgoing_map(self, edges: List[CanvasEdge]) -> Dict[str, List[CanvasEdge]]:
        outgoing_map: Dict[str, List[CanvasEdge]] = {}
        for edge in edges:
            outgoing_map.setdefault(edge.source_node_id, []).append(edge)
        return outgoing_map

    def _build_incoming_count(
        self, nodes: List[CanvasNode], edges: List[CanvasEdge]
    ) -> Dict[str, int]:
        count_map = {node.id: 0 for node in nodes}
        for edge in edges:
            if edge.target_node_id in count_map:
                count_map[edge.target_node_id] += 1
        return count_map

    def _find_start_node(
        self, nodes: List[CanvasNode], incoming_count: Dict[str, int]
    ) -> Optional[CanvasNode]:
        trigger_starts = [
            node
            for node in nodes
            if node.node_type.lower().startswith("trigger")
            and incoming_count.get(node.id, 0) == 0
        ]
        if trigger_starts:
            return trigger_starts[0]

        root_starts = [node for node in nodes if incoming_count.get(node.id, 0) == 0]
        if root_starts:
            return root_starts[0]

        return nodes[0] if nodes else None

    def _parse_directives(self, text: str) -> Dict[str, str]:
        directives: Dict[str, str] = {}

        for line in text.splitlines():
            raw = line.strip()
            if not raw or ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            directives[key.strip().lower()] = value.strip()

        return directives

    def _resolve_node_execution_policy(
        self,
        node: CanvasNode,
        graph_settings: Dict[str, object],
    ) -> Dict[str, float]:
        graph_policy = graph_settings if isinstance(graph_settings, dict) else {}
        node_policy = node.config.get("execution", {})
        if not isinstance(node_policy, dict):
            node_policy = {}
        defaults = self._node_execution_defaults(node)

        retry_max = self._parse_non_negative_int(
            node_policy.get(
                "retry_max",
                node.config.get(
                    "retry_max",
                    graph_policy.get("retry_max", defaults["retry_max"]),
                ),
            ),
            int(defaults["retry_max"]),
        )
        retry_backoff_ms = self._parse_non_negative_int(
            node_policy.get(
                "retry_backoff_ms",
                node.config.get(
                    "retry_backoff_ms",
                    graph_policy.get("retry_backoff_ms", defaults["retry_backoff_ms"]),
                ),
            ),
            int(defaults["retry_backoff_ms"]),
        )
        timeout_sec = self._parse_positive_float(
            node_policy.get(
                "timeout_sec",
                node.config.get(
                    "timeout_sec",
                    graph_policy.get("timeout_sec", defaults["timeout_sec"]),
                ),
            ),
            float(defaults["timeout_sec"]),
        )

        return {
            "retry_max": float(retry_max),
            "retry_backoff_ms": float(retry_backoff_ms),
            "timeout_sec": float(timeout_sec),
        }

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

    def _node_execution_defaults(self, node: CanvasNode) -> Dict[str, float]:
        node_kind = self._node_kind(node.node_type)
        integration = str(node.config.get("integration", "")).strip().lower()

        if node_kind == "trigger":
            return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 15.0}
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

    def _timeline_event(
        self,
        node_id: str,
        node_name: str,
        status: str,
        message: str,
        *,
        attempt: int,
        duration_ms: int,
        context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, str]:
        event = {
            "timestamp": self._timestamp(),
            "node_id": str(node_id).strip(),
            "node_name": str(node_name).strip(),
            "status": str(status).strip().lower(),
            "message": str(message).strip(),
            "attempt": str(max(1, int(attempt))),
            "duration_ms": str(max(0, int(duration_ms))),
        }
        if context and isinstance(context, dict):
            output_preview = str(context.get("last_output", "")).strip()
            if output_preview:
                event["output_preview"] = self._truncate(output_preview, 320)
            snapshot = self._context_snapshot_text(context)
            if snapshot:
                event["context_snapshot"] = snapshot
        return event

    def _context_snapshot_text(self, context: Dict[str, object]) -> str:
        snapshot: Dict[str, object] = {}
        for key, value in context.items():
            safe_key = str(key).strip()
            if not safe_key:
                continue
            if safe_key == "approved_node_ids":
                if isinstance(value, set):
                    snapshot[safe_key] = sorted(str(item) for item in value)
                elif isinstance(value, list):
                    snapshot[safe_key] = [str(item) for item in value]
                continue
            if safe_key == "last_output":
                snapshot[safe_key] = self._truncate(str(value), 320)
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                snapshot[safe_key] = value
            else:
                snapshot[safe_key] = str(value)
        try:
            return json.dumps(snapshot, indent=2, ensure_ascii=True)
        except Exception:
            return ""

    def _parse_non_negative_int(self, value: object, fallback: int) -> int:
        try:
            parsed = int(str(value).strip())
            return max(0, parsed)
        except (TypeError, ValueError):
            return max(0, fallback)

    def _parse_positive_float(self, value: object, fallback: float) -> float:
        try:
            parsed = float(str(value).strip())
            return max(0.0, parsed)
        except (TypeError, ValueError):
            return max(0.0, float(fallback))

    def _looks_like_cron(self, expression: str) -> bool:
        text = str(expression).strip()
        if not text:
            return False
        fields = [part for part in text.split() if part.strip()]
        if len(fields) not in {5, 6}:
            return False
        allowed = re.compile(r"^[\d\*/,\-\?LW#A-Za-z]+$")
        return all(bool(allowed.match(field)) for field in fields)

    def _parse_bot_chain(self, raw_value: str) -> List[str]:
        if not raw_value.strip():
            return []
        return [part.strip() for part in raw_value.split(">") if part.strip()]

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _json_payload_from_text(self, payload_text: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(payload_text)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            return {"text": payload_text}

    def _payload_mapping(self, payload_text: str) -> Dict[str, Any]:
        text = str(payload_text).strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
        return {}

    def _coalesce_config_value(
        self,
        config: Dict[str, Any],
        payload: Dict[str, Any],
        keys: List[str],
    ) -> str:
        for key in keys:
            value = str(config.get(key, "")).strip()
            if value:
                return value
        for key in keys:
            value = str(payload.get(key, "")).strip()
            if value:
                return value
        return ""

    def _headers_from_config(self, config: Dict[str, Any]) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        raw_headers = str(config.get("headers", "")).strip()
        if not raw_headers:
            return headers

        try:
            parsed = json.loads(raw_headers)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    header_name = str(key).strip()
                    if not header_name:
                        continue
                    headers[header_name] = str(value).strip()
                return headers
        except json.JSONDecodeError:
            pass

        for line in raw_headers.splitlines():
            item = line.strip()
            if not item or ":" not in item:
                continue
            key, value = item.split(":", 1)
            header_name = key.strip()
            if not header_name:
                continue
            headers[header_name] = value.strip()
        return headers

    def _integration_http_request(
        self,
        method: str,
        url: str,
        payload_text: str = "",
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 45.0,
    ) -> str:
        normalized_method = str(method).strip().upper() or "GET"
        merged_headers = {key: str(value) for key, value in (headers or {}).items() if str(key).strip()}

        data: Optional[bytes] = None
        if normalized_method in {"POST", "PUT", "PATCH", "DELETE"} and payload_text:
            if "Content-Type" in merged_headers:
                content_type = merged_headers.get("Content-Type", "")
            else:
                content_type = "application/json"
                merged_headers["Content-Type"] = content_type

            if "application/json" in content_type.lower():
                payload_obj = self._json_payload_from_text(payload_text)
                data = json.dumps(payload_obj).encode("utf-8")
            elif "application/x-www-form-urlencoded" in content_type.lower():
                form_pairs: Dict[str, str] = {}
                for line in payload_text.splitlines():
                    raw = line.strip()
                    if not raw:
                        continue
                    if ":" in raw:
                        key, value = raw.split(":", 1)
                    elif "=" in raw:
                        key, value = raw.split("=", 1)
                    else:
                        continue
                    normalized_key = key.strip()
                    if normalized_key:
                        form_pairs[normalized_key] = value.strip()
                data = urllib.parse.urlencode(form_pairs).encode("utf-8")
            else:
                data = payload_text.encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            headers=merged_headers,
            method=normalized_method,
        )

        try:
            with urllib.request.urlopen(request, timeout=max(1.0, timeout_seconds)) as response:
                return response.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {error.code}: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Network error: {error.reason}") from error

    def _integration_http_form_post(
        self,
        url: str,
        form_values: Dict[str, str],
        basic_auth_username: str = "",
        basic_auth_password: str = "",
        timeout_seconds: float = 30.0,
    ) -> str:
        data = urllib.parse.urlencode(form_values).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if basic_auth_username or basic_auth_password:
            token = f"{basic_auth_username}:{basic_auth_password}".encode("utf-8")
            encoded = base64.b64encode(token).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=max(1.0, timeout_seconds)) as response:
                return response.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {error.code}: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Network error: {error.reason}") from error

    def _integration_sqlite_query(self, path_value: str, sql: str) -> str:
        database_path = Path(path_value).expanduser()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        try:
            cursor = connection.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            connection.commit()
            if not rows:
                return "SQL executed successfully."
            preview_lines: List[str] = []
            for row in rows[:25]:
                preview_lines.append(" | ".join(str(item) for item in row))
            return "\n".join(preview_lines)
        finally:
            connection.close()

    def _build_simple_email(
        self,
        from_address: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        lines = [
            f"From: {from_address}",
            f"To: {to_address}",
            f"Subject: {subject}",
            "Content-Type: text/plain; charset=utf-8",
            "",
            body,
        ]
        return "\r\n".join(lines)

    def _integration_http_post(
        self,
        url: str,
        payload_text: str,
        timeout_seconds: float = 45.0,
    ) -> str:
        return self._integration_http_request(
            method="POST",
            url=url,
            payload_text=payload_text,
            headers={"Content-Type": "application/json"},
            timeout_seconds=timeout_seconds,
        )

    def _integration_http_get(
        self,
        url: str,
        timeout_seconds: float = 30.0,
    ) -> str:
        return self._integration_http_request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            timeout_seconds=timeout_seconds,
        )

    def _integration_file_append(self, path_value: str, content: str) -> str:
        path = Path(path_value).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a", encoding="utf-8") as file:
            file.write(content)
            file.write("\n")

        return str(path)

    def _integration_shell_command(
        self,
        command: str,
        input_payload: str,
        cancel_check: Optional[Callable[[], bool]] = None,
        timeout_seconds: float = 60.0,
    ) -> str:
        process = subprocess.Popen(
            command,
            shell=True,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout = ""
        stderr = ""
        communicate_input: Optional[str] = input_payload
        deadline = time.time() + max(1.0, timeout_seconds)
        while True:
            try:
                out, err = process.communicate(input=communicate_input, timeout=0.2)
                stdout = out or ""
                stderr = err or ""
                break
            except subprocess.TimeoutExpired:
                communicate_input = None
                if cancel_check and cancel_check():
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RuntimeError("Command cancelled by user.")
                if time.time() > deadline:
                    process.terminate()
                    try:
                        process.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RuntimeError(
                        f"Command timed out after {int(timeout_seconds)} second(s)."
                    )

        stdout = stdout.strip()
        stderr = stderr.strip()

        if process.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {process.returncode}): {stderr or stdout or 'No output'}"
            )

        return stdout or stderr or "Command completed with no output."

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
