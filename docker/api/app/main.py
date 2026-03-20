"""6X-Protocol Web Edition API scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from app.schemas import (
    DEFAULT_SETTINGS,
    RunIn,
    RunOut,
    RunPatch,
    SettingsPatch,
    WorkflowIn,
    WorkflowOut,
    make_run,
    make_workflow,
    normalize_settings,
    utc_now_iso,
)
from app.storage import JsonStore

APP_NAME = "6X-Protocol API"
APP_VERSION = "0.2.0-scaffold"

store = JsonStore()

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Scaffold API for the 6X-Protocol web/self-hosted edition.",
)


def _find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if str(item.get("id", "")) == item_id:
            return item
    return None


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/v1/meta", tags=["meta"])
def meta() -> dict[str, str]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "storage": "json",
        "data_dir": str(store.data_dir),
    }


@app.get("/api/v1/overview", tags=["meta"])
def overview() -> dict[str, int]:
    workflows = store.load_workflows()
    runs = store.load_runs()
    return {
        "workflow_count": len(workflows),
        "run_count": len(runs),
    }


@app.get("/api/v1/workflows", response_model=dict[str, list[WorkflowOut]], tags=["workflows"])
def list_workflows(
    q: str | None = Query(default=None, description="Filter by name/description"),
) -> dict[str, list[dict[str, Any]]]:
    workflows = store.load_workflows()
    if q:
        needle = q.strip().lower()
        workflows = [
            item
            for item in workflows
            if needle in str(item.get("name", "")).lower()
            or needle in str(item.get("description", "")).lower()
        ]
    workflows.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return {"items": workflows}


@app.post("/api/v1/workflows", response_model=WorkflowOut, status_code=201, tags=["workflows"])
def create_workflow(payload: WorkflowIn) -> dict[str, Any]:
    workflows = store.load_workflows()
    item = make_workflow(payload)
    workflows.insert(0, item)
    store.save_workflows(workflows)
    return item


@app.get("/api/v1/workflows/{workflow_id}", response_model=WorkflowOut, tags=["workflows"])
def get_workflow(workflow_id: str) -> dict[str, Any]:
    workflows = store.load_workflows()
    item = _find_by_id(workflows, workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return item


@app.put("/api/v1/workflows/{workflow_id}", response_model=WorkflowOut, tags=["workflows"])
def update_workflow(workflow_id: str, payload: WorkflowIn) -> dict[str, Any]:
    workflows = store.load_workflows()
    for index, item in enumerate(workflows):
        if str(item.get("id", "")) != workflow_id:
            continue
        updated = make_workflow(payload)
        updated["id"] = workflow_id
        updated["created_at"] = item.get("created_at", utc_now_iso())
        updated["updated_at"] = utc_now_iso()
        workflows[index] = updated
        store.save_workflows(workflows)
        return updated
    raise HTTPException(status_code=404, detail="Workflow not found")


@app.patch("/api/v1/workflows/{workflow_id}/graph", response_model=WorkflowOut, tags=["workflows"])
def update_workflow_graph(workflow_id: str, graph: dict[str, Any]) -> dict[str, Any]:
    workflows = store.load_workflows()
    for index, item in enumerate(workflows):
        if str(item.get("id", "")) != workflow_id:
            continue
        item["graph"] = graph
        item["updated_at"] = utc_now_iso()
        workflows[index] = item
        store.save_workflows(workflows)
        return item
    raise HTTPException(status_code=404, detail="Workflow not found")


@app.delete("/api/v1/workflows/{workflow_id}", tags=["workflows"])
def delete_workflow(workflow_id: str) -> dict[str, bool]:
    workflows = store.load_workflows()
    filtered = [item for item in workflows if str(item.get("id", "")) != workflow_id]
    if len(filtered) == len(workflows):
        raise HTTPException(status_code=404, detail="Workflow not found")
    store.save_workflows(filtered)
    return {"deleted": True}


@app.get("/api/v1/runs", response_model=dict[str, list[RunOut]], tags=["runs"])
def list_runs(
    workflow_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> dict[str, list[dict[str, Any]]]:
    runs = store.load_runs()
    if workflow_id:
        runs = [item for item in runs if str(item.get("workflow_id", "")) == workflow_id]
    if status:
        expected = status.strip().lower()
        runs = [item for item in runs if str(item.get("status", "")).lower() == expected]
    runs.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return {"items": runs}


@app.post("/api/v1/runs", response_model=RunOut, status_code=201, tags=["runs"])
def create_run(payload: RunIn) -> dict[str, Any]:
    workflows = store.load_workflows()
    if not _find_by_id(workflows, payload.workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found for run")
    runs = store.load_runs()
    item = make_run(payload)
    runs.insert(0, item)
    store.save_runs(runs)
    return item


@app.get("/api/v1/runs/{run_id}", response_model=RunOut, tags=["runs"])
def get_run(run_id: str) -> dict[str, Any]:
    runs = store.load_runs()
    item = _find_by_id(runs, run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Run not found")
    return item


@app.patch("/api/v1/runs/{run_id}", response_model=RunOut, tags=["runs"])
def patch_run(run_id: str, payload: RunPatch) -> dict[str, Any]:
    runs = store.load_runs()
    for index, item in enumerate(runs):
        if str(item.get("id", "")) != run_id:
            continue
        updates = payload.model_dump(exclude_none=True)
        item.update(updates)
        item["updated_at"] = utc_now_iso()
        runs[index] = item
        store.save_runs(runs)
        return item
    raise HTTPException(status_code=404, detail="Run not found")


@app.delete("/api/v1/runs/{run_id}", tags=["runs"])
def delete_run(run_id: str) -> dict[str, bool]:
    runs = store.load_runs()
    filtered = [item for item in runs if str(item.get("id", "")) != run_id]
    if len(filtered) == len(runs):
        raise HTTPException(status_code=404, detail="Run not found")
    store.save_runs(filtered)
    return {"deleted": True}


@app.get("/api/v1/settings", tags=["settings"])
def get_settings() -> dict[str, Any]:
    settings = store.load_settings(DEFAULT_SETTINGS)
    return normalize_settings(settings)


@app.patch("/api/v1/settings", tags=["settings"])
def patch_settings(payload: SettingsPatch) -> dict[str, Any]:
    current = normalize_settings(store.load_settings(DEFAULT_SETTINGS))
    updates = payload.model_dump(exclude_none=True)
    current.update(updates)
    normalized = normalize_settings(current)
    store.save_settings(normalized)
    return normalized


@app.post("/api/v1/settings/reset", tags=["settings"])
def reset_settings() -> dict[str, Any]:
    settings = normalize_settings(dict(DEFAULT_SETTINGS))
    store.save_settings(settings)
    return settings
