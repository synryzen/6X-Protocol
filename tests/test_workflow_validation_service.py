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

    def test_google_sheets_required_fields_can_be_read_from_payload(self):
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
            name="Sheets Append",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "google_sheets",
                "api_key": "token",
                "payload": (
                    '{"spreadsheet_id":"sheet_123","range":"Sheet1!A:B","values":[["ok"]]}'
                ),
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

        result = self.service.validate_graph([trigger, action], edges, "Sheets Payload")
        self.assertTrue(result.ok, result.errors)

    def test_http_request_invalid_url_reports_error(self):
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
            name="HTTP",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "http_request",
                "url": "localhost:8080/hook",
                "method": "POST",
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
        result = self.service.validate_graph([trigger, action], edges, "Invalid URL")
        self.assertFalse(result.ok)
        self.assertTrue(any("invalid URL" in item for item in result.errors))

    def test_http_request_invalid_method_reports_error(self):
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
            name="HTTP",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "http_request",
                "url": "https://example.com/hook",
                "method": "FETCH",
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
        result = self.service.validate_graph([trigger, action], edges, "Invalid Method")
        self.assertFalse(result.ok)
        self.assertTrue(any("invalid HTTP method" in item for item in result.errors))

    def test_trigger_schedule_requires_numeric_interval(self):
        trigger = CanvasNode(
            id="node_trigger",
            name="Interval Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=20,
            y=20,
            config={"trigger_mode": "schedule_interval", "trigger_value": "abc"},
        )
        action = CanvasNode(
            id="node_action",
            name="Action",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={"integration": "standard"},
        )
        edges = [
            CanvasEdge(
                id="edge_1",
                source_node_id=trigger.id,
                target_node_id=action.id,
                condition="",
            )
        ]
        result = self.service.validate_graph([trigger, action], edges, "Trigger Interval")
        self.assertFalse(result.ok)
        self.assertTrue(any("interval 'abc' is not numeric" in item for item in result.errors))

    def test_email_integration_validates_address_format(self):
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
            name="Email",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "resend_email",
                "api_key": "re_123",
                "to": "bad-address",
                "from": "sender@example.com",
                "url": "https://api.resend.com/emails",
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
        result = self.service.validate_graph([trigger, action], edges, "Bad Email")
        self.assertFalse(result.ok)
        self.assertTrue(any("invalid recipient email" in item for item in result.errors))

    def test_http_request_invalid_headers_json_reports_error(self):
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
            name="HTTP",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "http_request",
                "url": "https://example.com/hook",
                "method": "POST",
                "headers": "{not-json}",
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
        result = self.service.validate_graph([trigger, action], edges, "Bad Headers")
        self.assertFalse(result.ok)
        self.assertTrue(any("headers must be valid JSON" in item for item in result.errors))

    def test_postgres_connection_url_scheme_reports_error(self):
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
            name="Postgres",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "postgres_sql",
                "connection_url": "mysql://localhost/test",
                "sql": "select now();",
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
        result = self.service.validate_graph([trigger, action], edges, "Bad Postgres URL")
        self.assertFalse(result.ok)
        self.assertTrue(any("postgres://" in item.lower() for item in result.errors))

    def test_redis_connection_url_scheme_reports_error(self):
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
            name="Redis",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "redis_command",
                "connection_url": "http://localhost:6379",
                "command": "PING",
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
        result = self.service.validate_graph([trigger, action], edges, "Bad Redis URL")
        self.assertFalse(result.ok)
        self.assertTrue(any("redis://" in item.lower() for item in result.errors))

    def test_s3_command_prefix_reports_warning(self):
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
            name="S3",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "s3_cli",
                "command": "ls /tmp",
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
        result = self.service.validate_graph([trigger, action], edges, "S3 Warning")
        self.assertTrue(result.ok)
        self.assertTrue(any("aws s3" in item.lower() or "start with 's3'" in item.lower() for item in result.warnings))

    def test_on_error_goto_requires_existing_node_target(self):
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
            name="Action",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "standard",
                "on_error": "goto",
                "error_target_node_id": "missing_node",
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
        result = self.service.validate_graph([trigger, action], edges, "on_error target")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("goto:missing_node" in item.lower() and "does not exist" in item.lower() for item in result.errors)
        )

    def test_on_error_continue_without_outgoing_edge_warns(self):
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
            name="Action",
            node_type="Action",
            detail="",
            summary="",
            x=220,
            y=20,
            config={
                "integration": "standard",
                "on_error": "continue",
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
        result = self.service.validate_graph([trigger, action], edges, "on_error continue terminal")
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(
            any("on_error='continue'" in item.lower() and "no outgoing edge" in item.lower() for item in result.warnings)
        )


if __name__ == "__main__":
    unittest.main()
