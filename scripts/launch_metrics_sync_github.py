#!/usr/bin/env python3
"""Sync daily launch metrics from GitHub release/repo totals."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any


METRICS_HEADERS = [
    "date",
    "day_label",
    "channel_focus",
    "posts_count",
    "impressions",
    "link_clicks",
    "repo_views",
    "stars",
    "release_downloads",
    "deb_downloads",
    "portable_downloads",
    "appimage_downloads",
    "flatpak_downloads",
    "page_views",
    "issues_opened",
    "discussions_opened",
    "newsletter_signups",
    "notes",
]

TOTALS_HEADERS = [
    "date",
    "tag",
    "stars_total",
    "release_downloads_total",
    "deb_downloads_total",
    "portable_downloads_total",
    "appimage_downloads_total",
    "flatpak_downloads_total",
]

SYNC_FIELDS = [
    "stars",
    "release_downloads",
    "deb_downloads",
    "portable_downloads",
    "appimage_downloads",
    "flatpak_downloads",
]


def to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0


def run_gh_api(endpoint: str) -> dict[str, Any]:
    process = subprocess.run(
        ["gh", "api", endpoint],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(process.stdout)


def infer_tag(version_path: Path) -> str:
    if version_path.exists():
        version = version_path.read_text(encoding="utf-8").strip()
        if version:
            return f"v{version.lstrip('v')}"
    return "v0.1.7"


def read_csv_rows(path: Path, headers: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {header: str(raw.get(header, "") or "") for header in headers}
            rows.append(row)
    return rows


def write_csv_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda item: str(item.get("date", "")))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def classify_download_count(name: str, count: int, buckets: dict[str, int]) -> None:
    normalized = name.strip().lower()
    if normalized.endswith(".deb"):
        buckets["deb"] += count
    elif normalized.endswith(".tar.gz"):
        buckets["portable"] += count
    elif normalized.endswith(".appimage"):
        buckets["appimage"] += count
    elif normalized.endswith(".flatpak"):
        buckets["flatpak"] += count


def fetch_totals(repo: str, tag: str) -> dict[str, int]:
    repo_data = run_gh_api(f"repos/{repo}")
    release_data = run_gh_api(f"repos/{repo}/releases/tags/{tag}")
    stars_total = to_int(repo_data.get("stargazers_count", 0))

    buckets = {"deb": 0, "portable": 0, "appimage": 0, "flatpak": 0}
    release_total = 0
    for asset in release_data.get("assets", []) or []:
        name = str(asset.get("name", "") or "")
        count = to_int(asset.get("download_count", 0))
        if not name:
            continue
        if name.strip().lower() == "sha256sums.txt":
            continue
        release_total += count
        classify_download_count(name, count, buckets)

    return {
        "stars_total": stars_total,
        "release_downloads_total": release_total,
        "deb_downloads_total": buckets["deb"],
        "portable_downloads_total": buckets["portable"],
        "appimage_downloads_total": buckets["appimage"],
        "flatpak_downloads_total": buckets["flatpak"],
    }


def previous_totals(rows: list[dict[str, str]], current_date: str) -> dict[str, int]:
    eligible = [row for row in rows if str(row.get("date", "")) < current_date]
    if not eligible:
        return {}
    previous = sorted(eligible, key=lambda item: item.get("date", ""))[-1]
    return {
        "stars_total": to_int(previous.get("stars_total", 0)),
        "release_downloads_total": to_int(previous.get("release_downloads_total", 0)),
        "deb_downloads_total": to_int(previous.get("deb_downloads_total", 0)),
        "portable_downloads_total": to_int(previous.get("portable_downloads_total", 0)),
        "appimage_downloads_total": to_int(previous.get("appimage_downloads_total", 0)),
        "flatpak_downloads_total": to_int(previous.get("flatpak_downloads_total", 0)),
    }


def gains_from_totals(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    if not previous:
        return {
            "stars": current["stars_total"],
            "release_downloads": current["release_downloads_total"],
            "deb_downloads": current["deb_downloads_total"],
            "portable_downloads": current["portable_downloads_total"],
            "appimage_downloads": current["appimage_downloads_total"],
            "flatpak_downloads": current["flatpak_downloads_total"],
        }
    return {
        "stars": max(0, current["stars_total"] - previous.get("stars_total", 0)),
        "release_downloads": max(
            0, current["release_downloads_total"] - previous.get("release_downloads_total", 0)
        ),
        "deb_downloads": max(
            0, current["deb_downloads_total"] - previous.get("deb_downloads_total", 0)
        ),
        "portable_downloads": max(
            0, current["portable_downloads_total"] - previous.get("portable_downloads_total", 0)
        ),
        "appimage_downloads": max(
            0, current["appimage_downloads_total"] - previous.get("appimage_downloads_total", 0)
        ),
        "flatpak_downloads": max(
            0, current["flatpak_downloads_total"] - previous.get("flatpak_downloads_total", 0)
        ),
    }


def upsert_totals_snapshot(path: Path, date_value: str, tag: str, totals: dict[str, int]) -> None:
    rows = read_csv_rows(path, TOTALS_HEADERS)
    target = next((row for row in rows if row.get("date", "") == date_value), None)
    if target is None:
        target = {header: "" for header in TOTALS_HEADERS}
        target["date"] = date_value
        rows.append(target)
    target["tag"] = tag
    target["stars_total"] = str(totals["stars_total"])
    target["release_downloads_total"] = str(totals["release_downloads_total"])
    target["deb_downloads_total"] = str(totals["deb_downloads_total"])
    target["portable_downloads_total"] = str(totals["portable_downloads_total"])
    target["appimage_downloads_total"] = str(totals["appimage_downloads_total"])
    target["flatpak_downloads_total"] = str(totals["flatpak_downloads_total"])
    write_csv_rows(path, TOTALS_HEADERS, rows)


def upsert_metrics_row(
    path: Path,
    date_value: str,
    gains: dict[str, int],
    *,
    mode: str,
    note_suffix: str,
) -> dict[str, str]:
    rows = read_csv_rows(path, METRICS_HEADERS)
    target = next((row for row in rows if row.get("date", "") == date_value), None)
    if target is None:
        target = {header: "" for header in METRICS_HEADERS}
        target["date"] = date_value
        target["day_label"] = f"Day {len(rows) + 1}"
        for field in SYNC_FIELDS:
            target[field] = "0"
        rows.append(target)

    for field in SYNC_FIELDS:
        incoming = gains[field]
        current = to_int(target.get(field, "0"))
        target[field] = str(current + incoming if mode == "add" else incoming)

    existing_note = str(target.get("notes", "") or "").strip()
    target["notes"] = f"{existing_note} | {note_suffix}" if existing_note else note_suffix

    write_csv_rows(path, METRICS_HEADERS, rows)
    return target


def parse_date_or_today(value: str) -> str:
    if not value.strip():
        return dt.date.today().isoformat()
    parsed = dt.date.fromisoformat(value.strip())
    return parsed.isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pull GitHub stars/release download totals, compute daily gains, and sync launch metrics CSV."
        )
    )
    parser.add_argument("--repo", default="synryzen/6X-Protocol", help="owner/repo")
    parser.add_argument("--tag", default="", help="release tag (default inferred from VERSION)")
    parser.add_argument("--date", default="", help="YYYY-MM-DD (default today)")
    parser.add_argument("--mode", choices=["set", "add"], default="set", help="how to write gain values")
    parser.add_argument("--metrics-csv", default="docs/launch_metrics.csv", help="launch metrics CSV path")
    parser.add_argument(
        "--totals-csv",
        default="docs/launch_metrics_totals.csv",
        help="snapshot totals CSV path",
    )
    parser.add_argument(
        "--version-file",
        default="VERSION",
        help="version file used to infer tag when --tag not provided",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if subprocess.run(["which", "gh"], capture_output=True, text=True).returncode != 0:
        raise SystemExit("GitHub CLI `gh` is required for sync. Install and authenticate first.")

    date_value = parse_date_or_today(args.date)
    tag = args.tag.strip() or infer_tag(Path(args.version_file))

    totals_path = Path(args.totals_csv)
    existing_totals_rows = read_csv_rows(totals_path, TOTALS_HEADERS)
    previous = previous_totals(existing_totals_rows, date_value)

    current_totals = fetch_totals(args.repo, tag)
    gains = gains_from_totals(current_totals, previous)

    upsert_totals_snapshot(totals_path, date_value, tag, current_totals)

    note_suffix = (
        f"github-sync {tag}: totals stars={current_totals['stars_total']} "
        f"downloads={current_totals['release_downloads_total']}"
    )
    target = upsert_metrics_row(
        Path(args.metrics_csv),
        date_value,
        gains,
        mode=args.mode,
        note_suffix=note_suffix,
    )

    print(
        f"Synced {date_value} from GitHub ({args.repo} {tag}). "
        f"Gains: stars={gains['stars']} downloads={gains['release_downloads']} "
        f"deb={gains['deb_downloads']} portable={gains['portable_downloads']} "
        f"appimage={gains['appimage_downloads']} flatpak={gains['flatpak_downloads']}."
    )
    print(
        "Metrics row now: "
        f"stars={target.get('stars','0')} "
        f"downloads={target.get('release_downloads','0')} "
        f"deb={target.get('deb_downloads','0')} portable={target.get('portable_downloads','0')} "
        f"appimage={target.get('appimage_downloads','0')} flatpak={target.get('flatpak_downloads','0')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
