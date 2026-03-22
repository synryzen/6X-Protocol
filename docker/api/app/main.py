"""6X-Protocol Web Edition API scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.run_controller import ACTIVE_STATUSES, RunController
from app.schemas import (
    ALLOWED_PROVIDER,
    BotProfileIn,
    BotProfileOut,
    BotProfilePatch,
    BotTestRequest,
    BotTestResult,
    DEFAULT_SETTINGS,
    IntegrationProfileIn,
    IntegrationProfileOut,
    IntegrationProfilePatch,
    IntegrationTestRequest,
    IntegrationTestResult,
    RunIn,
    RunOut,
    RunPatch,
    RetryRunRequest,
    SettingsPatch,
    StartRunRequest,
    WorkflowIn,
    WorkflowOut,
    make_bot_profile,
    make_integration_profile,
    make_run,
    make_workflow,
    normalize_settings,
    utc_now_iso,
)
from app.storage import JsonStore

APP_NAME = "6X-Protocol API"
APP_VERSION = "0.5.0-preview"

INTEGRATION_CATALOG: list[dict[str, Any]] = [
    {"key": "standard", "name": "Standard Action", "category": "core", "required_fields": []},
    {"key": "http_request", "name": "HTTP Request", "category": "core", "required_fields": ["url"]},
    {"key": "http_post", "name": "HTTP POST", "category": "core", "required_fields": ["url"]},
    {"key": "slack_webhook", "name": "Slack Webhook", "category": "communication", "required_fields": ["webhook_url"]},
    {"key": "discord_webhook", "name": "Discord Webhook", "category": "communication", "required_fields": ["webhook_url"]},
    {"key": "teams_webhook", "name": "Microsoft Teams Webhook", "category": "communication", "required_fields": ["webhook_url"]},
    {"key": "telegram_bot", "name": "Telegram Bot", "category": "communication", "required_fields": ["api_key", "chat_id"]},
    {"key": "gmail_send", "name": "Gmail Send", "category": "communication", "required_fields": ["api_key", "to", "subject"]},
    {"key": "outlook_graph", "name": "Outlook Graph", "category": "communication", "required_fields": ["api_key", "url"]},
    {"key": "twilio_sms", "name": "Twilio SMS", "category": "communication", "required_fields": ["account_sid", "auth_token", "to", "from"]},
    {"key": "openweather_current", "name": "OpenWeather Current", "category": "data", "required_fields": ["api_key", "location"]},
    {"key": "google_apps_script", "name": "Google Apps Script", "category": "google", "required_fields": ["script_url"]},
    {"key": "google_sheets", "name": "Google Sheets", "category": "google", "required_fields": ["api_key", "spreadsheet_id", "range"]},
    {"key": "notion_api", "name": "Notion API", "category": "productivity", "required_fields": ["api_key", "url"]},
    {"key": "airtable_api", "name": "Airtable API", "category": "productivity", "required_fields": ["api_key", "url"]},
    {"key": "github_rest", "name": "GitHub REST", "category": "developer", "required_fields": ["api_key", "url"]},
    {"key": "gitlab_api", "name": "GitLab API", "category": "developer", "required_fields": ["api_key", "url"]},
    {"key": "jira_api", "name": "Jira API", "category": "project", "required_fields": ["api_key", "url"]},
    {"key": "asana_api", "name": "Asana API", "category": "project", "required_fields": ["api_key", "url"]},
    {"key": "clickup_api", "name": "ClickUp API", "category": "project", "required_fields": ["api_key", "url"]},
    {"key": "trello_api", "name": "Trello API", "category": "project", "required_fields": ["api_key", "url"]},
    {"key": "monday_api", "name": "Monday API", "category": "project", "required_fields": ["api_key", "url"]},
    {"key": "zendesk_api", "name": "Zendesk API", "category": "crm", "required_fields": ["api_key", "url"]},
    {"key": "salesforce_api", "name": "Salesforce API", "category": "crm", "required_fields": ["api_key", "url"]},
    {"key": "pipedrive_api", "name": "Pipedrive API", "category": "crm", "required_fields": ["api_key", "url"]},
    {"key": "hubspot_api", "name": "HubSpot API", "category": "crm", "required_fields": ["api_key", "url"]},
    {"key": "stripe_api", "name": "Stripe API", "category": "payments", "required_fields": ["api_key", "url"]},
    {"key": "file_append", "name": "File Append", "category": "system", "required_fields": ["path", "message"]},
    {"key": "sqlite_sql", "name": "SQLite SQL", "category": "database", "required_fields": ["path", "sql"]},
    {"key": "postgres_sql", "name": "Postgres SQL", "category": "database", "required_fields": ["connection_url", "sql"]},
    {"key": "mysql_sql", "name": "MySQL SQL", "category": "database", "required_fields": ["connection_url", "sql"]},
    {"key": "redis_command", "name": "Redis Command", "category": "database", "required_fields": ["command"]},
    {"key": "shell_command", "name": "Shell Command", "category": "system", "required_fields": ["command"]},
    {"key": "s3_cli", "name": "S3 CLI", "category": "system", "required_fields": ["command"]},
    {"key": "approval_gate", "name": "Approval Gate", "category": "workflow", "required_fields": ["message"]},
]

store = JsonStore()
run_controller = RunController(store=store)

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Scaffold API for the 6X-Protocol web/self-hosted edition.",
)


def _cors_allow_origins() -> list[str]:
    raw = str(
        os.getenv(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        )
    ).strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    if raw == "*":
        return ["*"]
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if str(item.get("id", "")) == item_id:
            return item
    return None


def _find_workflow(workflow_id: str) -> dict[str, Any] | None:
    workflows = store.load_workflows()
    return _find_by_id(workflows, workflow_id)


def _find_integration_profile(profile_id: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    profiles = store.load_integrations()
    return profiles, _find_by_id(profiles, profile_id)


def _find_bot_profile(bot_id: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    bots = store.load_bots()
    return bots, _find_by_id(bots, bot_id)


def _sanitize_profile_config(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _normalize_bot_temperature(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(2.0, float(value)))
    except (TypeError, ValueError):
        return None


def _normalize_bot_max_tokens(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def _normalize_bot_provider(value: Any) -> str:
    provider = str(value or "local").strip().lower() or "local"
    return provider if provider in ALLOWED_PROVIDER else "local"


def _simulate_bot_response(
    *,
    role: str,
    provider: str,
    model: str,
    prompt: str,
    system_prompt: str,
    temperature: float | None,
    max_tokens: int | None,
) -> tuple[str, str]:
    role_text = role.strip() or "automation assistant"
    prompt_text = prompt.strip() or "Respond with a concise confirmation."
    system_text = system_prompt.strip()
    model_text = model.strip() or "default"
    temp_text = f"{temperature:.2f}" if temperature is not None else "inherit"
    token_text = str(max_tokens) if max_tokens is not None else "inherit"
    header = f"[{provider}:{model_text}] role={role_text} temp={temp_text} max_tokens={token_text}"
    if system_text:
        summary = f"{header}\nSystem: {system_text[:220]}"
    else:
        summary = header
    output = f"{summary}\nPrompt: {prompt_text[:420]}\nResult: Bot test simulation completed successfully."
    message = f"Bot test completed using provider '{provider}' and model '{model_text}'."
    return message, output


def _run_timeline_events(run: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = run.get("timeline")
    if isinstance(timeline, list):
        return [item for item in timeline if isinstance(item, dict)]
    node_results = run.get("node_results")
    if isinstance(node_results, list):
        return [item for item in node_results if isinstance(item, dict)]
    return []


def _filter_timeline_events(
    events: list[dict[str, Any]],
    *,
    status: str = "",
    node_id: str = "",
    q: str = "",
) -> list[dict[str, Any]]:
    normalized_status = status.strip().lower()
    normalized_node = node_id.strip().lower()
    needle = q.strip().lower()
    filtered = events
    if normalized_status:
        filtered = [
            item for item in filtered if str(item.get("status", "")).strip().lower() == normalized_status
        ]
    if normalized_node:
        filtered = [
            item
            for item in filtered
            if normalized_node
            in (
                f"{str(item.get('node_id', '')).strip().lower()} "
                f"{str(item.get('node_name', '')).strip().lower()}"
            )
        ]
    if needle:
        filtered = [
            item
            for item in filtered
            if needle
            in (
                " ".join(
                    [
                        str(item.get("node_id", "")),
                        str(item.get("node_name", "")),
                        str(item.get("status", "")),
                        str(item.get("message", "")),
                        str(item.get("timestamp", "")),
                        str(item.get("output_preview", "")),
                    ]
                ).lower()
            )
        ]
    return filtered


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
    integrations = store.load_integrations()
    bots = store.load_bots()
    return {
        "workflow_count": len(workflows),
        "run_count": len(runs),
        "integration_count": len(integrations),
        "bot_count": len(bots),
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
    q: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    runs = store.load_runs()
    if workflow_id:
        runs = [item for item in runs if str(item.get("workflow_id", "")) == workflow_id]
    if status:
        expected = status.strip().lower()
        runs = [item for item in runs if str(item.get("status", "")).lower() == expected]
    if q:
        needle = q.strip().lower()
        if needle:
            runs = [
                item
                for item in runs
                if needle
                in (
                    " ".join(
                        [
                            str(item.get("id", "")),
                            str(item.get("workflow_id", "")),
                            str(item.get("workflow_name", "")),
                            str(item.get("status", "")),
                            str(item.get("summary", "")),
                            str(item.get("trigger", "")),
                            str(item.get("last_failed_node_id", "")),
                            str(item.get("last_failed_node_name", "")),
                            str(item.get("log", "")),
                        ]
                    ).lower()
                )
            ]
    runs.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    if isinstance(limit, int):
        runs = runs[: max(1, min(500, int(limit)))]
    return {"items": runs}


@app.post("/api/v1/runs", response_model=RunOut, status_code=201, tags=["runs"])
def create_run(payload: RunIn) -> dict[str, Any]:
    workflow = _find_workflow(payload.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found for run")
    runs = store.load_runs()
    item = make_run(payload)
    if not item.get("workflow_name"):
        item["workflow_name"] = str(workflow.get("name", ""))
    if not item.get("summary"):
        item["summary"] = "Run created."
    runs.insert(0, item)
    store.save_runs(runs)
    return item


@app.post("/api/v1/runs/start", response_model=RunOut, status_code=201, tags=["runs"])
def start_run(payload: StartRunRequest) -> dict[str, Any]:
    workflow = _find_workflow(payload.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found for run")
    return run_controller.start(
        workflow,
        trigger=payload.trigger,
        start_node_id=payload.start_node_id,
        idempotency_key=payload.idempotency_key,
        retry_max=payload.retry_max,
        retry_backoff_ms=payload.retry_backoff_ms,
        timeout_sec=payload.timeout_sec,
    )


@app.get("/api/v1/runs/{run_id}", response_model=RunOut, tags=["runs"])
def get_run(run_id: str) -> dict[str, Any]:
    runs = store.load_runs()
    item = _find_by_id(runs, run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Run not found")
    return item


@app.get("/api/v1/runs/{run_id}/timeline", tags=["runs"])
def get_run_timeline(
    run_id: str,
    status: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="desc"),
) -> dict[str, Any]:
    runs = store.load_runs()
    run = _find_by_id(runs, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    events = _run_timeline_events(run)
    events = _filter_timeline_events(
        events,
        status=str(status or ""),
        node_id=str(node_id or ""),
        q=str(q or ""),
    )

    total = len(events)
    normalized_order = str(order or "desc").strip().lower()
    if normalized_order == "desc":
        events = list(reversed(events))
    else:
        normalized_order = "asc"

    start = max(0, int(offset))
    end = start + max(1, min(1000, int(limit)))
    items = events[start:end]
    return {
        "run_id": run_id,
        "order": normalized_order,
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "items": items,
    }


@app.get("/api/v1/runs/{run_id}/logs", tags=["runs"])
def get_run_logs(
    run_id: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="desc"),
) -> dict[str, Any]:
    runs = store.load_runs()
    run = _find_by_id(runs, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    lines = str(run.get("log", "")).splitlines()
    normalized_q = str(q or "").strip().lower()
    indexed: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        if normalized_q and normalized_q not in line.lower():
            continue
        indexed.append({"line_no": idx, "line": line})

    total = len(indexed)
    normalized_order = str(order or "desc").strip().lower()
    if normalized_order == "desc":
        indexed = list(reversed(indexed))
    else:
        normalized_order = "asc"

    start = max(0, int(offset))
    end = start + max(1, min(2000, int(limit)))
    items = indexed[start:end]
    return {
        "run_id": run_id,
        "order": normalized_order,
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "items": items,
    }


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


@app.post("/api/v1/runs/{run_id}/cancel", response_model=RunOut, tags=["runs"])
def cancel_run(run_id: str) -> dict[str, Any]:
    success, message, run = run_controller.cancel(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not success:
        raise HTTPException(status_code=409, detail=message)
    return run


@app.post("/api/v1/runs/{run_id}/retry", response_model=RunOut, status_code=201, tags=["runs"])
def retry_run(run_id: str, payload: RetryRunRequest) -> dict[str, Any]:
    previous = run_controller.get_run(run_id)
    if not previous:
        raise HTTPException(status_code=404, detail="Run not found")

    previous_status = str(previous.get("status", "")).strip().lower()
    if previous_status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Active runs cannot be retried.")

    workflow_id = str(previous.get("workflow_id", "")).strip()
    workflow = _find_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found for retry")

    start_node_id = ""
    if payload.from_failed_node:
        start_node_id = str(previous.get("last_failed_node_id", "")).strip()
        if previous_status != "failed":
            raise HTTPException(
                status_code=409,
                detail="Retry from failed node requires a failed run.",
            )
        if not start_node_id:
            raise HTTPException(
                status_code=409,
                detail="No failed node was recorded for this run.",
            )

    try:
        previous_attempt = int(previous.get("attempt", 1))
    except (TypeError, ValueError):
        previous_attempt = 1
    try:
        previous_retry_count = int(previous.get("retry_count", 0))
    except (TypeError, ValueError):
        previous_retry_count = 0
    try:
        previous_exec_retry_max = int(previous.get("execution_retry_max", 0))
    except (TypeError, ValueError):
        previous_exec_retry_max = 0
    try:
        previous_exec_backoff_ms = int(previous.get("execution_backoff_ms", 0))
    except (TypeError, ValueError):
        previous_exec_backoff_ms = 0
    try:
        previous_exec_timeout_sec = float(previous.get("execution_timeout_sec", 0.0))
    except (TypeError, ValueError):
        previous_exec_timeout_sec = 0.0

    return run_controller.start(
        workflow,
        trigger="retry",
        start_node_id=start_node_id,
        replay_of_run_id=run_id,
        attempt=max(1, previous_attempt + 1),
        retry_count=max(0, previous_retry_count + 1),
        retry_max=max(0, previous_exec_retry_max),
        retry_backoff_ms=max(0, previous_exec_backoff_ms),
        timeout_sec=max(0.0, previous_exec_timeout_sec),
    )


@app.delete("/api/v1/runs/{run_id}", tags=["runs"])
def delete_run(run_id: str) -> dict[str, bool]:
    runs = store.load_runs()
    filtered = [item for item in runs if str(item.get("id", "")) != run_id]
    if len(filtered) == len(runs):
        raise HTTPException(status_code=404, detail="Run not found")
    store.save_runs(filtered)
    return {"deleted": True}


@app.get(
    "/api/v1/bots",
    response_model=dict[str, list[BotProfileOut]],
    tags=["bots"],
)
def list_bots(
    q: str | None = Query(default=None, description="Filter by name/role/provider/model"),
    provider: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
) -> dict[str, list[dict[str, Any]]]:
    bots = store.load_bots()
    if q:
        needle = q.strip().lower()
        if needle:
            bots = [
                item
                for item in bots
                if needle
                in (
                    " ".join(
                        [
                            str(item.get("name", "")),
                            str(item.get("role", "")),
                            str(item.get("provider", "")),
                            str(item.get("model", "")),
                            str(item.get("system_prompt", "")),
                        ]
                    ).lower()
                )
            ]
    if provider:
        normalized_provider = _normalize_bot_provider(provider)
        bots = [item for item in bots if _normalize_bot_provider(item.get("provider")) == normalized_provider]
    if enabled is not None:
        bots = [item for item in bots if bool(item.get("enabled", True)) == bool(enabled)]
    bots.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return {"items": bots}


@app.post(
    "/api/v1/bots",
    response_model=BotProfileOut,
    status_code=201,
    tags=["bots"],
)
def create_bot(payload: BotProfileIn) -> dict[str, Any]:
    bots = store.load_bots()
    item = make_bot_profile(payload)
    bots.insert(0, item)
    store.save_bots(bots)
    return item


@app.get(
    "/api/v1/bots/{bot_id}",
    response_model=BotProfileOut,
    tags=["bots"],
)
def get_bot(bot_id: str) -> dict[str, Any]:
    bots = store.load_bots()
    item = _find_by_id(bots, bot_id)
    if not item:
        raise HTTPException(status_code=404, detail="Bot not found")
    return item


@app.patch(
    "/api/v1/bots/{bot_id}",
    response_model=BotProfileOut,
    tags=["bots"],
)
def patch_bot(bot_id: str, payload: BotProfilePatch) -> dict[str, Any]:
    bots = store.load_bots()
    for index, item in enumerate(bots):
        if str(item.get("id", "")) != bot_id:
            continue
        updates = payload.model_dump(exclude_none=True)
        if "name" in updates:
            updates["name"] = str(updates["name"]).strip()
        if "role" in updates:
            updates["role"] = str(updates["role"]).strip()
        if "provider" in updates:
            updates["provider"] = _normalize_bot_provider(updates["provider"])
        if "model" in updates:
            updates["model"] = str(updates["model"]).strip()
        if "system_prompt" in updates:
            updates["system_prompt"] = str(updates["system_prompt"]).strip()
        if "temperature" in updates:
            updates["temperature"] = _normalize_bot_temperature(updates.get("temperature"))
        if "max_tokens" in updates:
            updates["max_tokens"] = _normalize_bot_max_tokens(updates.get("max_tokens"))
        if "enabled" in updates:
            updates["enabled"] = bool(updates["enabled"])
        if "tags" in updates and not isinstance(updates.get("tags"), list):
            updates["tags"] = []
        item.update(updates)
        item["updated_at"] = utc_now_iso()
        bots[index] = item
        store.save_bots(bots)
        return item
    raise HTTPException(status_code=404, detail="Bot not found")


@app.delete("/api/v1/bots/{bot_id}", tags=["bots"])
def delete_bot(bot_id: str) -> dict[str, bool]:
    bots = store.load_bots()
    filtered = [item for item in bots if str(item.get("id", "")) != bot_id]
    if len(filtered) == len(bots):
        raise HTTPException(status_code=404, detail="Bot not found")
    store.save_bots(filtered)
    return {"deleted": True}


@app.post(
    "/api/v1/bots/test",
    response_model=BotTestResult,
    tags=["bots"],
)
def test_bot(payload: BotTestRequest) -> dict[str, Any]:
    bot_id = str(payload.bot_id or "").strip()
    prompt = str(payload.prompt or "").strip() or "Respond with a concise confirmation."
    role = str(payload.role or "").strip()
    provider = _normalize_bot_provider(payload.provider)
    model = str(payload.model or "").strip()
    system_prompt = str(payload.system_prompt or "").strip()
    temperature = _normalize_bot_temperature(payload.temperature)
    max_tokens = _normalize_bot_max_tokens(payload.max_tokens)

    bots: list[dict[str, Any]] = []
    bot: dict[str, Any] | None = None
    if bot_id:
        bots, bot = _find_bot_profile(bot_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        role = role or str(bot.get("role", "")).strip()
        provider = _normalize_bot_provider(provider or bot.get("provider"))
        model = model or str(bot.get("model", "")).strip()
        system_prompt = system_prompt or str(bot.get("system_prompt", "")).strip()
        if temperature is None:
            temperature = _normalize_bot_temperature(bot.get("temperature"))
        if max_tokens is None:
            max_tokens = _normalize_bot_max_tokens(bot.get("max_tokens"))

    if not model:
        settings = normalize_settings(store.load_settings(DEFAULT_SETTINGS))
        model = str(settings.get("default_local_model", "")).strip() or "default"
    if not role:
        role = "automation assistant"

    tested_at = utc_now_iso()
    message, output = _simulate_bot_response(
        role=role,
        provider=provider,
        model=model,
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if bot and bots:
        for index, item in enumerate(bots):
            if str(item.get("id", "")) != str(bot.get("id", "")):
                continue
            item["last_test_status"] = "success"
            item["last_test_message"] = message
            item["last_test_output"] = output
            item["last_tested_at"] = tested_at
            item["updated_at"] = tested_at
            bots[index] = item
            store.save_bots(bots)
            break

    return {
        "ok": True,
        "bot_id": bot_id,
        "provider": provider,
        "model": model,
        "message": message,
        "output": output,
        "tested_at": tested_at,
    }


@app.get("/api/v1/integrations/catalog", tags=["integrations"])
def integration_catalog(
    q: str | None = Query(default=None, description="Filter by key/name/category"),
) -> dict[str, list[dict[str, Any]]]:
    items = list(INTEGRATION_CATALOG)
    if q:
        needle = q.strip().lower()
        if needle:
            items = [
                item
                for item in items
                if needle in str(item.get("key", "")).lower()
                or needle in str(item.get("name", "")).lower()
                or needle in str(item.get("category", "")).lower()
            ]
    items.sort(key=lambda item: str(item.get("name", "")).lower())
    return {"items": items}


@app.get(
    "/api/v1/integrations",
    response_model=dict[str, list[IntegrationProfileOut]],
    tags=["integrations"],
)
def list_integrations(
    q: str | None = Query(default=None, description="Filter by profile name/key/description"),
    enabled: bool | None = Query(default=None),
) -> dict[str, list[dict[str, Any]]]:
    profiles = store.load_integrations()
    if q:
        needle = q.strip().lower()
        if needle:
            profiles = [
                item
                for item in profiles
                if needle in str(item.get("name", "")).lower()
                or needle in str(item.get("key", "")).lower()
                or needle in str(item.get("description", "")).lower()
            ]
    if enabled is not None:
        profiles = [item for item in profiles if bool(item.get("enabled", True)) == bool(enabled)]
    profiles.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return {"items": profiles}


@app.post(
    "/api/v1/integrations",
    response_model=IntegrationProfileOut,
    status_code=201,
    tags=["integrations"],
)
def create_integration_profile(payload: IntegrationProfileIn) -> dict[str, Any]:
    profiles = store.load_integrations()
    item = make_integration_profile(payload)
    item["config"] = _sanitize_profile_config(item.get("config", {}))
    profiles.insert(0, item)
    store.save_integrations(profiles)
    return item


@app.get(
    "/api/v1/integrations/{profile_id}",
    response_model=IntegrationProfileOut,
    tags=["integrations"],
)
def get_integration_profile(profile_id: str) -> dict[str, Any]:
    profiles = store.load_integrations()
    item = _find_by_id(profiles, profile_id)
    if not item:
        raise HTTPException(status_code=404, detail="Integration profile not found")
    return item


@app.patch(
    "/api/v1/integrations/{profile_id}",
    response_model=IntegrationProfileOut,
    tags=["integrations"],
)
def patch_integration_profile(profile_id: str, payload: IntegrationProfilePatch) -> dict[str, Any]:
    profiles = store.load_integrations()
    for index, item in enumerate(profiles):
        if str(item.get("id", "")) != profile_id:
            continue
        updates = payload.model_dump(exclude_none=True)
        if "key" in updates:
            updates["key"] = str(updates["key"]).strip().lower()
        if "name" in updates:
            updates["name"] = str(updates["name"]).strip()
        if "description" in updates:
            updates["description"] = str(updates["description"]).strip()
        if "config" in updates:
            updates["config"] = _sanitize_profile_config(updates.get("config"))
        if "tags" in updates and not isinstance(updates.get("tags"), list):
            updates["tags"] = []
        item.update(updates)
        item["updated_at"] = utc_now_iso()
        profiles[index] = item
        store.save_integrations(profiles)
        return item
    raise HTTPException(status_code=404, detail="Integration profile not found")


@app.delete("/api/v1/integrations/{profile_id}", tags=["integrations"])
def delete_integration_profile(profile_id: str) -> dict[str, bool]:
    profiles = store.load_integrations()
    filtered = [item for item in profiles if str(item.get("id", "")) != profile_id]
    if len(filtered) == len(profiles):
        raise HTTPException(status_code=404, detail="Integration profile not found")
    store.save_integrations(filtered)
    return {"deleted": True}


@app.post(
    "/api/v1/integrations/test",
    response_model=IntegrationTestResult,
    tags=["integrations"],
)
def test_integration(payload: IntegrationTestRequest) -> dict[str, Any]:
    profile_id = str(payload.profile_id).strip()
    integration_key = str(payload.integration_key).strip().lower()
    merged_config: dict[str, Any] = _sanitize_profile_config(payload.config)
    profile: dict[str, Any] | None = None
    profiles: list[dict[str, Any]] = []

    if profile_id:
        profiles, profile = _find_integration_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Integration profile not found")
        profile_config = _sanitize_profile_config(profile.get("config", {}))
        profile_config.update(merged_config)
        merged_config = profile_config
        if not integration_key:
            integration_key = str(profile.get("key", "")).strip().lower()

    if not integration_key:
        raise HTTPException(status_code=400, detail="integration_key or profile_id is required")

    tested_at = utc_now_iso()
    input_context = str(payload.input_context or "").strip() or "integration test ping"
    timeout_sec = max(0.1, min(120.0, float(payload.timeout_sec or 8.0)))
    context = {"last_output": input_context}
    try:
        message, output = run_controller._execute_action_integration(
            integration=integration_key,
            config=merged_config,
            context=context,
            timeout_sec=timeout_sec,
        )
        ok = True
    except Exception as error:
        message = f"Integration test failed: {error}"
        output = ""
        ok = False

    if profile and profiles:
        for index, item in enumerate(profiles):
            if str(item.get("id", "")) != str(profile.get("id", "")):
                continue
            item["last_test_status"] = "success" if ok else "failed"
            item["last_test_message"] = str(message).strip()
            item["last_tested_at"] = tested_at
            item["updated_at"] = tested_at
            profiles[index] = item
            store.save_integrations(profiles)
            break

    return {
        "ok": ok,
        "integration_key": integration_key,
        "profile_id": profile_id,
        "message": str(message).strip(),
        "output": str(output).strip(),
        "tested_at": tested_at,
    }


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
