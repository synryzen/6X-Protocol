import tempfile
import time
import unittest
from pathlib import Path
import sys
import types
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


if __name__ == "__main__":
    unittest.main()
