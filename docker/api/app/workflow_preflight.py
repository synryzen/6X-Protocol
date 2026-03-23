from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_NODE_TYPES = {"trigger", "action", "ai", "condition", "template"}
VALID_EDGE_CONDITIONS = {"", "next", "true", "false"}
VALID_TRIGGER_MODES = {"manual", "schedule_interval", "cron", "webhook", "file_watch"}
REQUIRED_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "url": ("webhook_url", "script_url", "connection_url"),
    "webhook_url": ("url",),
    "script_url": ("url",),
    "connection_url": ("url",),
    "api_key": ("auth_token",),
    "auth_token": ("api_key",),
    "message": ("payload", "text", "content"),
    "payload": ("message", "text", "content"),
    "text": ("message", "payload", "content"),
    "content": ("message", "payload", "text"),
}


@dataclass
class PreflightIssue:
    severity: str
    message: str
    node_id: str = ""
    edge_id: str = ""
    source_node_id: str = ""
    target_node_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "node_id": self.node_id,
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
        }


def _node_type_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"ai node", "ai_node", "ainode"}:
        return "ai"
    if raw in VALID_NODE_TYPES:
        return raw
    return "unknown"


def _read_graph_nodes(graph: Any) -> list[dict[str, Any]]:
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [item for item in nodes if isinstance(item, dict)]


def _read_graph_edges(graph: Any) -> list[dict[str, Any]]:
    if not isinstance(graph, dict):
        return []
    edges = graph.get("edges")
    if not isinstance(edges, list):
        return []
    return [item for item in edges if isinstance(item, dict)]


def _node_config(node: dict[str, Any]) -> dict[str, Any]:
    config = node.get("config")
    metadata = node.get("metadata")
    merged: dict[str, Any] = {}
    if isinstance(metadata, dict):
        merged.update(metadata)
    if isinstance(config, dict):
        merged.update(config)
    return merged


def _edge_source(edge: dict[str, Any]) -> str:
    for key in ("source_node_id", "source", "from"):
        value = str(edge.get(key, "")).strip()
        if value:
            return value
    return ""


def _edge_target(edge: dict[str, Any]) -> str:
    for key in ("target_node_id", "target", "to"):
        value = str(edge.get(key, "")).strip()
        if value:
            return value
    return ""


def _edge_condition(edge: dict[str, Any]) -> str:
    condition = str(edge.get("condition", "")).strip().lower()
    if condition:
        return condition
    edge_type = str(edge.get("type", "")).strip().lower()
    if edge_type in VALID_EDGE_CONDITIONS:
        return edge_type
    return "next" if edge_type else ""


def _required_fields_by_integration(
    integration_catalog: list[dict[str, Any]] | None,
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in integration_catalog or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip().lower()
        if not key:
            continue
        fields = item.get("required_fields")
        if not isinstance(fields, list):
            mapping[key] = []
            continue
        mapping[key] = [str(field).strip().lower() for field in fields if str(field).strip()]
    return mapping


def _has_field_value(config: dict[str, Any], field: str) -> bool:
    primary = str(config.get(field, "")).strip()
    if primary:
        return True
    for alias in REQUIRED_FIELD_ALIASES.get(field, ()):
        alias_value = str(config.get(alias, "")).strip()
        if alias_value:
            return True
    return False


def preflight_graph(
    graph: dict[str, Any] | None,
    *,
    workflow_name: str = "",
    integration_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    issues: list[PreflightIssue] = []
    errors: list[str] = []
    warnings: list[str] = []

    def add_error(
        message: str,
        *,
        node_id: str = "",
        edge_id: str = "",
        source_node_id: str = "",
        target_node_id: str = "",
    ) -> None:
        errors.append(message)
        issues.append(
            PreflightIssue(
                severity="error",
                message=message,
                node_id=node_id,
                edge_id=edge_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
            )
        )

    def add_warning(
        message: str,
        *,
        node_id: str = "",
        edge_id: str = "",
        source_node_id: str = "",
        target_node_id: str = "",
    ) -> None:
        warnings.append(message)
        issues.append(
            PreflightIssue(
                severity="warning",
                message=message,
                node_id=node_id,
                edge_id=edge_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
            )
        )

    label = str(workflow_name).strip() or "Workflow"
    nodes = _read_graph_nodes(graph or {})
    edges = _read_graph_edges(graph or {})
    required_by_integration = _required_fields_by_integration(integration_catalog)

    if not nodes:
        add_warning(f"{label} has no graph nodes.")
        return {
            "ok": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "issues": [issue.as_dict() for issue in issues],
        }

    node_map: dict[str, dict[str, Any]] = {}
    incoming_count: dict[str, int] = {}
    outgoing_count: dict[str, int] = {}

    for node in nodes:
        node_id = str(node.get("id", "")).strip()
        node_name = str(node.get("name", "")).strip() or "Unnamed"
        node_kind = _node_type_key(node.get("type", ""))
        if not node_id:
            add_error(f"Node '{node_name}' is missing an id.")
            continue
        if node_id in node_map:
            add_error(f"Duplicate node id '{node_id}' detected.", node_id=node_id)
            continue
        node_map[node_id] = node
        incoming_count[node_id] = 0
        outgoing_count[node_id] = 0

        if node_kind == "unknown":
            add_error(
                f"Node '{node_name}' has unsupported type '{node.get('type', '')}'.",
                node_id=node_id,
            )
            continue

        config = _node_config(node)
        if node_kind == "trigger":
            trigger_mode = str(config.get("trigger_mode", "")).strip().lower()
            if not trigger_mode:
                detail = str(node.get("detail", "")).strip().lower()
                if detail.startswith("trigger:"):
                    trigger_mode = detail.split(":", 1)[1].strip().split(":", 1)[0].strip()
            if trigger_mode and trigger_mode not in VALID_TRIGGER_MODES:
                add_error(
                    f"Trigger node '{node_name}' has unsupported mode '{trigger_mode}'.",
                    node_id=node_id,
                )

        if node_kind in {"action", "template"}:
            integration_key = str(config.get("integration", "standard")).strip().lower() or "standard"
            required_fields = required_by_integration.get(integration_key, [])
            for field in required_fields:
                if not _has_field_value(config, field):
                    add_error(
                        (
                            f"Action node '{node_name}' is missing required integration field "
                            f"'{field}' for '{integration_key}'."
                        ),
                        node_id=node_id,
                    )

    for index, edge in enumerate(edges):
        edge_id = str(edge.get("id", "")).strip() or f"edge-{index + 1}"
        source = _edge_source(edge)
        target = _edge_target(edge)
        condition = _edge_condition(edge)
        if not source or not target:
            add_error(
                "A graph edge is missing source or target node id.",
                edge_id=edge_id,
                source_node_id=source,
                target_node_id=target,
            )
            continue
        if source not in node_map:
            add_error(
                f"Edge source '{source}' does not exist.",
                edge_id=edge_id,
                source_node_id=source,
                target_node_id=target,
            )
            continue
        if target not in node_map:
            add_error(
                f"Edge target '{target}' does not exist.",
                edge_id=edge_id,
                source_node_id=source,
                target_node_id=target,
            )
            continue
        if source == target:
            add_warning(
                f"Edge '{source} -> {target}' is a self-loop.",
                edge_id=edge_id,
                source_node_id=source,
                target_node_id=target,
            )
        if condition not in VALID_EDGE_CONDITIONS:
            add_error(
                f"Edge '{source} -> {target}' has unsupported condition '{condition}'.",
                edge_id=edge_id,
                source_node_id=source,
                target_node_id=target,
            )
        incoming_count[target] = incoming_count.get(target, 0) + 1
        outgoing_count[source] = outgoing_count.get(source, 0) + 1

    start_nodes = [node_id for node_id, count in incoming_count.items() if count == 0]
    if not start_nodes:
        add_error("Graph has no start node (all nodes have incoming edges).")

    for node_id, node in node_map.items():
        node_kind = _node_type_key(node.get("type", ""))
        node_name = str(node.get("name", "")).strip() or node_id
        outgoing = outgoing_count.get(node_id, 0)
        if node_kind == "condition":
            if outgoing == 0:
                add_error(
                    f"Condition node '{node_name}' has no outgoing branches.",
                    node_id=node_id,
                )
            true_branch = any(
                _edge_source(edge) == node_id and _edge_condition(edge) == "true" for edge in edges
            )
            false_branch = any(
                _edge_source(edge) == node_id and _edge_condition(edge) == "false" for edge in edges
            )
            if true_branch and not false_branch:
                add_warning(
                    f"Condition node '{node_name}' is missing a false branch.",
                    node_id=node_id,
                )
            if false_branch and not true_branch:
                add_warning(
                    f"Condition node '{node_name}' is missing a true branch.",
                    node_id=node_id,
                )
        elif node_kind in {"trigger", "action", "ai", "template"} and outgoing == 0:
            add_warning(
                f"Node '{node_name}' is terminal (no outgoing edge).",
                node_id=node_id,
            )

    return {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "issues": [issue.as_dict() for issue in issues],
    }

