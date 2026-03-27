#!/usr/bin/env python3
"""Verify release pipeline governance baseline and optional artifact policy."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


REQUIRED_RELEASE_WORKFLOW_SNIPPETS = {
    'tags:\n      - "v*"',
    "attestations: write",
    "id-token: write",
    "uses: actions/attest-build-provenance@v2",
    "uses: softprops/action-gh-release@v2",
    "dist/SHA256SUMS.txt",
    "REQUIRE_ALL_PACKAGES=1 ./scripts/build_packages.sh",
}

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

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
APP_VERSION_RE = re.compile(r'APP_VERSION\s*=\s*"([^"]+)"')


def _fail(message: str) -> None:
    print(f"[release-governance] {message}")
    raise SystemExit(1)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_artifact(dist_dir: Path, pattern: str) -> list[Path]:
    return sorted(path for path in dist_dir.glob(pattern) if path.is_file())


def _verify_workflow_and_env(repo_root: Path) -> None:
    release_workflow = repo_root / ".github" / "workflows" / "release.yml"
    env_example = repo_root / "docker" / ".env.example"

    if not release_workflow.exists():
        _fail("Missing .github/workflows/release.yml")
    if not env_example.exists():
        _fail("Missing docker/.env.example")

    release_text = _read(release_workflow)
    env_text = _read(env_example)

    for snippet in sorted(REQUIRED_RELEASE_WORKFLOW_SNIPPETS):
        if snippet not in release_text:
            _fail(f"Missing release workflow governance snippet: {snippet}")

    for key in sorted(REQUIRED_ENV_KEYS):
        if f"{key}=" not in env_text:
            _fail(f"Missing {key}= in docker/.env.example")


def _verify_tag_docs_alignment(repo_root: Path, expect_tag: str) -> str:
    matched = TAG_RE.match(str(expect_tag or "").strip())
    if not matched:
        _fail(
            f"Expected semantic tag format v<major>.<minor>.<patch>, got '{expect_tag}'."
        )
    version = f"{matched.group(1)}.{matched.group(2)}.{matched.group(3)}"
    release_notes = repo_root / "docs" / f"RELEASE_NOTES_v{version}.md"
    if not release_notes.exists():
        _fail(f"Missing release notes for tag {expect_tag}: {release_notes}")

    docs_index = repo_root / "docs" / "index.html"
    if docs_index.exists():
        index_text = _read(docs_index)
        if f"v{version}" not in index_text:
            _fail(f"docs/index.html does not reference tag v{version}.")
        if f"/download/v{version}/" not in index_text:
            _fail(f"docs/index.html does not include download links for v{version}.")

    return version


def _verify_app_version_exists(repo_root: Path) -> None:
    main_py = repo_root / "docker" / "api" / "app" / "main.py"
    if not main_py.exists():
        _fail("Missing docker/api/app/main.py")
    text = _read(main_py)
    matched = APP_VERSION_RE.search(text)
    if not matched:
        _fail("APP_VERSION constant missing in docker/api/app/main.py")


def _verify_dist_artifacts(dist_dir: Path, version: str | None) -> None:
    if not dist_dir.exists():
        _fail(f"Dist directory not found: {dist_dir}")

    required_patterns = {
        "*.deb": ".deb package",
        "*.tar.gz": "portable tarball",
        "*.AppImage": "AppImage",
        "*.flatpak": "Flatpak bundle",
        "SHA256SUMS.txt": "checksum manifest",
    }
    for pattern, label in required_patterns.items():
        if not _find_artifact(dist_dir, pattern):
            _fail(f"Missing {label} in {dist_dir} ({pattern})")

    if version:
        expected_fragment = f"_{version}_"
        files_to_check = []
        files_to_check.extend(_find_artifact(dist_dir, "*.deb"))
        files_to_check.extend(_find_artifact(dist_dir, "*.tar.gz"))
        files_to_check.extend(_find_artifact(dist_dir, "*.AppImage"))
        files_to_check.extend(_find_artifact(dist_dir, "*.flatpak"))
        for path in files_to_check:
            if expected_fragment not in path.name:
                _fail(
                    "Release artifact version mismatch: "
                    f"expected fragment '{expected_fragment}' in {path.name}"
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expect-tag",
        default="",
        help="Optional tag to enforce release-doc and artifact version alignment (e.g., v0.1.9).",
    )
    parser.add_argument(
        "--dist-dir",
        default="",
        help="Optional dist directory to enforce release artifact presence/version.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    _verify_workflow_and_env(repo_root)
    _verify_app_version_exists(repo_root)

    expected_version: str | None = None
    if args.expect_tag:
        expected_version = _verify_tag_docs_alignment(repo_root, args.expect_tag)

    if args.dist_dir:
        _verify_dist_artifacts((repo_root / args.dist_dir).resolve(), expected_version)

    print("[release-governance] Release governance baseline verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
