#!/usr/bin/env python3
"""Upsert daily launch metrics into docs/launch_metrics.csv."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import Any


HEADERS = [
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

NUMERIC_FIELDS = {
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
}


def today_iso() -> str:
    return dt.date.today().isoformat()


def to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {header: str(row.get(header, "") or "") for header in HEADERS}
            rows.append(normalized)
    return rows


def default_row(date_value: str, index: int) -> dict[str, str]:
    row = {header: "" for header in HEADERS}
    row["date"] = date_value
    row["day_label"] = f"Day {index}"
    for field in NUMERIC_FIELDS:
        row[field] = "0"
    return row


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda row: row.get("date", ""))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in HEADERS})


def add_or_set_numeric(row: dict[str, str], field: str, value: int, add_mode: bool) -> None:
    current = to_int(row.get(field, "0"))
    row[field] = str(current + value if add_mode else value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upsert daily launch metrics into docs/launch_metrics.csv."
    )
    parser.add_argument("--csv", default="docs/launch_metrics.csv", help="Metrics CSV path.")
    parser.add_argument("--date", default=today_iso(), help="Date in YYYY-MM-DD (default: today).")
    parser.add_argument(
        "--add",
        action="store_true",
        help="Add numeric values to existing row instead of replacing them.",
    )
    parser.add_argument("--day-label", default="", help="Override day label text.")
    parser.add_argument("--channel-focus", default="", help="Set channel focus value.")
    parser.add_argument("--notes", default="", help="Set notes field (replaces previous notes).")
    parser.add_argument(
        "--append-note",
        default="",
        help="Append text to notes field (keeps existing notes).",
    )

    parser.add_argument("--posts", type=int, default=None, help="posts_count")
    parser.add_argument("--impressions", type=int, default=None, help="impressions")
    parser.add_argument("--clicks", type=int, default=None, help="link_clicks")
    parser.add_argument("--repo-views", type=int, default=None, help="repo_views")
    parser.add_argument("--stars", type=int, default=None, help="stars")
    parser.add_argument("--downloads", type=int, default=None, help="release_downloads")
    parser.add_argument("--deb", type=int, default=None, help="deb_downloads")
    parser.add_argument("--portable", type=int, default=None, help="portable_downloads")
    parser.add_argument("--appimage", type=int, default=None, help="appimage_downloads")
    parser.add_argument("--flatpak", type=int, default=None, help="flatpak_downloads")
    parser.add_argument("--page-views", type=int, default=None, help="page_views")
    parser.add_argument("--issues", type=int, default=None, help="issues_opened")
    parser.add_argument("--discussions", type=int, default=None, help="discussions_opened")
    parser.add_argument("--signups", type=int, default=None, help="newsletter_signups")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        parse_date(args.date)
    except ValueError:
        parser.error("--date must be in YYYY-MM-DD format")

    path = Path(args.csv)
    rows = load_rows(path)

    target = next((row for row in rows if row.get("date", "") == args.date), None)
    if target is None:
        existing_count = len(rows)
        target = default_row(args.date, existing_count + 1)
        rows.append(target)

    if args.day_label:
        target["day_label"] = args.day_label.strip()
    if args.channel_focus:
        target["channel_focus"] = args.channel_focus.strip()

    numeric_map = {
        "posts_count": args.posts,
        "impressions": args.impressions,
        "link_clicks": args.clicks,
        "repo_views": args.repo_views,
        "stars": args.stars,
        "release_downloads": args.downloads,
        "deb_downloads": args.deb,
        "portable_downloads": args.portable,
        "appimage_downloads": args.appimage,
        "flatpak_downloads": args.flatpak,
        "page_views": args.page_views,
        "issues_opened": args.issues,
        "discussions_opened": args.discussions,
        "newsletter_signups": args.signups,
    }

    for field, value in numeric_map.items():
        if value is None:
            continue
        add_or_set_numeric(target, field, int(value), bool(args.add))

    if args.notes:
        target["notes"] = args.notes.strip()
    if args.append_note:
        existing = str(target.get("notes", "") or "").strip()
        suffix = args.append_note.strip()
        target["notes"] = f"{existing} | {suffix}" if existing and suffix else (suffix or existing)

    write_rows(path, rows)

    print(
        f"Updated {path} for {args.date}: "
        f"posts={target.get('posts_count','0')} "
        f"clicks={target.get('link_clicks','0')} "
        f"downloads={target.get('release_downloads','0')} "
        f"stars={target.get('stars','0')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
