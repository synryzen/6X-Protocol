#!/usr/bin/env python3
"""Verify Docker runtime governance baseline files stay intact."""

from __future__ import annotations

from pathlib import Path
import sys


REQUIRED_ENV_KEYS = {
    "SIXPX_IMAGE_TAG",
    "SIXPX_EXPECTED_IMAGE_TAG",
    "SIXPX_RELEASE_CHANNEL",
    "SIXPX_BUILD_SHA",
    "SIXPX_EXPECTED_RELEASE_CHANNEL",
    "SIXPX_EXPECTED_BUILD_SHA",
    "SIXPX_ENFORCE_DIGEST_FOR_GA",
    "SIXPX_ENFORCE_TAG_API_MATCH",
    "SIXPX_MIN_STORE_SCHEMA_VERSION",
    "SIXPX_MAX_STORE_SCHEMA_VERSION",
}

REQUIRED_COMPOSE_SNIPPETS = {
    "image: synryzen/6x-protocol-api:${SIXPX_IMAGE_TAG:-local-dev}",
    "image: synryzen/6x-protocol-web:${SIXPX_IMAGE_TAG:-local-dev}",
    "SIXPX_IMAGE_TAG: ${SIXPX_IMAGE_TAG:-local-dev}",
    "SIXPX_EXPECTED_IMAGE_TAG: ${SIXPX_EXPECTED_IMAGE_TAG:-local-dev}",
    "SIXPX_ENFORCE_DIGEST_FOR_GA: ${SIXPX_ENFORCE_DIGEST_FOR_GA:-true}",
    "SIXPX_ENFORCE_TAG_API_MATCH: ${SIXPX_ENFORCE_TAG_API_MATCH:-false}",
}

REQUIRED_MAIN_SNIPPETS = {
    '"/api/v1/admin/runtime/governance"',
    '"runtime_governance_status"',
    '"runtime_image_tag"',
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fail(message: str) -> None:
    print(f"[governance-check] {message}")
    raise SystemExit(1)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    env_example = repo_root / "docker" / ".env.example"
    compose = repo_root / "docker" / "docker-compose.web.yml"
    main_py = repo_root / "docker" / "api" / "app" / "main.py"

    if not env_example.exists() or not compose.exists() or not main_py.exists():
        _fail("Required governance files are missing.")

    env_text = _read(env_example)
    compose_text = _read(compose)
    main_text = _read(main_py)

    for key in sorted(REQUIRED_ENV_KEYS):
        needle = f"{key}="
        if needle not in env_text:
            _fail(f"Missing {needle} in docker/.env.example")

    for snippet in sorted(REQUIRED_COMPOSE_SNIPPETS):
        if snippet not in compose_text:
            _fail(f"Missing compose governance snippet: {snippet}")

    for snippet in sorted(REQUIRED_MAIN_SNIPPETS):
        if snippet not in main_text:
            _fail(f"Missing API governance snippet: {snippet}")

    print("[governance-check] Runtime governance baseline verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
