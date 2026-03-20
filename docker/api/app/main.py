"""6X-Protocol Web Edition API scaffold.

This module provides a small but real FastAPI service that can be expanded into
workflow CRUD, run orchestration, and settings APIs for the web edition.
"""

from datetime import UTC, datetime

from fastapi import FastAPI

APP_NAME = "6X-Protocol API"
APP_VERSION = "0.1.0-scaffold"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Scaffold API for the 6X-Protocol web/self-hosted edition.",
)


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
    }


@app.get("/api/v1/workflows", tags=["workflows"])
def list_workflows() -> dict[str, list[dict[str, str]]]:
    # Scaffold response shape for future runtime extraction.
    return {"items": []}


@app.get("/api/v1/runs", tags=["runs"])
def list_runs() -> dict[str, list[dict[str, str]]]:
    # Scaffold response shape for future run timeline APIs.
    return {"items": []}


@app.get("/api/v1/settings", tags=["settings"])
def settings() -> dict[str, str | bool]:
    return {
        "mode": "scaffold",
        "desktop_edition": True,
        "web_edition": True,
    }
