import http.server
import json
import tempfile
import time
import unittest
from pathlib import Path
import sys
import types
import threading
from datetime import UTC, datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "api"))

# Keep this unit test lightweight outside the Docker API venv.
schemas_stub = types.ModuleType("app.schemas")
schemas_stub.utc_now_iso = lambda: datetime.now(UTC).isoformat()
sys.modules.setdefault("app.schemas", schemas_stub)

from app.run_controller import RunController, TERMINAL_STATUSES
from app.storage import JsonStore


class DockerRunControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(data_dir=self.tmp.name)
        self.controller = RunController(store=self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _wait_for_terminal(self, run_id: str, timeout: float = 3.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            run = self.controller.get_run(run_id)
            if run and str(run.get("status", "")).strip().lower() in TERMINAL_STATUSES:
                return run
            time.sleep(0.02)
        self.fail(f"Timed out waiting for terminal status for run {run_id}")

    @staticmethod
    def _success_node_order(run: dict) -> list[str]:
        order: list[str] = []
        seen: set[str] = set()
        for event in run.get("node_results", []):
            if str(event.get("status", "")).strip().lower() != "success":
                continue
            node_id = str(event.get("node_id", "")).strip()
            if node_id and node_id not in seen:
                seen.add(node_id)
                order.append(node_id)
        return order

    def test_edges_control_execution_order(self):
        workflow = {
            "id": "wf_edges",
            "name": "Edge Flow",
            "graph": {
                "nodes": [
                    {"id": "n1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {"id": "n3", "name": "Connected", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "n2", "name": "Detached", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"source": "n1", "target": "n3", "type": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("success", completed.get("status"))
        self.assertEqual(["n1", "n2", "n3"], self._success_node_order(completed))

    def test_condition_branch_routes_false_path(self):
        workflow = {
            "id": "wf_branch",
            "name": "Condition Flow",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Trigger", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "c1",
                        "name": "Condition",
                        "type": "condition",
                        "config": {"expression": "always_false", "simulate_delay_ms": 0},
                    },
                    {"id": "a1", "name": "True Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "a2", "name": "False Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "c1", "condition": "next"},
                    {"source_node_id": "c1", "target_node_id": "a1", "condition": "true"},
                    {"source_node_id": "c1", "target_node_id": "a2", "condition": "false"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("success", completed.get("status"))
        self.assertEqual(["t1", "c1", "a2"], self._success_node_order(completed))

    def test_condition_mode_not_contains_routes_true_path(self):
        workflow = {
            "id": "wf_branch_not_contains",
            "name": "Condition Not Contains",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Trigger", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "c1",
                        "name": "Condition",
                        "type": "condition",
                        "config": {
                            "condition_mode": "not_contains",
                            "condition_value": "error",
                            "simulate_delay_ms": 0,
                        },
                    },
                    {"id": "a1", "name": "True Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "a2", "name": "False Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "c1", "condition": "next"},
                    {"source_node_id": "c1", "target_node_id": "a1", "condition": "true"},
                    {"source_node_id": "c1", "target_node_id": "a2", "condition": "false"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("success", completed.get("status"))
        self.assertEqual(["t1", "c1", "a1"], self._success_node_order(completed))

    def test_condition_mode_min_len_routes_false_path(self):
        workflow = {
            "id": "wf_branch_min_len",
            "name": "Condition Min Length",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Trigger", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "c1",
                        "name": "Condition",
                        "type": "condition",
                        "config": {
                            "condition_mode": "min_len",
                            "condition_min_len": 40,
                            "simulate_delay_ms": 0,
                        },
                    },
                    {"id": "a1", "name": "True Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "a2", "name": "False Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "c1", "condition": "next"},
                    {"source_node_id": "c1", "target_node_id": "a1", "condition": "true"},
                    {"source_node_id": "c1", "target_node_id": "a2", "condition": "false"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("success", completed.get("status"))
        self.assertEqual(["t1", "c1", "a2"], self._success_node_order(completed))

    def test_replay_start_node_runs_descendants_only(self):
        workflow = {
            "id": "wf_replay",
            "name": "Replay Flow",
            "graph": {
                "nodes": [
                    {"id": "n1", "name": "First", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {"id": "n3", "name": "Third", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "n2", "name": "Second", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"from": "n1", "to": "n2", "type": "next"},
                    {"from": "n2", "to": "n3", "type": "next"},
                ],
            },
        }

        run = self.controller.start(workflow, start_node_id="n2", trigger="retry")
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("success", completed.get("status"))
        self.assertEqual(["n2", "n3"], self._success_node_order(completed))

    def test_parallel_branches_join_before_merge_node(self):
        workflow = {
            "id": "wf_join",
            "name": "Join Flow",
            "graph": {
                "settings": {"max_parallel": 3},
                "nodes": [
                    {"id": "s1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {"id": "b1", "name": "Branch A", "type": "action", "config": {"simulate_delay_ms": 80}},
                    {"id": "b2", "name": "Branch B", "type": "action", "config": {"simulate_delay_ms": 80}},
                    {"id": "j1", "name": "Join", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"source": "s1", "target": "b1", "type": "next"},
                    {"source": "s1", "target": "b2", "type": "next"},
                    {"source": "b1", "target": "j1", "type": "next"},
                    {"source": "b2", "target": "j1", "type": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))

        node_results = completed.get("node_results", [])
        success_indices = {}
        join_running_index = None
        for idx, event in enumerate(node_results):
            node_id = str(event.get("node_id", "")).strip()
            status = str(event.get("status", "")).strip().lower()
            if status == "success" and node_id in {"b1", "b2"}:
                success_indices[node_id] = idx
            if status == "running" and node_id == "j1":
                join_running_index = idx

        self.assertIn("b1", success_indices)
        self.assertIn("b2", success_indices)
        self.assertIsNotNone(join_running_index)
        self.assertGreater(join_running_index, success_indices["b1"])
        self.assertGreater(join_running_index, success_indices["b2"])

    def test_condition_pruned_branch_does_not_block_join(self):
        workflow = {
            "id": "wf_pruned_join",
            "name": "Pruned Join Flow",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Trigger", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "c1",
                        "name": "Condition",
                        "type": "condition",
                        "config": {"expression": "always_false", "simulate_delay_ms": 0},
                    },
                    {"id": "a1", "name": "True Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "a2", "name": "False Path", "type": "action", "config": {"simulate_delay_ms": 0}},
                    {"id": "j1", "name": "Merge", "type": "action", "config": {"simulate_delay_ms": 0}},
                ],
                "edges": [
                    {"source": "t1", "target": "c1", "type": "next"},
                    {"source": "c1", "target": "a1", "type": "true"},
                    {"source": "c1", "target": "a2", "type": "false"},
                    {"source": "a1", "target": "j1", "type": "next"},
                    {"source": "a2", "target": "j1", "type": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))

        successful = self._success_node_order(completed)
        self.assertIn("a2", successful)
        self.assertIn("j1", successful)
        self.assertNotIn("a1", successful)

        skipped_nodes = {
            str(event.get("node_id", "")).strip()
            for event in completed.get("node_results", [])
            if str(event.get("status", "")).strip().lower() == "skipped"
        }
        self.assertIn("a1", skipped_nodes)

    def test_http_request_action_executes_against_local_server(self):
        class SuccessHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib handler name
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                body = raw.decode("utf-8", errors="replace")
                payload = json.dumps({"ok": True, "received": body}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *_args):  # noqa: A003 - stdlib signature
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SuccessHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_port)
            workflow = {
                "id": "wf_http_ok",
                "name": "HTTP Action",
                "graph": {
                    "nodes": [
                        {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                        {
                            "id": "a1",
                            "name": "Send HTTP",
                            "type": "action",
                            "config": {
                                "integration": "http_request",
                                "method": "POST",
                                "url": f"http://127.0.0.1:{port}/hook",
                                "payload": '{"message":"hello"}',
                                "simulate_delay_ms": 0,
                            },
                        },
                    ],
                    "edges": [
                        {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                    ],
                },
            }

            run = self.controller.start(workflow)
            completed = self._wait_for_terminal(run["id"])
            self.assertEqual("success", completed.get("status"))
            self.assertEqual(["t1", "a1"], self._success_node_order(completed))

            action_success = [
                item
                for item in completed.get("node_results", [])
                if str(item.get("node_id", "")).strip() == "a1"
                and str(item.get("status", "")).strip().lower() == "success"
            ]
            self.assertTrue(action_success, "Expected action node success event.")
            preview = str(action_success[-1].get("output_preview", ""))
            self.assertIn("integration:http_request", preview)
            self.assertIn("status:200", preview)
        finally:
            server.shutdown()
            server.server_close()

    def test_http_request_action_retries_after_http_error(self):
        attempts = {"count": 0}

        class RetryThenSuccessHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib handler name
                attempts["count"] += 1
                if attempts["count"] == 1:
                    self.send_response(500)
                    payload = b'{"error":"temporary"}'
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                payload = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *_args):  # noqa: A003 - stdlib signature
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RetryThenSuccessHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_port)
            workflow = {
                "id": "wf_http_retry",
                "name": "HTTP Retry Action",
                "graph": {
                    "settings": {"retry_max": 0, "retry_backoff_ms": 0, "timeout_sec": 0},
                    "nodes": [
                        {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                        {
                            "id": "a1",
                            "name": "Send HTTP",
                            "type": "action",
                            "config": {
                                "integration": "http_request",
                                "method": "POST",
                                "url": f"http://127.0.0.1:{port}/retry",
                                "payload": '{"message":"retry"}',
                                "retry_max": 1,
                                "retry_backoff_ms": 0,
                                "timeout_sec": 5,
                                "simulate_delay_ms": 0,
                            },
                        },
                    ],
                    "edges": [
                        {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                    ],
                },
            }

            run = self.controller.start(workflow)
            completed = self._wait_for_terminal(run["id"])

            self.assertEqual("success", completed.get("status"))
            self.assertEqual(2, attempts["count"])

            statuses = [
                str(item.get("status", "")).strip().lower()
                for item in completed.get("node_results", [])
                if str(item.get("node_id", "")).strip() == "a1"
            ]
            self.assertIn("failed", statuses)
            self.assertIn("retrying", statuses)
            self.assertIn("success", statuses)
        finally:
            server.shutdown()
            server.server_close()

    def test_node_type_defaults_retry_action_when_graph_defaults_unset(self):
        workflow = {
            "id": "wf_default_action_retry",
            "name": "Default Action Retry",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Transient Action",
                        "type": "action",
                        "config": {
                            "integration": "standard",
                            "simulate_delay_ms": 0,
                            "simulate_failure_attempts": 1,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("success", completed.get("status"))
        statuses = [
            str(item.get("status", "")).strip().lower()
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "a1"
        ]
        self.assertIn("failed", statuses)
        self.assertIn("retrying", statuses)
        self.assertIn("success", statuses)

    def test_explicit_run_retry_override_disables_node_default_retry(self):
        workflow = {
            "id": "wf_no_retry_override",
            "name": "Explicit No Retry",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Transient Action",
                        "type": "action",
                        "config": {
                            "integration": "standard",
                            "simulate_delay_ms": 0,
                            "simulate_failure_attempts": 1,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow, retry_max=0, retry_backoff_ms=0, timeout_sec=30.0)
        completed = self._wait_for_terminal(run["id"])

        self.assertEqual("failed", completed.get("status"))
        statuses = [
            str(item.get("status", "")).strip().lower()
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "a1"
        ]
        self.assertIn("failed", statuses)
        self.assertNotIn("retrying", statuses)

    def test_shell_command_action_executes(self):
        workflow = {
            "id": "wf_shell_ok",
            "name": "Shell Action",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Run Shell",
                        "type": "action",
                        "config": {
                            "integration": "shell_command",
                            "command": "printf 'hello-from-shell'",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))

        action_success = [
            item
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "a1"
            and str(item.get("status", "")).strip().lower() == "success"
        ]
        self.assertTrue(action_success, "Expected action node success event.")
        preview = str(action_success[-1].get("output_preview", ""))
        self.assertIn("integration:shell_command", preview)
        self.assertIn("hello-from-shell", preview)

    def test_file_append_action_writes_to_disk(self):
        target_path = Path(self.tmp.name) / "output" / "run.log"
        workflow = {
            "id": "wf_file_append",
            "name": "File Append Action",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Append File",
                        "type": "action",
                        "config": {
                            "integration": "file_append",
                            "path": str(target_path),
                            "message": "file-append-ok",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        self.assertTrue(target_path.exists())
        content = target_path.read_text(encoding="utf-8")
        self.assertIn("file-append-ok", content)

    def test_sqlite_action_executes_query(self):
        db_path = Path(self.tmp.name) / "sqlite" / "runtime.db"
        workflow = {
            "id": "wf_sqlite_query",
            "name": "SQLite Action",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "SQLite Query",
                        "type": "action",
                        "config": {
                            "integration": "sqlite_sql",
                            "path": str(db_path),
                            "sql": "select 42 as value;",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))

        action_success = [
            item
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "a1"
            and str(item.get("status", "")).strip().lower() == "success"
        ]
        self.assertTrue(action_success, "Expected action node success event.")
        preview = str(action_success[-1].get("output_preview", ""))
        self.assertIn("integration:sqlite_sql", preview)
        self.assertIn("rows:1", preview)

    def test_postgres_sql_accepts_endpoint_alias_from_payload(self):
        captured: dict[str, object] = {}

        def fake_run_command(args, *, timeout_sec, integration, env=None):
            captured["args"] = list(args)
            captured["timeout_sec"] = timeout_sec
            captured["integration"] = integration
            return "42"

        self.controller._run_command = fake_run_command  # type: ignore[method-assign]

        workflow = {
            "id": "wf_pg_endpoint_alias",
            "name": "Postgres Alias",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Postgres Query",
                        "type": "action",
                        "config": {
                            "integration": "postgres_sql",
                            "payload": json.dumps(
                                {
                                    "endpoint": "postgresql://postgres:secret@localhost:5432/demo",
                                    "query": "select 42;",
                                }
                            ),
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [{"source": "t1", "target": "a1", "type": "next"}],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        self.assertEqual("postgres_sql", captured.get("integration"))
        args = captured.get("args")
        self.assertIsInstance(args, list)
        self.assertGreaterEqual(len(args), 5)
        self.assertEqual("psql", args[0])
        self.assertEqual("postgresql://postgres:secret@localhost:5432/demo", args[1])
        self.assertEqual("select 42;", args[-1])

    def test_redis_command_accepts_request_url_and_query_aliases(self):
        captured: dict[str, object] = {}

        def fake_run_command(args, *, timeout_sec, integration, env=None):
            captured["args"] = list(args)
            captured["timeout_sec"] = timeout_sec
            captured["integration"] = integration
            return "PONG"

        self.controller._run_command = fake_run_command  # type: ignore[method-assign]

        workflow = {
            "id": "wf_redis_aliases",
            "name": "Redis Alias",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Redis Query",
                        "type": "action",
                        "config": {
                            "integration": "redis_command",
                            "payload": json.dumps(
                                {
                                    "request_url": "redis://127.0.0.1:6379/0",
                                    "query": "PING",
                                }
                            ),
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [{"source": "t1", "target": "a1", "type": "next"}],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        self.assertEqual("redis_command", captured.get("integration"))
        args = captured.get("args")
        self.assertIsInstance(args, list)
        self.assertIn("-u", args)
        self.assertIn("redis://127.0.0.1:6379/0", args)
        self.assertIn("PING", args)

    def test_pick_url_accepts_script_url_alias(self):
        picked = self.controller._pick_url({"script_url": "https://example.com/script"})
        self.assertEqual("https://example.com/script", picked)

    def test_generic_api_integration_sends_bearer_request(self):
        captured = {"auth": "", "method": "", "body": ""}

        class GenericApiHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib handler name
                captured["auth"] = str(self.headers.get("Authorization", ""))
                captured["method"] = "POST"
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                captured["body"] = raw.decode("utf-8", errors="replace")
                payload = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *_args):  # noqa: A003 - stdlib signature
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GenericApiHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_port)
            workflow = {
                "id": "wf_generic_api",
                "name": "Generic API Action",
                "graph": {
                    "nodes": [
                        {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                        {
                            "id": "a1",
                            "name": "GitHub API",
                            "type": "action",
                            "config": {
                                "integration": "github_rest",
                                "url": f"http://127.0.0.1:{port}/repos",
                                "method": "POST",
                                "api_key": "token-123",
                                "payload": '{"test":true}',
                                "simulate_delay_ms": 0,
                            },
                        },
                    ],
                    "edges": [
                        {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                    ],
                },
            }

            run = self.controller.start(workflow)
            completed = self._wait_for_terminal(run["id"])
            self.assertEqual("success", completed.get("status"))
            self.assertEqual("POST", captured["method"])
            self.assertEqual("Bearer token-123", captured["auth"])
            self.assertIn('"test":true', captured["body"])
        finally:
            server.shutdown()
            server.server_close()

    def test_twilio_sms_integration_sends_basic_auth_form_request(self):
        captured = {"auth": "", "body": ""}

        class TwilioHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib handler name
                captured["auth"] = str(self.headers.get("Authorization", ""))
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                captured["body"] = raw.decode("utf-8", errors="replace")
                payload = b'{"sid":"SM123"}'
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *_args):  # noqa: A003 - stdlib signature
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TwilioHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_port)
            workflow = {
                "id": "wf_twilio_api",
                "name": "Twilio SMS Action",
                "graph": {
                    "nodes": [
                        {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                        {
                            "id": "a1",
                            "name": "Twilio SMS",
                            "type": "action",
                            "config": {
                                "integration": "twilio_sms",
                                "url": f"http://127.0.0.1:{port}/messages",
                                "account_sid": "AC123",
                                "auth_token": "secret",
                                "from": "+15550001111",
                                "to": "+15550002222",
                                "message": "hello",
                                "simulate_delay_ms": 0,
                            },
                        },
                    ],
                    "edges": [
                        {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                    ],
                },
            }

            run = self.controller.start(workflow)
            completed = self._wait_for_terminal(run["id"])
            self.assertEqual("success", completed.get("status"))
            self.assertTrue(captured["auth"].startswith("Basic "))
            self.assertIn("From=%2B15550001111", captured["body"])
            self.assertIn("To=%2B15550002222", captured["body"])
            self.assertIn("Body=hello", captured["body"])
        finally:
            server.shutdown()
            server.server_close()

    def test_on_error_continue_allows_run_to_progress(self):
        workflow = {
            "id": "wf_on_error_continue",
            "name": "On Error Continue",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Broken HTTP",
                        "type": "action",
                        "config": {
                            "integration": "http_request",
                            "method": "POST",
                            "retry_max": 0,
                            "simulate_delay_ms": 0,
                            "on_error": "continue",
                        },
                    },
                    {
                        "id": "a2",
                        "name": "Recovery",
                        "type": "action",
                        "config": {
                            "integration": "standard",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                    {"source_node_id": "a1", "target_node_id": "a2", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        self.assertIn("a2", self._success_node_order(completed))

        a1_statuses = [
            str(item.get("status", "")).strip().lower()
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "a1"
        ]
        self.assertIn("failed", a1_statuses)
        self.assertIn("warning", a1_statuses)

    def test_on_error_goto_routes_to_target_node(self):
        workflow = {
            "id": "wf_on_error_goto",
            "name": "On Error Goto",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Broken HTTP",
                        "type": "action",
                        "config": {
                            "integration": "http_request",
                            "method": "POST",
                            "retry_max": 0,
                            "simulate_delay_ms": 0,
                            "on_error": "goto:a3",
                        },
                    },
                    {
                        "id": "a2",
                        "name": "Default Next",
                        "type": "action",
                        "config": {"integration": "standard", "simulate_delay_ms": 0},
                    },
                    {
                        "id": "a3",
                        "name": "Goto Target",
                        "type": "action",
                        "config": {"integration": "standard", "simulate_delay_ms": 0},
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                    {"source_node_id": "a1", "target_node_id": "a2", "condition": "next"},
                    {"source_node_id": "a1", "target_node_id": "a3", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        successful = self._success_node_order(completed)
        self.assertIn("a3", successful)
        self.assertNotIn("a2", successful)

    def test_trigger_schedule_interval_includes_interval_output(self):
        workflow = {
            "id": "wf_trigger_schedule",
            "name": "Trigger Schedule",
            "graph": {
                "nodes": [
                    {
                        "id": "t1",
                        "name": "Schedule Trigger",
                        "type": "trigger",
                        "config": {
                            "trigger_mode": "schedule_interval",
                            "trigger_value": "30",
                            "simulate_delay_ms": 0,
                        },
                    },
                    {
                        "id": "a1",
                        "name": "Action",
                        "type": "action",
                        "config": {"integration": "standard", "simulate_delay_ms": 0},
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        trigger_success = [
            item
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "t1"
            and str(item.get("status", "")).strip().lower() == "success"
        ]
        self.assertTrue(trigger_success, "Expected trigger success event.")
        output_preview = str(trigger_success[-1].get("output_preview", ""))
        self.assertIn("trigger:schedule_interval:30s", output_preview)

    def test_trigger_invalid_cron_marks_run_failed(self):
        workflow = {
            "id": "wf_trigger_bad_cron",
            "name": "Trigger Bad Cron",
            "graph": {
                "nodes": [
                    {
                        "id": "t1",
                        "name": "Cron Trigger",
                        "type": "trigger",
                        "config": {
                            "trigger_mode": "cron",
                            "trigger_value": "not-a-cron",
                            "simulate_delay_ms": 0,
                        },
                    },
                    {
                        "id": "a1",
                        "name": "Action",
                        "type": "action",
                        "config": {"integration": "standard", "simulate_delay_ms": 0},
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("failed", completed.get("status"))
        self.assertIn("cron expression is invalid", str(completed.get("summary", "")).lower())

    def test_postgres_sql_missing_fields_fails_cleanly(self):
        workflow = {
            "id": "wf_postgres_missing",
            "name": "Postgres Missing Fields",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Postgres",
                        "type": "action",
                        "config": {
                            "integration": "postgres_sql",
                            "sql": "select 1;",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("failed", completed.get("status"))
        self.assertIn("postgres_sql", str(completed.get("summary", "")))
        self.assertIn("connection_url", str(completed.get("summary", "")))

    def test_redis_command_missing_command_fails_cleanly(self):
        workflow = {
            "id": "wf_redis_missing",
            "name": "Redis Missing Command",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Redis",
                        "type": "action",
                        "config": {
                            "integration": "redis_command",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("failed", completed.get("status"))
        self.assertIn("redis_command", str(completed.get("summary", "")))
        self.assertIn("requires command", str(completed.get("summary", "")))

    def test_trigger_execution_defaults_follow_mode_profiles(self):
        node = {
            "id": "t_webhook_defaults",
            "name": "Webhook Trigger",
            "type": "trigger",
            "config": {"trigger_mode": "webhook"},
        }
        self.assertEqual(
            {"retry_max": 1.0, "retry_backoff_ms": 150.0, "timeout_sec": 45.0},
            self.controller._node_execution_defaults(node),
        )

    def test_trigger_execution_defaults_infer_mode_from_detail(self):
        node = {
            "id": "t_schedule_defaults",
            "name": "Schedule Trigger",
            "type": "trigger",
            "detail": "schedule:30",
            "config": {},
        }
        self.assertEqual(
            {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 20.0},
            self.controller._node_execution_defaults(node),
        )

    def test_handoff_integration_executes_chain_and_uses_heavy_defaults(self):
        node = {
            "id": "a_handoff_defaults",
            "name": "Handoff Node",
            "type": "action",
            "config": {"integration": "handoff"},
        }
        self.assertEqual(
            {"retry_max": 1.0, "retry_backoff_ms": 400.0, "timeout_sec": 90.0},
            self.controller._node_execution_defaults(node),
        )

        workflow = {
            "id": "wf_handoff",
            "name": "Handoff Flow",
            "graph": {
                "nodes": [
                    {"id": "t1", "name": "Start", "type": "trigger", "config": {"simulate_delay_ms": 0}},
                    {
                        "id": "a1",
                        "name": "Handoff",
                        "type": "action",
                        "config": {
                            "integration": "handoff",
                            "bot_chain": "Planner > Writer",
                            "message": "Draft release notes",
                            "simulate_delay_ms": 0,
                        },
                    },
                ],
                "edges": [
                    {"source_node_id": "t1", "target_node_id": "a1", "condition": "next"},
                ],
            },
        }

        run = self.controller.start(workflow)
        completed = self._wait_for_terminal(run["id"])
        self.assertEqual("success", completed.get("status"))
        self.assertEqual(["t1", "a1"], self._success_node_order(completed))

        action_success = [
            item
            for item in completed.get("node_results", [])
            if str(item.get("node_id", "")).strip() == "a1"
            and str(item.get("status", "")).strip().lower() == "success"
        ]
        self.assertTrue(action_success, "Expected handoff action success event.")
        preview = str(action_success[-1].get("output_preview", ""))
        self.assertIn("integration:handoff", preview)
        self.assertIn("chain:Planner > Writer", preview)


if __name__ == "__main__":
    unittest.main()
