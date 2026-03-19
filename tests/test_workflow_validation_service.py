import unittest

from src.models.canvas_edge import CanvasEdge
from src.models.canvas_node import CanvasNode
from src.services.workflow_validation_service import WorkflowValidationService


class DummySettingsStore:
    def __init__(self, settings):
        self._settings = dict(settings)

    def load_settings(self):
        return dict(self._settings)


class WorkflowValidationServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = WorkflowValidationService(settings_store=DummySettingsStore({}))

    def test_required_field_alias_allows_webhook_url_via_url(self):
        trigger = CanvasNode(
            id="node_trigger",
            name="Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=20,
            y=20,
            config={"trigger_mode": "manual"},
        )
        action = CanvasNode(
            id="node_action",
            name="Slack",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "slack_webhook",
                "url": "https://hooks.slack.com/services/T/B/K",
                "message": "hello",
            },
        )
        edges = [
            CanvasEdge(
                id="edge_1",
                source_node_id=trigger.id,
                target_node_id=action.id,
                condition="",
            )
        ]

        result = self.service.validate_graph([trigger, action], edges, "Webhook Alias")
        self.assertTrue(result.ok, result.errors)

    def test_missing_required_field_reports_error(self):
        trigger = CanvasNode(
            id="node_trigger",
            name="Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=20,
            y=20,
            config={"trigger_mode": "manual"},
        )
        action = CanvasNode(
            id="node_action",
            name="Weather",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "openweather_current",
                "api_key": "abc",
            },
        )
        edges = [
            CanvasEdge(
                id="edge_1",
                source_node_id=trigger.id,
                target_node_id=action.id,
                condition="",
            )
        ]

        result = self.service.validate_graph([trigger, action], edges, "Missing Field")
        self.assertFalse(result.ok)
        self.assertTrue(any("missing required field 'location'" in item for item in result.errors))

    def test_validate_workflow_parses_legacy_links(self):
        graph = {
            "nodes": [
                {
                    "id": "node_trigger",
                    "name": "Trigger",
                    "node_type": "Trigger",
                    "x": 20,
                    "y": 20,
                    "config": {"trigger_mode": "manual"},
                },
                {
                    "id": "node_action",
                    "name": "Action",
                    "node_type": "Action",
                    "x": 220,
                    "y": 20,
                    "config": {"integration": "standard"},
                },
            ],
            "links": [
                {
                    "from": "node_trigger",
                    "to": "node_action",
                    "type": "next",
                }
            ],
        }
        from src.models.workflow import Workflow

        result = self.service.validate_workflow(
            Workflow(id="wf_1", name="Legacy", trigger="", action="", graph=graph)
        )
        self.assertTrue(result.ok, result.errors)

    def test_required_field_can_be_satisfied_from_saved_settings(self):
        service = WorkflowValidationService(
            settings_store=DummySettingsStore(
                {
                    "slack_webhook_url": "https://hooks.slack.com/services/T/B/K",
                }
            )
        )
        trigger = CanvasNode(
            id="node_trigger",
            name="Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=20,
            y=20,
            config={"trigger_mode": "manual"},
        )
        action = CanvasNode(
            id="node_action",
            name="Slack",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={"integration": "slack_webhook"},
        )
        edges = [
            CanvasEdge(
                id="edge_1",
                source_node_id=trigger.id,
                target_node_id=action.id,
                condition="",
            )
        ]
        result = service.validate_graph([trigger, action], edges, "Settings Fallback")
        self.assertTrue(result.ok, result.errors)


if __name__ == "__main__":
    unittest.main()
