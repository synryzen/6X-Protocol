from dataclasses import dataclass, asdict, field
from typing import Dict, List


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class RunRecord:
    id: str
    workflow_id: str
    workflow_name: str
    status: str
    started_at: str
    summary: str
    finished_at: str = ""
    steps: List[str] = field(default_factory=list)
    timeline: List[Dict[str, str]] = field(default_factory=list)
    last_failed_node_id: str = ""
    last_failed_node_name: str = ""
    pending_approval_node_id: str = ""
    pending_approval_node_name: str = ""
    replay_of_run_id: str = ""
    attempt: int = 1
    retry_count: int = 0
    idempotency_key: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "RunRecord":
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            steps = []
        timeline = data.get("timeline", [])
        if not isinstance(timeline, list):
            timeline = []

        return RunRecord(
            id=data.get("id", ""),
            workflow_id=data.get("workflow_id", ""),
            workflow_name=data.get("workflow_name", ""),
            status=data.get("status", ""),
            started_at=data.get("started_at", ""),
            summary=data.get("summary", ""),
            finished_at=data.get("finished_at", ""),
            steps=[str(step) for step in steps],
            timeline=[
                {
                    "timestamp": str(item.get("timestamp", "")).strip(),
                    "node_id": str(item.get("node_id", "")).strip(),
                    "node_name": str(item.get("node_name", "")).strip(),
                    "status": str(item.get("status", "")).strip().lower(),
                    "message": str(item.get("message", "")).strip(),
                    "attempt": str(item.get("attempt", "")).strip(),
                    "duration_ms": str(item.get("duration_ms", "")).strip(),
                    "output_preview": str(item.get("output_preview", "")).strip(),
                    "context_snapshot": str(item.get("context_snapshot", "")).strip(),
                }
                for item in timeline
                if isinstance(item, dict)
            ],
            last_failed_node_id=str(data.get("last_failed_node_id", "")).strip(),
            last_failed_node_name=str(data.get("last_failed_node_name", "")).strip(),
            pending_approval_node_id=str(data.get("pending_approval_node_id", "")).strip(),
            pending_approval_node_name=str(data.get("pending_approval_node_name", "")).strip(),
            replay_of_run_id=str(data.get("replay_of_run_id", "")).strip(),
            attempt=_safe_int(data.get("attempt", 1), 1),
            retry_count=_safe_int(data.get("retry_count", 0), 0),
            idempotency_key=str(data.get("idempotency_key", "")).strip(),
        )
