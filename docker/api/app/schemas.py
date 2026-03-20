from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    graph: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)


class WorkflowOut(WorkflowIn):
    id: str
    created_at: str
    updated_at: str


class RunIn(BaseModel):
    workflow_id: str
    status: str = "queued"
    trigger: str = "manual"
    log: str = ""
    node_results: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    workflow_name: str = ""
    finished_at: str = ""
    attempt: int = 1
    retry_count: int = 0
    replay_of_run_id: str = ""
    idempotency_key: str = ""
    cancellation_requested: bool = False
    last_failed_node_id: str = ""
    last_failed_node_name: str = ""
    execution_retry_max: int = 0
    execution_backoff_ms: int = 0
    execution_timeout_sec: float = 0.0


class RunPatch(BaseModel):
    status: str | None = None
    log: str | None = None
    summary: str | None = None
    node_results: list[dict[str, Any]] | None = None
    cancellation_requested: bool | None = None
    last_failed_node_id: str | None = None
    last_failed_node_name: str | None = None


class StartRunRequest(BaseModel):
    workflow_id: str
    trigger: str = "manual"
    start_node_id: str = ""
    idempotency_key: str = ""
    retry_max: int | None = None
    retry_backoff_ms: int | None = None
    timeout_sec: float | None = None


class RetryRunRequest(BaseModel):
    from_failed_node: bool = True


class RunOut(RunIn):
    id: str
    created_at: str
    updated_at: str


class SettingsPatch(BaseModel):
    preferred_provider: str | None = None
    local_ai_enabled: bool | None = None
    local_ai_endpoint: str | None = None
    default_local_model: str | None = None
    theme: str | None = None
    theme_preset: str | None = None
    ui_density: str | None = None
    reduce_motion: bool | None = None


DEFAULT_SETTINGS: dict[str, Any] = {
    "preferred_provider": "local",
    "local_ai_enabled": True,
    "local_ai_endpoint": "http://localhost:11434",
    "default_local_model": "",
    "theme": "dark",
    "theme_preset": "graphite",
    "ui_density": "comfortable",
    "reduce_motion": False,
}

ALLOWED_THEME = {"system", "light", "dark"}
ALLOWED_DENSITY = {"comfortable", "compact"}
ALLOWED_PROVIDER = {"local", "openai", "anthropic"}


def make_workflow(payload: WorkflowIn) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "id": str(uuid4()),
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "graph": payload.graph,
        "status": payload.status,
        "tags": payload.tags,
        "created_at": now,
        "updated_at": now,
    }


def make_run(payload: RunIn) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "id": str(uuid4()),
        "workflow_id": payload.workflow_id,
        "workflow_name": payload.workflow_name,
        "status": payload.status,
        "trigger": payload.trigger,
        "log": payload.log,
        "summary": payload.summary,
        "node_results": payload.node_results,
        "finished_at": payload.finished_at,
        "created_at": now,
        "updated_at": now,
        "attempt": max(1, int(payload.attempt)),
        "retry_count": max(0, int(payload.retry_count)),
        "replay_of_run_id": payload.replay_of_run_id,
        "idempotency_key": payload.idempotency_key,
        "cancellation_requested": bool(payload.cancellation_requested),
        "last_failed_node_id": payload.last_failed_node_id,
        "last_failed_node_name": payload.last_failed_node_name,
        "execution_retry_max": max(0, int(payload.execution_retry_max)),
        "execution_backoff_ms": max(0, int(payload.execution_backoff_ms)),
        "execution_timeout_sec": max(0.0, float(payload.execution_timeout_sec)),
    }


def normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)

    preferred_provider = str(merged.get("preferred_provider", "local")).strip().lower()
    merged["preferred_provider"] = (
        preferred_provider if preferred_provider in ALLOWED_PROVIDER else DEFAULT_SETTINGS["preferred_provider"]
    )

    theme = str(merged.get("theme", "dark")).strip().lower()
    merged["theme"] = theme if theme in ALLOWED_THEME else DEFAULT_SETTINGS["theme"]

    theme_preset = str(merged.get("theme_preset", "graphite")).strip().lower()
    merged["theme_preset"] = theme_preset or DEFAULT_SETTINGS["theme_preset"]

    density = str(merged.get("ui_density", "comfortable")).strip().lower()
    merged["ui_density"] = density if density in ALLOWED_DENSITY else DEFAULT_SETTINGS["ui_density"]

    merged["local_ai_enabled"] = bool(merged.get("local_ai_enabled", True))
    merged["reduce_motion"] = bool(merged.get("reduce_motion", False))
    merged["local_ai_endpoint"] = str(merged.get("local_ai_endpoint", "")).strip() or DEFAULT_SETTINGS["local_ai_endpoint"]
    merged["default_local_model"] = str(merged.get("default_local_model", "")).strip()
    return merged
