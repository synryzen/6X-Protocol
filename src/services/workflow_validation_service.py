import json
from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional

from src.models.canvas_edge import CanvasEdge
from src.models.canvas_node import CanvasNode
from src.models.workflow import Workflow
from src.services.integration_registry_service import IntegrationRegistryService
from src.services.settings_store import SettingsStore


@dataclass
class ValidationIssue:
    severity: str
    message: str
    node_id: str = ""
    edge_id: str = ""
    source_node_id: str = ""
    target_node_id: str = ""


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_error(
        self,
        message: str,
        *,
        node_id: str = "",
        edge_id: str = "",
        source_node_id: str = "",
        target_node_id: str = "",
    ):
        self.errors.append(message)
        self.issues.append(
            ValidationIssue(
                severity="error",
                message=message,
                node_id=node_id,
                edge_id=edge_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
            )
        )

    def add_warning(
        self,
        message: str,
        *,
        node_id: str = "",
        edge_id: str = "",
        source_node_id: str = "",
        target_node_id: str = "",
    ):
        self.warnings.append(message)
        self.issues.append(
            ValidationIssue(
                severity="warning",
                message=message,
                node_id=node_id,
                edge_id=edge_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
            )
        )


class WorkflowValidationService:
    VALID_EDGE_CONDITIONS = {"", "next", "true", "false"}
    REQUIRED_FIELD_ALIASES = {
        "url": ["webhook_url", "script_url", "connection_url"],
        "webhook_url": ["url"],
        "script_url": ["url"],
        "connection_url": ["url"],
        "sql": ["payload", "query", "command"],
        "query": ["sql", "payload"],
        "command": ["payload", "query"],
        "api_key": ["auth_token"],
        "auth_token": ["api_key"],
        "payload": ["message", "text", "content", "approval_message"],
        "message": ["payload", "text", "content", "approval_message"],
        "text": ["message", "payload", "content"],
        "content": ["message", "payload", "text"],
    }
    VALID_TRIGGER_MODES = {"manual", "schedule_interval", "webhook", "file_watch", "cron"}
    VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    URL_REQUIRED_INTEGRATIONS = {
        "http_post",
        "http_request",
        "slack_webhook",
        "discord_webhook",
        "teams_webhook",
        "google_apps_script",
        "google_calendar_api",
        "outlook_graph",
        "notion_api",
        "airtable_api",
        "hubspot_api",
        "stripe_api",
        "github_rest",
        "gitlab_api",
        "jira_api",
        "asana_api",
        "clickup_api",
        "trello_api",
        "monday_api",
        "zendesk_api",
        "pipedrive_api",
        "salesforce_api",
        "resend_email",
        "mailgun_email",
    }
    HEADERS_JSON_INTEGRATIONS = {
        "http_request",
        "notion_api",
        "airtable_api",
        "hubspot_api",
        "stripe_api",
        "github_rest",
        "gitlab_api",
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
    }
    JSON_PAYLOAD_INTEGRATIONS = {
        "http_request",
        "http_post",
        "google_apps_script",
        "google_sheets",
        "google_calendar_api",
        "notion_api",
        "airtable_api",
        "hubspot_api",
        "stripe_api",
        "github_rest",
        "gitlab_api",
        "linear_api",
        "outlook_graph",
        "jira_api",
        "asana_api",
        "clickup_api",
        "trello_api",
        "monday_api",
        "zendesk_api",
        "pipedrive_api",
        "salesforce_api",
        "telegram_bot",
        "twilio_sms",
        "resend_email",
        "mailgun_email",
    }

    def __init__(
        self,
        integration_registry: Optional[IntegrationRegistryService] = None,
        settings_store: Optional[SettingsStore] = None,
    ):
        self.integration_registry = integration_registry or IntegrationRegistryService()
        self.settings_store = settings_store or SettingsStore()

    def validate_workflow(self, workflow: Workflow) -> ValidationResult:
        graph = workflow.normalized_graph()
        nodes = self._parse_nodes(graph)
        edges = self._parse_edges(graph)
        return self.validate_graph(nodes, edges, workflow.name)

    def validate_graph(
        self,
        nodes: List[CanvasNode],
        edges: List[CanvasEdge],
        workflow_name: str = "",
    ) -> ValidationResult:
        app_settings = self.settings_store.load_settings()
        result = ValidationResult()
        label = workflow_name.strip() or "Workflow"

        if not nodes:
            result.add_warning(
                f"{label} has no graph nodes. Execution will use fallback trigger/action flow."
            )
            return result

        node_map: Dict[str, CanvasNode] = {}
        for node in nodes:
            if not node.id:
                result.add_error("A graph node is missing an ID.")
                continue
            if node.id in node_map:
                result.add_error(
                    f"Duplicate node ID '{node.id}' detected ({node.name or 'Unnamed'})."
                )
                continue
            node_map[node.id] = node

            node_name = node.name.strip() or "Unnamed"
            node_kind = self._node_type_key(node.node_type)
            if not node.name.strip():
                result.add_warning(f"Node '{node.id}' has no name.", node_id=node.id)
            if node_kind == "unknown":
                result.add_error(
                    f"Node '{node_name}' has unsupported type '{node.node_type}'.",
                    node_id=node.id,
                )

            self._validate_node_contract(node, node_kind, result, app_settings)

        incoming_count = {node_id: 0 for node_id in node_map}
        outgoing_count = {node_id: 0 for node_id in node_map}
        for edge in edges:
            source = edge.source_node_id.strip()
            target = edge.target_node_id.strip()
            if not source or not target:
                result.add_error(
                    "A graph edge is missing source or target node ID.",
                    edge_id=edge.id,
                    source_node_id=source,
                    target_node_id=target,
                )
                continue
            if source not in node_map:
                result.add_error(
                    f"Edge source '{source}' does not exist.",
                    edge_id=edge.id,
                    source_node_id=source,
                    target_node_id=target,
                )
                continue
            if target not in node_map:
                result.add_error(
                    f"Edge target '{target}' does not exist.",
                    edge_id=edge.id,
                    source_node_id=source,
                    target_node_id=target,
                )
                continue
            if edge.condition not in self.VALID_EDGE_CONDITIONS:
                result.add_error(
                    f"Edge '{source} -> {target}' has unsupported condition '{edge.condition}'.",
                    edge_id=edge.id,
                    source_node_id=source,
                    target_node_id=target,
                )
            incoming_count[target] += 1
            outgoing_count[source] += 1

        start_nodes = [node_id for node_id, count in incoming_count.items() if count == 0]
        if not start_nodes:
            result.add_error("Graph has no start node (all nodes have incoming edges).")

        for node_id, node in node_map.items():
            node_kind = self._node_type_key(node.node_type)
            if node_kind == "condition" and outgoing_count.get(node_id, 0) == 0:
                result.add_error(
                    f"Condition node '{node.name or node_id}' has no outgoing branches.",
                    node_id=node_id,
                )
            if node_kind in {"trigger", "action", "ai"} and outgoing_count.get(node_id, 0) == 0:
                result.add_warning(
                    f"Node '{node.name or node_id}' is terminal (no outgoing edge).",
                    node_id=node_id,
                )

        return result

    def _validate_node_contract(
        self,
        node: CanvasNode,
        node_kind: str,
        result: ValidationResult,
        app_settings: Dict[str, str],
    ):
        config = dict(node.config)
        directives = self._parse_directives(node.detail)
        config.update(directives)
        node_name = node.name.strip() or node.id or "Unnamed"

        if node_kind in {"action", "template"}:
            integration_key = str(config.get("integration", "standard")).strip().lower() or "standard"
            integration = self.integration_registry.get_integration(integration_key)
            if not integration:
                result.add_error(
                    f"Action node '{node_name}' references missing integration '{integration_key}'.",
                    node_id=node.id,
                )
                return

            required_fields = integration.get("required_fields", [])
            if isinstance(required_fields, list):
                for field in required_fields:
                    key = str(field).strip()
                    if not key:
                        continue
                    if not self._required_field_value(
                        config,
                        key,
                        integration_key=integration_key,
                        app_settings=app_settings,
                    ):
                        result.add_error(
                            f"Action node '{node_name}' is missing required field '{key}'.",
                            node_id=node.id,
                        )
            self._validate_action_contract_fields(
                node=node,
                node_name=node_name,
                integration_key=integration_key,
                config=config,
                app_settings=app_settings,
                result=result,
            )

        if node_kind == "ai":
            prompt = str(config.get("prompt", "")).strip() or node.summary.strip()
            if not prompt:
                result.add_warning(
                    f"AI node '{node_name}' has no prompt/summary and will use default prompt.",
                    node_id=node.id,
                )

            temperature = str(config.get("temperature", "")).strip()
            if temperature:
                try:
                    value = float(temperature)
                    if value < 0.0 or value > 2.0:
                        result.add_error(
                            f"AI node '{node_name}' temperature must be between 0.0 and 2.0.",
                            node_id=node.id,
                        )
                except ValueError:
                    result.add_error(
                        f"AI node '{node_name}' temperature is not a number.",
                        node_id=node.id,
                    )

            max_tokens = str(config.get("max_tokens", "")).strip()
            if max_tokens:
                try:
                    value = int(max_tokens)
                    if value < 64 or value > 64000:
                        result.add_error(
                            f"AI node '{node_name}' max tokens must be between 64 and 64000.",
                            node_id=node.id,
                        )
                except ValueError:
                    result.add_error(
                        f"AI node '{node_name}' max tokens is not a whole number.",
                        node_id=node.id,
                    )

        if node_kind == "condition":
            expression = str(config.get("expression", "")).strip() or node.detail.strip()
            if not expression:
                result.add_warning(
                    f"Condition node '{node_name}' has no expression. It will use default truthy behavior.",
                    node_id=node.id,
                )

        if node_kind == "trigger":
            self._validate_trigger_contract_fields(
                node=node,
                node_name=node_name,
                config=config,
                result=result,
            )

    def _validate_action_contract_fields(
        self,
        *,
        node: CanvasNode,
        node_name: str,
        integration_key: str,
        config: Dict[str, str],
        app_settings: Dict[str, str],
        result: ValidationResult,
    ):
        timeout_raw = str(config.get("timeout_sec", "")).strip()
        if timeout_raw:
            try:
                timeout_value = float(timeout_raw)
                if timeout_value < 0.0:
                    result.add_error(
                        f"Action node '{node_name}' timeout_sec must be >= 0.",
                        node_id=node.id,
                    )
                elif timeout_value > 600.0:
                    result.add_warning(
                        f"Action node '{node_name}' timeout_sec is very high ({timeout_value}).",
                        node_id=node.id,
                    )
            except ValueError:
                result.add_error(
                    f"Action node '{node_name}' timeout_sec is not a number.",
                    node_id=node.id,
                )

        retry_raw = str(config.get("retry_max", "")).strip()
        if retry_raw:
            try:
                retry_value = int(retry_raw)
                if retry_value < 0:
                    result.add_error(
                        f"Action node '{node_name}' retry_max must be >= 0.",
                        node_id=node.id,
                    )
                elif retry_value > 8:
                    result.add_warning(
                        f"Action node '{node_name}' retry_max is very high ({retry_value}).",
                        node_id=node.id,
                    )
            except ValueError:
                result.add_error(
                    f"Action node '{node_name}' retry_max must be a whole number.",
                    node_id=node.id,
                )

        backoff_raw = str(config.get("retry_backoff_ms", "")).strip()
        if backoff_raw:
            try:
                backoff_value = int(backoff_raw)
                if backoff_value < 0:
                    result.add_error(
                        f"Action node '{node_name}' retry_backoff_ms must be >= 0.",
                        node_id=node.id,
                    )
            except ValueError:
                result.add_error(
                    f"Action node '{node_name}' retry_backoff_ms must be a whole number.",
                    node_id=node.id,
                )

        if integration_key in self.URL_REQUIRED_INTEGRATIONS:
            url_value = self._required_field_value(
                config,
                "url",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if url_value and not self._looks_like_url(url_value):
                result.add_error(
                    f"Action node '{node_name}' has invalid URL '{url_value}'.",
                    node_id=node.id,
                )

        if integration_key in {"http_request", "http_post"}:
            method_value = str(config.get("method", "POST")).strip().upper()
            if method_value and method_value not in self.VALID_HTTP_METHODS:
                result.add_error(
                    f"Action node '{node_name}' has invalid HTTP method '{method_value}'.",
                    node_id=node.id,
                )

        headers_raw = str(config.get("headers", "")).strip()
        if headers_raw and integration_key in self.HEADERS_JSON_INTEGRATIONS:
            try:
                parsed_headers = json.loads(headers_raw)
                if not isinstance(parsed_headers, dict):
                    result.add_error(
                        f"Action node '{node_name}' headers must be a JSON object.",
                        node_id=node.id,
                    )
            except Exception:
                result.add_error(
                    f"Action node '{node_name}' headers must be valid JSON.",
                    node_id=node.id,
                )

        payload_raw = str(config.get("payload", "")).strip()
        if payload_raw and integration_key in self.JSON_PAYLOAD_INTEGRATIONS:
            try:
                json.loads(payload_raw)
            except Exception:
                result.add_error(
                    f"Action node '{node_name}' payload must be valid JSON for integration '{integration_key}'.",
                    node_id=node.id,
                )

        if integration_key in {"postgres_sql", "mysql_sql"}:
            connection_url = self._required_field_value(
                config,
                "connection_url",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if connection_url:
                lowered = connection_url.lower()
                if integration_key == "postgres_sql" and not lowered.startswith(
                    ("postgres://", "postgresql://")
                ):
                    result.add_error(
                        f"Action node '{node_name}' connection_url must start with postgres:// or postgresql://.",
                        node_id=node.id,
                    )
                if integration_key == "mysql_sql" and not lowered.startswith(("mysql://", "mysql2://")):
                    result.add_error(
                        f"Action node '{node_name}' connection_url must start with mysql:// or mysql2://.",
                        node_id=node.id,
                    )

        if integration_key == "redis_command":
            connection_url = self._required_field_value(
                config,
                "connection_url",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if connection_url and not connection_url.lower().startswith(("redis://", "rediss://")):
                result.add_error(
                    f"Action node '{node_name}' redis connection_url must start with redis:// or rediss://.",
                    node_id=node.id,
                )
            command_value = self._required_field_value(
                config,
                "command",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if command_value.lower().startswith("redis-cli"):
                result.add_warning(
                    f"Action node '{node_name}' command should omit 'redis-cli' prefix.",
                    node_id=node.id,
                )

        if integration_key == "s3_cli":
            command_value = self._required_field_value(
                config,
                "command",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            lowered = command_value.lower()
            if lowered and not (lowered.startswith("aws ") or lowered.startswith("s3 ")):
                result.add_warning(
                    f"Action node '{node_name}' command should start with 's3' or 'aws s3'.",
                    node_id=node.id,
                )

        if integration_key in {"postgres_sql", "mysql_sql", "sqlite_sql"}:
            sql_value = self._required_field_value(
                config,
                "sql",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if sql_value and len(sql_value.strip()) < 6:
                result.add_warning(
                    f"Action node '{node_name}' SQL query appears very short.",
                    node_id=node.id,
                )
        if integration_key == "sqlite_sql":
            path_value = self._required_field_value(
                config,
                "path",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if path_value and not path_value.lower().endswith((".db", ".sqlite", ".sqlite3")):
                result.add_warning(
                    f"Action node '{node_name}' SQLite path should usually end with .db/.sqlite.",
                    node_id=node.id,
                )

        if integration_key in {"gmail_send", "resend_email", "mailgun_email"}:
            to_value = self._required_field_value(
                config,
                "to",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if to_value and not self._looks_like_email(to_value):
                result.add_error(
                    f"Action node '{node_name}' has invalid recipient email '{to_value}'.",
                    node_id=node.id,
                )
            from_value = self._required_field_value(
                config,
                "from",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if from_value and from_value != "me" and not self._looks_like_email(from_value):
                result.add_error(
                    f"Action node '{node_name}' has invalid sender email '{from_value}'.",
                    node_id=node.id,
                )

        if integration_key == "twilio_sms":
            from_value = self._required_field_value(
                config,
                "from",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            to_value = self._required_field_value(
                config,
                "to",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if from_value and not self._looks_like_phone(from_value):
                result.add_error(
                    f"Action node '{node_name}' has invalid Twilio from number '{from_value}'.",
                    node_id=node.id,
                )
            if to_value and not self._looks_like_phone(to_value):
                result.add_error(
                    f"Action node '{node_name}' has invalid Twilio to number '{to_value}'.",
                    node_id=node.id,
                )

    def _validate_trigger_contract_fields(
        self,
        *,
        node: CanvasNode,
        node_name: str,
        config: Dict[str, str],
        result: ValidationResult,
    ):
        trigger_mode = str(config.get("trigger_mode", "")).strip().lower() or "manual"
        trigger_value = str(config.get("trigger_value", "")).strip()

        if trigger_mode not in self.VALID_TRIGGER_MODES:
            result.add_error(
                f"Trigger node '{node_name}' has unsupported trigger mode '{trigger_mode}'.",
                node_id=node.id,
            )
            return

        if trigger_mode == "schedule_interval":
            if not trigger_value:
                result.add_error(
                    f"Trigger node '{node_name}' requires trigger_value seconds for schedule_interval.",
                    node_id=node.id,
                )
            else:
                try:
                    interval_value = float(trigger_value)
                    if interval_value <= 0:
                        result.add_error(
                            f"Trigger node '{node_name}' interval must be > 0 seconds.",
                            node_id=node.id,
                        )
                except ValueError:
                    result.add_error(
                        f"Trigger node '{node_name}' interval '{trigger_value}' is not numeric.",
                        node_id=node.id,
                    )

        if trigger_mode == "cron":
            if not trigger_value:
                result.add_error(
                    f"Trigger node '{node_name}' requires trigger_value cron expression.",
                    node_id=node.id,
                )
            elif not self._looks_like_cron(trigger_value):
                result.add_error(
                    f"Trigger node '{node_name}' has invalid cron expression '{trigger_value}'.",
                    node_id=node.id,
                )

        if trigger_mode in {"webhook", "file_watch"} and not trigger_value:
            result.add_warning(
                f"Trigger node '{node_name}' has no trigger_value for mode '{trigger_mode}'. Default will be used.",
                node_id=node.id,
            )

    def _node_type_key(self, node_type: str) -> str:
        normalized = str(node_type).strip().lower()
        if normalized.startswith("trigger"):
            return "trigger"
        if normalized.startswith("action"):
            return "action"
        if "condition" in normalized:
            return "condition"
        if normalized.startswith("ai"):
            return "ai"
        if "template" in normalized:
            return "template"
        return "unknown"

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
        seen: set[tuple[str, str, str]] = set()
        raw_edges = graph.get("edges", [])
        if not isinstance(raw_edges, list):
            raw_edges = []
        legacy_links = graph.get("links", [])
        if isinstance(legacy_links, list):
            raw_edges = [*raw_edges, *legacy_links]

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
            condition_raw = str(
                item.get("condition")
                or item.get("link_type")
                or item.get("type")
                or ""
            ).strip().lower()
            condition = condition_raw if condition_raw in {"next", "true", "false"} else ""
            signature = (source, target, condition)
            if signature in seen:
                continue
            seen.add(signature)
            parsed_edges.append(
                CanvasEdge(
                    id=str(item.get("id", "")).strip(),
                    source_node_id=source,
                    target_node_id=target,
                    condition=condition,
                )
            )
        return parsed_edges

    def _parse_directives(self, text: str) -> Dict[str, str]:
        directives: Dict[str, str] = {}
        for line in str(text).splitlines():
            raw = line.strip()
            if not raw or ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            directives[key.strip().lower()] = value.strip()
        return directives

    def _required_field_value(
        self,
        config: Dict[str, str],
        field_name: str,
        *,
        integration_key: str = "",
        app_settings: Optional[Dict[str, str]] = None,
    ) -> str:
        key = str(field_name).strip().lower()
        candidates = [key, *self.REQUIRED_FIELD_ALIASES.get(key, [])]
        for candidate in candidates:
            value = str(config.get(candidate, "")).strip()
            if value:
                return value
        settings = app_settings if isinstance(app_settings, dict) else {}
        if settings and integration_key:
            for setting_key in self._setting_keys_for_required_field(
                integration_key,
                key,
            ):
                value = str(settings.get(setting_key, "")).strip()
                if value:
                    return value
        return ""

    def _setting_keys_for_required_field(self, integration_key: str, field_name: str) -> List[str]:
        key = str(integration_key).strip().lower()
        field = str(field_name).strip().lower()
        mapping: Dict[str, Dict[str, List[str]]] = {
            "slack_webhook": {"webhook_url": ["slack_webhook_url"], "url": ["slack_webhook_url"]},
            "discord_webhook": {
                "webhook_url": ["discord_webhook_url"],
                "url": ["discord_webhook_url"],
            },
            "teams_webhook": {"webhook_url": ["teams_webhook_url"], "url": ["teams_webhook_url"]},
            "telegram_bot": {
                "api_key": ["telegram_bot_token"],
                "chat_id": ["telegram_default_chat_id"],
            },
            "openweather_current": {
                "api_key": ["openweather_api_key"],
                "location": ["openweather_default_location"],
            },
            "google_apps_script": {"script_url": ["google_apps_script_url"], "url": ["google_apps_script_url"]},
            "google_sheets": {
                "api_key": ["google_sheets_api_key"],
                "spreadsheet_id": ["google_sheets_spreadsheet_id"],
                "range": ["google_sheets_range"],
            },
            "google_calendar_api": {
                "api_key": ["google_calendar_api_key"],
                "url": ["google_calendar_api_url"],
            },
            "outlook_graph": {
                "api_key": ["outlook_api_key"],
                "url": ["outlook_api_url"],
            },
            "gmail_send": {"api_key": ["gmail_api_key"], "from": ["gmail_from_address"]},
            "notion_api": {"api_key": ["notion_api_key"], "url": ["notion_api_url"]},
            "airtable_api": {"api_key": ["airtable_api_key"], "url": ["airtable_api_url"]},
            "hubspot_api": {"api_key": ["hubspot_api_key"], "url": ["hubspot_api_url"]},
            "stripe_api": {"api_key": ["stripe_api_key"], "url": ["stripe_api_url"]},
            "github_rest": {"api_key": ["github_api_key"], "url": ["github_api_url"]},
            "jira_api": {"api_key": ["jira_api_key"], "url": ["jira_api_url"]},
            "asana_api": {"api_key": ["asana_api_key"], "url": ["asana_api_url"]},
            "clickup_api": {"api_key": ["clickup_api_key"], "url": ["clickup_api_url"]},
            "trello_api": {"api_key": ["trello_api_key"], "url": ["trello_api_url"]},
            "monday_api": {"api_key": ["monday_api_key"], "url": ["monday_api_url"]},
            "zendesk_api": {"api_key": ["zendesk_api_key"], "url": ["zendesk_api_url"]},
            "pipedrive_api": {"api_key": ["pipedrive_api_key"], "url": ["pipedrive_api_url"]},
            "salesforce_api": {"api_key": ["salesforce_api_key"], "url": ["salesforce_api_url"]},
            "gitlab_api": {"api_key": ["gitlab_api_key"], "url": ["gitlab_api_url"]},
            "twilio_sms": {
                "account_sid": ["twilio_account_sid"],
                "auth_token": ["twilio_auth_token"],
                "from": ["twilio_from_number"],
            },
            "resend_email": {"api_key": ["resend_api_key"], "from": ["resend_from_address"]},
            "mailgun_email": {
                "api_key": ["mailgun_api_key"],
                "domain": ["mailgun_domain"],
                "from": ["mailgun_from_address"],
            },
            "postgres_sql": {"connection_url": ["postgres_connection_url"]},
            "mysql_sql": {"connection_url": ["mysql_connection_url"]},
            "redis_command": {"connection_url": ["redis_connection_url"]},
        }
        integration_mapping = mapping.get(key, {})
        if field in integration_mapping:
            return integration_mapping[field]
        if field == "url":
            return integration_mapping.get("webhook_url", []) + integration_mapping.get("script_url", [])
        return []

    def _looks_like_url(self, value: str) -> bool:
        text = str(value).strip()
        if not text:
            return False
        return text.startswith("http://") or text.startswith("https://")

    def _looks_like_email(self, value: str) -> bool:
        text = str(value).strip()
        if not text:
            return False
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text))

    def _looks_like_phone(self, value: str) -> bool:
        text = str(value).strip()
        if not text:
            return False
        return bool(re.match(r"^\+?[0-9][0-9\-\s]{6,}$", text))

    def _looks_like_cron(self, value: str) -> bool:
        text = str(value).strip()
        if not text:
            return False
        tokens = [item for item in text.split(" ") if item.strip()]
        return len(tokens) in {5, 6}
