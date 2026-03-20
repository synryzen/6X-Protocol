import json
import unittest

from src.models.canvas_node import CanvasNode
from src.services.execution_engine import ExecutionEngine


class _InMemorySettingsStore:
    def __init__(self, values=None):
        self._values = values or {}

    def load_settings(self):
        return dict(self._values)


class ExecutionEngineActionAliasTests(unittest.TestCase):
    def setUp(self):
        self.engine = ExecutionEngine(settings_store=_InMemorySettingsStore())

    def test_postgres_sql_accepts_endpoint_alias_in_payload(self):
        captured = {"command": ""}

        def fake_shell(command, _input_payload, cancel_check=None, timeout_seconds=60.0):
            captured["command"] = command
            return "42"

        self.engine._integration_shell_command = fake_shell  # type: ignore[method-assign]
        node = CanvasNode(
            id="a1",
            name="Postgres Action",
            node_type="action",
            detail="",
            summary="",
            x=0,
            y=0,
            config={
                "integration": "postgres_sql",
                "payload": json.dumps(
                    {
                        "endpoint": "postgresql://postgres:secret@localhost:5432/demo",
                        "query": "select 42;",
                    }
                ),
            },
        )

        logs, output = self.engine.execute_action_node_for_test(node)
        self.assertIn("executed Postgres SQL", logs[0])
        self.assertEqual("42", output)
        self.assertIn('psql "postgresql://postgres:secret@localhost:5432/demo"', captured["command"])
        self.assertIn('select 42;', captured["command"])

    def test_redis_command_accepts_request_url_and_query_aliases(self):
        captured = {"command": ""}

        def fake_shell(command, _input_payload, cancel_check=None, timeout_seconds=60.0):
            captured["command"] = command
            return "PONG"

        self.engine._integration_shell_command = fake_shell  # type: ignore[method-assign]
        node = CanvasNode(
            id="a2",
            name="Redis Action",
            node_type="action",
            detail="",
            summary="",
            x=0,
            y=0,
            config={
                "integration": "redis_command",
                "payload": json.dumps(
                    {
                        "request_url": "redis://127.0.0.1:6379/0",
                        "query": "PING",
                    }
                ),
            },
        )

        logs, output = self.engine.execute_action_node_for_test(node)
        self.assertIn("executed Redis command", logs[0])
        self.assertEqual("PONG", output)
        self.assertIn('redis-cli -u "redis://127.0.0.1:6379/0" PING', captured["command"])


if __name__ == "__main__":
    unittest.main()
