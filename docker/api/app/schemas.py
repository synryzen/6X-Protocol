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
    approval_required: bool = False
    pending_approval_node_id: str = ""
    pending_approval_node_name: str = ""
    pending_approval_message: str = ""
    pending_approval_requested_at: str = ""
    pending_approval_resumed_at: str = ""
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
    approval_required: bool | None = None
    pending_approval_node_id: str | None = None
    pending_approval_node_name: str | None = None
    pending_approval_message: str | None = None
    pending_approval_requested_at: str | None = None
    pending_approval_resumed_at: str | None = None
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
    local_ai_backend: str | None = None
    local_ai_endpoint: str | None = None
    local_ai_api_key: str | None = None
    default_local_model: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    theme: str | None = None
    theme_preset: str | None = None
    ui_density: str | None = None
    reduce_motion: bool | None = None
    auto_save_workflows: bool | None = None
    daemon_autostart: bool | None = None
    tray_enabled: bool | None = None
    canvas_minimap_x: int | None = None
    canvas_minimap_y: int | None = None
    canvas_minimap_user_placed: bool | None = None


class IntegrationProfileIn(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class IntegrationProfilePatch(BaseModel):
    key: str | None = None
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


class IntegrationProfileOut(IntegrationProfileIn):
    id: str
    last_test_status: str = ""
    last_test_message: str = ""
    last_tested_at: str = ""
    created_at: str
    updated_at: str


class IntegrationTestRequest(BaseModel):
    integration_key: str = ""
    profile_id: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    input_context: str = "integration test ping"
    timeout_sec: float = 8.0


class IntegrationTestResult(BaseModel):
    ok: bool
    integration_key: str
    profile_id: str = ""
    message: str
    output: str = ""
    tested_at: str


class IntegrationProfileImportRequest(BaseModel):
    source_path: str = ""
    merge: bool = True


class IntegrationProfileImportResult(BaseModel):
    imported_count: int
    total_count: int
    source_path: str
    merge: bool


class IntegrationProfileExportResult(BaseModel):
    path: str
    count: int
    exported_at: str


class BackupRestoreRequest(BaseModel):
    source_path: str = ""
    merge: bool = False


class BackupExportResult(BaseModel):
    path: str
    counts: dict[str, int] = Field(default_factory=dict)
    exported_at: str


class BackupRestoreResult(BaseModel):
    restored_counts: dict[str, int] = Field(default_factory=dict)
    source_path: str
    merge: bool
    restored_at: str


class SecretRotateRequest(BaseModel):
    new_key_material: str = Field(min_length=1)


class SecretRotateResult(BaseModel):
    rotated_counts: dict[str, int] = Field(default_factory=dict)
    rotated_at: str


class BotProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = ""
    provider: str = "local"
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str = ""
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class BotProfilePatch(BaseModel):
    name: str | None = None
    role: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


class BotProfileOut(BotProfileIn):
    id: str
    last_test_status: str = ""
    last_test_message: str = ""
    last_test_output: str = ""
    last_tested_at: str = ""
    created_at: str
    updated_at: str


class BotTestRequest(BaseModel):
    bot_id: str = ""
    prompt: str = "Respond with a concise confirmation."
    provider: str = ""
    model: str = ""
    role: str = ""
    system_prompt: str = ""
    temperature: float | None = None
    max_tokens: int | None = None


class BotTestResult(BaseModel):
    ok: bool
    bot_id: str = ""
    provider: str = ""
    model: str = ""
    message: str
    output: str = ""
    tested_at: str


DEFAULT_SETTINGS: dict[str, Any] = {
    "preferred_provider": "local",
    "local_ai_enabled": True,
    "local_ai_backend": "ollama",
    "local_ai_endpoint": "http://localhost:11434",
    "local_ai_api_key": "",
    "default_local_model": "",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "theme": "dark",
    "theme_preset": "graphite",
    "ui_density": "comfortable",
    "reduce_motion": False,
    "auto_save_workflows": True,
    "daemon_autostart": False,
    "tray_enabled": False,
    "canvas_minimap_x": 0,
    "canvas_minimap_y": 0,
    "canvas_minimap_user_placed": False,
}

ALLOWED_THEME = {"system", "light", "dark"}
ALLOWED_DENSITY = {"comfortable", "compact"}
ALLOWED_PROVIDER = {"local", "openai", "anthropic"}
ALLOWED_THEME_PRESETS = {
    "graphite",
    "indigo",
    "carbon",
    "aurora",
    "frost",
    "sunset",
    "rose",
    "amber",
}
ALLOWED_LOCAL_BACKENDS = {
    "ollama",
    "lm_studio",
    "openai_compatible",
    "vllm",
    "llama_cpp",
    "text_generation_webui",
    "jan",
}


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
        "approval_required": bool(payload.approval_required),
        "pending_approval_node_id": payload.pending_approval_node_id,
        "pending_approval_node_name": payload.pending_approval_node_name,
        "pending_approval_message": payload.pending_approval_message,
        "pending_approval_requested_at": payload.pending_approval_requested_at,
        "pending_approval_resumed_at": payload.pending_approval_resumed_at,
        "last_failed_node_id": payload.last_failed_node_id,
        "last_failed_node_name": payload.last_failed_node_name,
        "execution_retry_max": max(0, int(payload.execution_retry_max)),
        "execution_backoff_ms": max(0, int(payload.execution_backoff_ms)),
        "execution_timeout_sec": max(0.0, float(payload.execution_timeout_sec)),
    }


def make_integration_profile(payload: IntegrationProfileIn) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "id": str(uuid4()),
        "key": payload.key.strip().lower(),
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "config": payload.config if isinstance(payload.config, dict) else {},
        "enabled": bool(payload.enabled),
        "tags": payload.tags if isinstance(payload.tags, list) else [],
        "last_test_status": "",
        "last_test_message": "",
        "last_tested_at": "",
        "created_at": now,
        "updated_at": now,
    }


def make_bot_profile(payload: BotProfileIn) -> dict[str, Any]:
    now = utc_now_iso()
    provider = str(payload.provider or "local").strip().lower() or "local"
    if provider not in ALLOWED_PROVIDER:
        provider = "local"
    temperature = payload.temperature if payload.temperature is not None else None
    if temperature is not None:
        temperature = max(0.0, min(2.0, float(temperature)))
    max_tokens = payload.max_tokens if payload.max_tokens is not None else None
    if max_tokens is not None:
        max_tokens = max(1, int(max_tokens))
    return {
        "id": str(uuid4()),
        "name": payload.name.strip(),
        "role": payload.role.strip(),
        "provider": provider,
        "model": payload.model.strip(),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": payload.system_prompt.strip(),
        "enabled": bool(payload.enabled),
        "tags": payload.tags if isinstance(payload.tags, list) else [],
        "last_test_status": "",
        "last_test_message": "",
        "last_test_output": "",
        "last_tested_at": "",
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
    merged["theme_preset"] = (
        theme_preset
        if theme_preset in ALLOWED_THEME_PRESETS
        else DEFAULT_SETTINGS["theme_preset"]
    )

    density = str(merged.get("ui_density", "comfortable")).strip().lower()
    merged["ui_density"] = density if density in ALLOWED_DENSITY else DEFAULT_SETTINGS["ui_density"]

    merged["local_ai_enabled"] = coerce_bool(merged.get("local_ai_enabled", True), True)
    merged["reduce_motion"] = coerce_bool(merged.get("reduce_motion", False), False)
    merged["auto_save_workflows"] = coerce_bool(
        merged.get("auto_save_workflows", DEFAULT_SETTINGS["auto_save_workflows"])
    )
    merged["daemon_autostart"] = coerce_bool(
        merged.get("daemon_autostart", DEFAULT_SETTINGS["daemon_autostart"])
    )
    merged["tray_enabled"] = coerce_bool(
        merged.get("tray_enabled", DEFAULT_SETTINGS["tray_enabled"])
    )
    try:
        minimap_x = int(merged.get("canvas_minimap_x", DEFAULT_SETTINGS["canvas_minimap_x"]))
    except (TypeError, ValueError):
        minimap_x = int(DEFAULT_SETTINGS["canvas_minimap_x"])
    try:
        minimap_y = int(merged.get("canvas_minimap_y", DEFAULT_SETTINGS["canvas_minimap_y"]))
    except (TypeError, ValueError):
        minimap_y = int(DEFAULT_SETTINGS["canvas_minimap_y"])
    merged["canvas_minimap_x"] = max(0, minimap_x)
    merged["canvas_minimap_y"] = max(0, minimap_y)
    merged["canvas_minimap_user_placed"] = coerce_bool(
        merged.get(
            "canvas_minimap_user_placed",
            DEFAULT_SETTINGS["canvas_minimap_user_placed"],
        )
    )
    local_backend = str(merged.get("local_ai_backend", "ollama")).strip().lower()
    merged["local_ai_backend"] = local_backend if local_backend in ALLOWED_LOCAL_BACKENDS else "ollama"
    local_endpoint = str(merged.get("local_ai_endpoint", "")).strip()
    if not local_endpoint:
        local_endpoint = default_endpoint_for_backend(merged["local_ai_backend"])
    merged["local_ai_endpoint"] = local_endpoint.rstrip("/")
    merged["local_ai_api_key"] = str(merged.get("local_ai_api_key", "")).strip()
    merged["default_local_model"] = sanitize_model_name(str(merged.get("default_local_model", "")).strip())
    merged["openai_api_key"] = str(merged.get("openai_api_key", "")).strip()
    merged["anthropic_api_key"] = str(merged.get("anthropic_api_key", "")).strip()
    return merged


def default_endpoint_for_backend(backend: str) -> str:
    normalized = str(backend).strip().lower()
    if normalized == "lm_studio":
        return "http://localhost:1234/v1"
    if normalized in {"openai_compatible", "vllm"}:
        return "http://localhost:8000/v1"
    if normalized == "llama_cpp":
        return "http://localhost:8080/v1"
    if normalized == "text_generation_webui":
        return "http://localhost:5000/v1"
    if normalized == "jan":
        return "http://localhost:1337/v1"
    return "http://localhost:11434"


def sanitize_model_name(model: str) -> str:
    value = str(model).strip().strip("/")
    if not value:
        return ""
    lowered = value.lower()
    for suffix in ("v1/chat/completions", "chat/completions", "v1/completions", "completions"):
        if lowered.endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")
            break
    return value


def coerce_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(fallback)
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off", ""}:
        return False
    return bool(fallback)
