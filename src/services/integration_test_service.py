from typing import Dict, Optional

from src.models.canvas_node import CanvasNode
from src.services.execution_engine import ExecutionEngine
from src.services.integration_registry_service import IntegrationRegistryService


class IntegrationTestService:
    def __init__(
        self,
        execution_engine: Optional[ExecutionEngine] = None,
        integration_registry: Optional[IntegrationRegistryService] = None,
    ):
        self.execution_engine = execution_engine or ExecutionEngine()
        self.integration_registry = integration_registry or IntegrationRegistryService()

    def run_test(
        self,
        integration_key: str,
        directives_text: str = "",
        input_context: str = "",
    ) -> Dict[str, str]:
        key = integration_key.strip().lower()
        if not key:
            raise ValueError("Choose an integration to test.")

        integration = self.integration_registry.get_integration(key)
        if not integration:
            raise ValueError(f"Integration '{key}' is not installed.")

        config = self._parse_directives(directives_text)
        config["integration"] = key
        node = CanvasNode(
            id="integration-test-node",
            name=f"Test {integration.get('name', key)}",
            node_type="Action",
            detail=f"integration:{key}",
            summary="Integration test mode",
            x=0,
            y=0,
            config=config,
        )

        logs, output = self.execution_engine.execute_action_node_for_test(
            node,
            input_context=input_context,
        )

        return {
            "status": "success",
            "integration": key,
            "summary": logs[-1] if logs else "Integration test completed.",
            "output": output,
            "logs": "\n".join(logs),
        }

    def _parse_directives(self, directives_text: str) -> Dict[str, str]:
        config: Dict[str, str] = {}
        for line in directives_text.splitlines():
            raw = line.strip()
            if not raw or ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            normalized = key.strip().lower()
            if not normalized:
                continue
            config[normalized] = value.strip()
        return config
