import unittest

from src.models.canvas_edge import CanvasEdge
from src.models.canvas_node import CanvasNode
from src.services.execution_engine import ExecutionEngine


class _InMemorySettingsStore:
    def __init__(self, values=None):
        self._values = values or {}

    def load_settings(self):
        return dict(self._values)


class _DummyAIService:
    def generate(self, prompt, node_config=None, bot=None, system_prompt=""):
        return '{"status":"ok","prompt_preview":"%s"}' % str(prompt)[:20].replace('"', "'")


class ExecutionEngineNodePreviewTests(unittest.TestCase):
    def setUp(self):
        self.engine = ExecutionEngine(
            settings_store=_InMemorySettingsStore(),
            ai_service=_DummyAIService(),
        )

    def test_condition_preview_evaluates_and_selects_true_edge(self):
        expression = "contains:success"
        sample_input = "workflow success message"
        result = self.engine.evaluate_condition_for_test(expression, sample_input)
        self.assertTrue(result)

        outgoing = [
            CanvasEdge(id="e1", source_node_id="c1", target_node_id="n_true", condition="true"),
            CanvasEdge(id="e2", source_node_id="c1", target_node_id="n_false", condition="false"),
        ]
        target = self.engine.choose_condition_branch_for_test(outgoing, result)
        self.assertEqual("n_true", target)

    def test_ai_node_test_returns_output_and_logs(self):
        node = CanvasNode(
            id="ai_1",
            name="AI Summary",
            node_type="AI",
            detail="",
            summary="Summarize incoming data.",
            x=0,
            y=0,
            config={
                "provider": "local",
                "model": "dummy/model",
            },
        )
        logs, output = self.engine.execute_ai_node_for_test(
            node,
            input_context="example source payload",
        )
        self.assertTrue(any("executed" in item.lower() for item in logs))
        self.assertIn('"status":"ok"', output)


if __name__ == "__main__":
    unittest.main()
