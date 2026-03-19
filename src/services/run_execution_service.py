import threading
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

from src.models.run_record import RunRecord
from src.models.workflow import Workflow
from src.services.execution_engine import ExecutionEngine
from src.services.run_store import RunStore
from src.services.workflow_store import WorkflowStore
from src.services.workflow_validation_service import WorkflowValidationService


class RunExecutionService:
    def __init__(
        self,
        run_store: Optional[RunStore] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        workflow_store: Optional[WorkflowStore] = None,
        validation_service: Optional[WorkflowValidationService] = None,
    ):
        self.run_store = run_store or RunStore()
        self.execution_engine = execution_engine or ExecutionEngine(run_store=self.run_store)
        self.workflow_store = workflow_store or WorkflowStore()
        self.validation_service = validation_service or WorkflowValidationService()
        self._lock = threading.Lock()
        self._active_threads: Dict[str, threading.Thread] = {}
        self._cancel_events: Dict[str, threading.Event] = {}

    def start_workflow_run(
        self,
        workflow: Workflow,
        *,
        start_node_id: Optional[str] = None,
        initial_context: Optional[Dict[str, object]] = None,
        replay_of_run_id: str = "",
        attempt: int = 1,
        retry_count: int = 0,
        idempotency_key: str = "",
        skip_preflight: bool = False,
    ) -> RunRecord:
        run_id = str(uuid.uuid4())
        started_at = self._timestamp()
        preflight_steps: list[str] = ["Run started by user."]

        if not skip_preflight:
            validation = self.validation_service.validate_workflow(workflow)
            if validation.errors:
                failure_summary = (
                    f"Preflight failed with {len(validation.errors)} error(s). Execution blocked."
                )
                failed_steps = [f"Preflight error: {item}" for item in validation.errors]
                failed_steps.extend([f"Preflight warning: {item}" for item in validation.warnings])
                failed_run = RunRecord(
                    id=run_id,
                    workflow_id=workflow.id,
                    workflow_name=workflow.name,
                    status="failed",
                    started_at=started_at,
                    finished_at=started_at,
                    summary=failure_summary,
                    steps=failed_steps,
                    timeline=[
                        {
                            "timestamp": started_at,
                            "node_id": "preflight",
                            "node_name": "Preflight",
                            "status": "failed",
                            "message": failure_summary,
                            "attempt": "1",
                            "duration_ms": "0",
                        }
                    ],
                    replay_of_run_id=replay_of_run_id,
                    attempt=max(1, attempt),
                    retry_count=max(0, retry_count),
                    idempotency_key=idempotency_key.strip() or run_id,
                )
                self.run_store.add_run(failed_run)
                return failed_run
            if validation.warnings:
                preflight_steps.extend(
                    [f"Preflight warning: {item}" for item in validation.warnings[:4]]
                )

        initial_run = RunRecord(
            id=run_id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            status="running",
            started_at=started_at,
            finished_at="",
            summary="Run started.",
            steps=preflight_steps,
            replay_of_run_id=replay_of_run_id,
            attempt=max(1, attempt),
            retry_count=max(0, retry_count),
            idempotency_key=idempotency_key.strip() or run_id,
        )
        self.run_store.add_run(initial_run)

        cancel_event = threading.Event()
        worker = threading.Thread(
            target=self._run_background,
            args=(
                workflow,
                run_id,
                started_at,
                cancel_event,
                start_node_id,
                initial_context,
                replay_of_run_id,
                max(1, attempt),
                max(0, retry_count),
                idempotency_key.strip() or run_id,
                preflight_steps,
            ),
            daemon=True,
        )

        with self._lock:
            self._cancel_events[run_id] = cancel_event
            self._active_threads[run_id] = worker

        worker.start()
        return initial_run

    def retry_from_failed_node(self, run_id: str) -> Tuple[bool, str, Optional[RunRecord]]:
        target = self.run_store.get_run_by_id(run_id)
        if not target:
            return False, "Run not found.", None
        if target.status.strip().lower() != "failed":
            return False, "Only failed runs can be retried from failed node.", None
        if not target.workflow_id:
            return False, "Run does not include a workflow reference.", None
        if not target.last_failed_node_id:
            return False, "No failed node was recorded for this run.", None

        workflow = self.workflow_store.get_workflow_by_id(target.workflow_id)
        if not workflow:
            return False, "Original workflow no longer exists.", None

        replay_run = self.start_workflow_run(
            workflow,
            start_node_id=target.last_failed_node_id,
            replay_of_run_id=target.id,
            attempt=max(1, target.attempt + 1),
            retry_count=max(0, target.retry_count + 1),
            idempotency_key=target.idempotency_key or target.id,
        )
        return (
            True,
            f"Retry from failed node '{target.last_failed_node_name or target.last_failed_node_id}' started.",
            replay_run,
        )

    def approve_and_resume(self, run_id: str) -> Tuple[bool, str, Optional[RunRecord]]:
        target = self.run_store.get_run_by_id(run_id)
        if not target:
            return False, "Run not found.", None
        if target.status.strip().lower() != "waiting_approval":
            return False, "Run is not waiting for approval.", None
        if not target.workflow_id:
            return False, "Run does not include a workflow reference.", None
        if not target.pending_approval_node_id:
            return False, "No approval node was recorded for this run.", None

        workflow = self.workflow_store.get_workflow_by_id(target.workflow_id)
        if not workflow:
            return False, "Original workflow no longer exists.", None

        replay_run = self.start_workflow_run(
            workflow,
            start_node_id=target.pending_approval_node_id,
            initial_context={
                "approved_node_ids": [target.pending_approval_node_id],
            },
            replay_of_run_id=target.id,
            attempt=max(1, target.attempt + 1),
            retry_count=max(0, target.retry_count + 1),
            idempotency_key=target.idempotency_key or target.id,
        )
        return (
            True,
            f"Approval captured. Resumed from '{target.pending_approval_node_name or target.pending_approval_node_id}'.",
            replay_run,
        )

    def request_stop(self, run_id: str) -> Tuple[bool, str]:
        with self._lock:
            cancel_event = self._cancel_events.get(run_id)

        if not cancel_event:
            run = self.run_store.get_run_by_id(run_id)
            if not run:
                return False, "Run not found."
            if run.status == "running":
                return False, "Run stop is not available for this execution source."
            return False, f"Run is already {run.status.upper()}."

        if cancel_event.is_set():
            return False, "Stop already requested for this run."

        cancel_event.set()
        run = self.run_store.get_run_by_id(run_id)
        if run and run.status == "running":
            self.run_store.update_run(
                run_id,
                RunRecord(
                    id=run.id,
                    workflow_id=run.workflow_id,
                    workflow_name=run.workflow_name,
                    status=run.status,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    summary="Stop requested by user.",
                    steps=[*run.steps, "Stop requested by user."],
                    timeline=run.timeline,
                    last_failed_node_id=run.last_failed_node_id,
                    last_failed_node_name=run.last_failed_node_name,
                    pending_approval_node_id=run.pending_approval_node_id,
                    pending_approval_node_name=run.pending_approval_node_name,
                    replay_of_run_id=run.replay_of_run_id,
                    attempt=run.attempt,
                    retry_count=run.retry_count,
                    idempotency_key=run.idempotency_key,
                ),
            )

        return True, "Stop requested. Run will cancel at the next safe checkpoint."

    def is_active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._active_threads

    def _run_background(
        self,
        workflow: Workflow,
        run_id: str,
        started_at: str,
        cancel_event: threading.Event,
        start_node_id: Optional[str],
        initial_context: Optional[Dict[str, object]],
        replay_of_run_id: str,
        attempt: int,
        retry_count: int,
        idempotency_key: str,
        initial_steps: list[str],
    ):
        try:
            result = self.execution_engine.run_workflow(
                workflow,
                run_id=run_id,
                persist=False,
                cancel_check=cancel_event.is_set,
                initial_steps=initial_steps,
                start_node_id=start_node_id,
                initial_context=initial_context,
                replay_of_run_id=replay_of_run_id,
                attempt=attempt,
                retry_count=retry_count,
                idempotency_key=idempotency_key,
            )
            result.started_at = started_at

            current = self.run_store.get_run_by_id(run_id)
            if current:
                carried_steps = [
                    step
                    for step in current.steps
                    if str(step).strip().lower() == "stop requested by user."
                ]
                if carried_steps:
                    result.steps = [*result.steps, *carried_steps]
            self.run_store.update_run(run_id, result)
        except Exception as error:
            failed_run = RunRecord(
                id=run_id,
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                status="failed",
                started_at=started_at,
                finished_at=self._timestamp(),
                summary=f"Run crashed: {error}",
                steps=[f"Unhandled run error: {error}"],
                replay_of_run_id=replay_of_run_id,
                attempt=attempt,
                retry_count=retry_count,
                idempotency_key=idempotency_key,
            )
            self.run_store.update_run(run_id, failed_run)
        finally:
            with self._lock:
                self._cancel_events.pop(run_id, None)
                self._active_threads.pop(run_id, None)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_run_execution_service_instance: Optional[RunExecutionService] = None


def get_run_execution_service() -> RunExecutionService:
    global _run_execution_service_instance
    if _run_execution_service_instance is None:
        _run_execution_service_instance = RunExecutionService()
    return _run_execution_service_instance
