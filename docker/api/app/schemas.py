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


class RunPatch(BaseModel):
    status: str | None = None
    log: str | None = None
    node_results: list[dict[str, Any]] | None = None


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
        "status": payload.status,
        "trigger": payload.trigger,
        "log": payload.log,
        "node_results": payload.node_results,
        "created_at": now,
        "updated_at": now,
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
