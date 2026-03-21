import unittest

from src.models.workflow import Workflow
from src.services.execution_engine import ExecutionEngine


class _InMemorySettingsStore:
    def __init__(self, values=None):
        self._values = values or {}

    def load_settings(self):
        return dict(self._values)


class ExecutionEngineErrorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = ExecutionEngine(settings_store=_InMemorySettingsStore())

    def _workflow_with_failure(self, failing_config: dict[str, str], failing_detail: str = "") -> Workflow:
        return Workflow(
            id="wf_error_policy",
            name="Error Policy Workflow",
            trigger="manual",
            action="graph",
            graph={
                "version": 1,
                "nodes": [
                    {
                        "id": "t1",
                        "name": "Start",
                        "node_type": "trigger",
                        "detail": "trigger:manual",
                        "summary": "Start execution",
                        "x": 0,
                        "y": 0,
                        "config": {
                            "trigger_mode": "manual",
                        },
                    },
                    {
                        "id": "a1",
                        "name": "Failing Action",
                        "node_type": "action",
                        "detail": failing_detail,
                        "summary": "Intentionally fails",
                        "x": 220,
                        "y": 0,
                        "config": failing_config,
                    },
                    {
                        "id": "a2",
                        "name": "Recovery Action",
                        "node_type": "action",
                        "detail": "integration:standard",
                        "summary": "Continue path",
                        "x": 440,
                        "y": 0,
                        "config": {
                            "integration": "standard",
                        },
                    },
                ],
                "edges": [
                    {
                        "id": "e1",
                        "source_node_id": "t1",
                        "target_node_id": "a1",
                        "condition": "next",
                    },
                    {
                        "id": "e2",
                        "source_node_id": "a1",
                        "target_node_id": "a2",
                        "condition": "next",
                    },
                ],
            },
        )

    @staticmethod
    def _success_node_ids(run) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for event in run.timeline:
            if str(event.get("status", "")).strip().lower() != "success":
                continue
            node_id = str(event.get("node_id", "")).strip()
            if node_id and node_id not in seen:
                seen.add(node_id)
                ordered.append(node_id)
        return ordered

    def test_default_error_policy_fails_run(self):
        workflow = self._workflow_with_failure(
            {
                "integration": "http_request",
                "method": "POST",
                "retry_max": "0",
            },
        )

        run = self.engine.run_workflow(workflow, persist=False)

        self.assertEqual("failed", run.status)
        self.assertEqual("a1", run.last_failed_node_id)
        self.assertEqual(["t1"], self._success_node_ids(run))

    def test_on_error_continue_moves_to_next_node(self):
        workflow = self._workflow_with_failure(
            {
                "integration": "http_request",
                "method": "POST",
                "retry_max": "0",
                "on_error": "continue",
            },
        )

        run = self.engine.run_workflow(workflow, persist=False)

        self.assertEqual("success", run.status)
        self.assertIn("a2", self._success_node_ids(run))
        warning_messages = [
            str(event.get("message", ""))
            for event in run.timeline
            if str(event.get("status", "")).strip().lower() == "warning"
        ]
        self.assertTrue(any("on_error='continue'" in message for message in warning_messages))

    def test_on_error_goto_routes_to_target_node(self):
        workflow = self._workflow_with_failure(
            {
                "integration": "http_request",
                "method": "POST",
                "retry_max": "0",
                "on_error": "goto:a2",
            },
        )

        run = self.engine.run_workflow(workflow, persist=False)

        self.assertEqual("success", run.status)
        self.assertIn("a2", self._success_node_ids(run))
        warning_messages = [
            str(event.get("message", ""))
            for event in run.timeline
            if str(event.get("status", "")).strip().lower() == "warning"
        ]
        self.assertTrue(any("on_error='goto:a2'" in message for message in warning_messages))

    def test_on_error_goto_missing_target_fails_run(self):
        workflow = self._workflow_with_failure(
            {
                "integration": "http_request",
                "method": "POST",
                "retry_max": "0",
                "on_error": "goto:missing_node",
            },
        )

        run = self.engine.run_workflow(workflow, persist=False)

        self.assertEqual("failed", run.status)
        self.assertEqual("a1", run.last_failed_node_id)
        self.assertIn("missing_node", run.summary)


if __name__ == "__main__":
    unittest.main()
