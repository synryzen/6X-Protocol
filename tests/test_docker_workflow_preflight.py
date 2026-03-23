import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "api"))

from app.workflow_preflight import preflight_graph


class DockerWorkflowPreflightTests(unittest.TestCase):
    def test_preflight_flags_missing_edge_target(self):
        graph = {
            "nodes": [
                {"id": "t1", "name": "Start", "type": "trigger"},
                {"id": "a1", "name": "Action", "type": "action"},
            ],
            "edges": [
                {"source": "t1", "target": "missing", "type": "next"},
            ],
        }
        result = preflight_graph(graph, workflow_name="Smoke")
        self.assertFalse(result["ok"])
        self.assertGreaterEqual(result["error_count"], 1)
        self.assertTrue(any("does not exist" in msg for msg in result["errors"]))

    def test_preflight_flags_missing_required_integration_fields(self):
        graph = {
            "nodes": [
                {"id": "t1", "name": "Start", "type": "trigger"},
                {
                    "id": "a1",
                    "name": "Slack Send",
                    "type": "action",
                    "config": {"integration": "slack_webhook"},
                },
            ],
            "edges": [{"source": "t1", "target": "a1", "type": "next"}],
        }
        catalog = [
            {
                "key": "slack_webhook",
                "required_fields": ["webhook_url"],
            }
        ]
        result = preflight_graph(graph, workflow_name="Slack Flow", integration_catalog=catalog)
        self.assertFalse(result["ok"])
        self.assertTrue(any("webhook_url" in msg for msg in result["errors"]))

    def test_preflight_accepts_valid_linear_graph(self):
        graph = {
            "nodes": [
                {"id": "t1", "name": "Start", "type": "trigger", "config": {"trigger_mode": "manual"}},
                {"id": "a1", "name": "Action", "type": "action", "config": {"integration": "standard"}},
                {"id": "a2", "name": "Done", "type": "action", "config": {"integration": "standard"}},
            ],
            "edges": [
                {"source": "t1", "target": "a1", "type": "next"},
                {"source": "a1", "target": "a2", "type": "next"},
            ],
        }
        result = preflight_graph(graph, workflow_name="Linear")
        self.assertTrue(result["ok"])
        self.assertEqual(0, result["error_count"])
        self.assertGreaterEqual(result["warning_count"], 1)
        self.assertTrue(any("terminal" in msg.lower() for msg in result["warnings"]))


if __name__ == "__main__":
    unittest.main()

