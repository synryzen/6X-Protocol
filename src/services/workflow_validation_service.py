from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.models.canvas_edge import CanvasEdge
from src.models.canvas_node import CanvasNode
from src.models.workflow import Workflow
from src.services.integration_registry_service import IntegrationRegistryService


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

    def __init__(
        self,
        integration_registry: Optional[IntegrationRegistryService] = None,
    ):
        self.integration_registry = integration_registry or IntegrationRegistryService()

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

            self._validate_node_contract(node, node_kind, result)

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
    ):
        config = dict(node.config)
        directives = self._parse_directives(node.detail)
        config.update(directives)
        node_name = node.name.strip() or node.id or "Unnamed"

        if node_kind == "action":
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
                    if not self._required_field_value(config, key):
                        result.add_error(
                            f"Action node '{node_name}' is missing required field '{key}'.",
                            node_id=node.id,
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

    def _required_field_value(self, config: Dict[str, str], field_name: str) -> str:
        key = str(field_name).strip().lower()
        candidates = [key, *self.REQUIRED_FIELD_ALIASES.get(key, [])]
        for candidate in candidates:
            value = str(config.get(candidate, "")).strip()
            if value:
                return value
        return ""
