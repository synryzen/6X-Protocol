"""Runtime image/version governance checks for Docker GA hardening."""

from __future__ import annotations

import os
import re
from typing import Any

ALLOWED_RELEASE_CHANNELS = {"dev", "beta", "rc", "ga", "stable", "prod"}
_SEMVER_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9.\-]+)?\s*$")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any, *, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    matched = _SEMVER_RE.match(str(value or ""))
    if not matched:
        return None
    return int(matched.group(1)), int(matched.group(2)), int(matched.group(3))


def _compare_semver(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    if left == right:
        return 0
    if left < right:
        return -1
    return 1


def runtime_governance_snapshot(*, api_version: str, store_schema_version: int | str) -> dict[str, Any]:
    image_tag = _clean(os.getenv("SIXPX_IMAGE_TAG", ""))
    expected_image_tag = _clean(os.getenv("SIXPX_EXPECTED_IMAGE_TAG", ""))
    image_digest = _clean(os.getenv("SIXPX_IMAGE_DIGEST", ""))
    release_channel = _clean(os.getenv("SIXPX_RELEASE_CHANNEL", "beta")).lower() or "beta"
    build_sha = _clean(os.getenv("SIXPX_BUILD_SHA", ""))
    build_date = _clean(os.getenv("SIXPX_BUILD_DATE", ""))
    expected_api_version = _clean(os.getenv("SIXPX_EXPECTED_API_VERSION", ""))
    min_api_version = _clean(os.getenv("SIXPX_MIN_API_VERSION", ""))
    max_api_version = _clean(os.getenv("SIXPX_MAX_API_VERSION", ""))
    schema_version = _to_int(store_schema_version, default=0, minimum=0)
    min_store_schema = _to_int(os.getenv("SIXPX_MIN_STORE_SCHEMA_VERSION", "1"), default=1, minimum=1)
    max_store_schema = _to_int(
        os.getenv("SIXPX_MAX_STORE_SCHEMA_VERSION", str(schema_version or 1)),
        default=max(1, schema_version),
        minimum=1,
    )

    issues: list[dict[str, str]] = []

    def add_issue(*, severity: str, code: str, message: str) -> None:
        issues.append({"severity": severity, "code": code, "message": message})

    if release_channel not in ALLOWED_RELEASE_CHANNELS:
        add_issue(
            severity="warn",
            code="release_channel_invalid",
            message=f"Unknown SIXPX_RELEASE_CHANNEL '{release_channel}'.",
        )

    if not image_tag:
        add_issue(
            severity="warn",
            code="image_tag_missing",
            message="SIXPX_IMAGE_TAG is missing; image traceability is reduced.",
        )

    if expected_image_tag and image_tag and expected_image_tag != image_tag:
        add_issue(
            severity="error",
            code="image_tag_mismatch",
            message=(
                "Runtime image tag mismatch: "
                f"expected '{expected_image_tag}', got '{image_tag}'."
            ),
        )

    if not build_sha:
        add_issue(
            severity="warn",
            code="build_sha_missing",
            message="SIXPX_BUILD_SHA is missing; build provenance is incomplete.",
        )

    if release_channel in {"ga", "stable", "prod"} and not image_digest:
        add_issue(
            severity="warn",
            code="image_digest_missing",
            message="SIXPX_IMAGE_DIGEST is recommended for GA/stable/prod releases.",
        )

    if schema_version < min_store_schema:
        add_issue(
            severity="error",
            code="schema_too_old",
            message=(
                f"Store schema v{schema_version} is below minimum supported v{min_store_schema}."
            ),
        )
    if schema_version > max_store_schema:
        add_issue(
            severity="error",
            code="schema_too_new",
            message=(
                f"Store schema v{schema_version} exceeds maximum supported v{max_store_schema}."
            ),
        )

    if expected_api_version and expected_api_version != api_version:
        add_issue(
            severity="error",
            code="api_version_mismatch",
            message=(
                f"API version mismatch: expected '{expected_api_version}', got '{api_version}'."
            ),
        )

    current_semver = _parse_semver(api_version)
    min_semver = _parse_semver(min_api_version) if min_api_version else None
    max_semver = _parse_semver(max_api_version) if max_api_version else None

    if min_api_version and min_semver is None:
        add_issue(
            severity="warn",
            code="min_api_version_invalid",
            message=f"SIXPX_MIN_API_VERSION '{min_api_version}' is not valid semver.",
        )
    if max_api_version and max_semver is None:
        add_issue(
            severity="warn",
            code="max_api_version_invalid",
            message=f"SIXPX_MAX_API_VERSION '{max_api_version}' is not valid semver.",
        )
    if (min_semver or max_semver) and current_semver is None:
        add_issue(
            severity="warn",
            code="api_version_not_semver",
            message=f"Current API version '{api_version}' is not semver-compatible.",
        )

    if current_semver is not None and min_semver is not None:
        if _compare_semver(current_semver, min_semver) < 0:
            add_issue(
                severity="error",
                code="api_version_below_min",
                message=(
                    f"API version '{api_version}' is below minimum supported '{min_api_version}'."
                ),
            )
    if current_semver is not None and max_semver is not None:
        if _compare_semver(current_semver, max_semver) > 0:
            add_issue(
                severity="error",
                code="api_version_above_max",
                message=(
                    f"API version '{api_version}' is above maximum supported '{max_api_version}'."
                ),
            )

    error_count = sum(1 for item in issues if item.get("severity") == "error")
    warn_count = sum(1 for item in issues if item.get("severity") == "warn")
    status = "error" if error_count else "warn" if warn_count else "ok"

    return {
        "status": status,
        "api_version": api_version,
        "release_channel": release_channel,
        "image_tag": image_tag,
        "expected_image_tag": expected_image_tag,
        "image_digest": image_digest,
        "build_sha": build_sha,
        "build_date": build_date,
        "expected_api_version": expected_api_version,
        "min_api_version": min_api_version,
        "max_api_version": max_api_version,
        "store_schema_version": schema_version,
        "min_store_schema_version": min_store_schema,
        "max_store_schema_version": max_store_schema,
        "issue_count": len(issues),
        "error_count": error_count,
        "warn_count": warn_count,
        "issues": issues,
    }
