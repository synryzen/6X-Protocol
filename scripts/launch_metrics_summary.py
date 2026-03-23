#!/usr/bin/env python3
"""Summarize 6X-Protocol launch metrics from a CSV tracker."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import Any


NUMERIC_FIELDS = [
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
]


def to_int(value: Any) -> int:
    if value is None:
        return 0
    raw = str(value).strip().replace(",", "")
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def parse_date(value: str) -> dt.date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"metrics file not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for row in reader:
            normalized = dict(row)
            normalized["date_obj"] = parse_date(normalized.get("date", ""))
            for field in NUMERIC_FIELDS:
                normalized[field] = to_int(normalized.get(field))
            rows.append(normalized)
    rows.sort(key=lambda item: item.get("date_obj") or dt.date.min)
    return rows


def totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {field: 0 for field in NUMERIC_FIELDS}
    for row in rows:
        for field in NUMERIC_FIELDS:
            summary[field] += int(row.get(field, 0))
    return summary


def best_row(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda item: int(item.get(field, 0)))


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def markdown_report(rows: list[dict[str, Any]]) -> str:
    total = totals(rows)
    best_download_day = best_row(rows, "release_downloads")
    best_star_day = best_row(rows, "stars")
    best_traffic_day = best_row(rows, "link_clicks")
    conversion = safe_ratio(total["release_downloads"], total["link_clicks"])
    deb_share = safe_ratio(total["deb_downloads"], max(1, total["release_downloads"]))
    portable_share = safe_ratio(total["portable_downloads"], max(1, total["release_downloads"]))

    lines = [
        "## Launch Metrics Summary",
        "",
        f"- Days tracked: **{len(rows)}**",
        f"- Total posts: **{total['posts_count']}**",
        f"- Total impressions: **{total['impressions']}**",
        f"- Total link clicks: **{total['link_clicks']}**",
        f"- Total release downloads: **{total['release_downloads']}**",
        f"- Total stars gained: **{total['stars']}**",
        f"- Total repo views: **{total['repo_views']}**",
        f"- Total page views: **{total['page_views']}**",
        f"- Click->download conversion: **{conversion * 100:.2f}%**",
        f"- Download mix: **.deb {deb_share * 100:.1f}%** / **portable {portable_share * 100:.1f}%**",
        "",
    ]

    if best_download_day:
        lines.append(
            "- Best download day: "
            f"**{best_download_day.get('date', 'n/a')}** "
            f"({best_download_day.get('release_downloads', 0)} downloads)"
        )
    if best_star_day:
        lines.append(
            "- Best star day: "
            f"**{best_star_day.get('date', 'n/a')}** "
            f"({best_star_day.get('stars', 0)} stars)"
        )
    if best_traffic_day:
        lines.append(
            "- Best traffic day: "
            f"**{best_traffic_day.get('date', 'n/a')}** "
            f"({best_traffic_day.get('link_clicks', 0)} clicks)"
        )

    lines.extend(
        [
            "",
            "### Daily Breakdown",
            "",
            "| Date | Focus | Posts | Clicks | Downloads | Stars |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('date','')} | {row.get('channel_focus','')} | "
            f"{row.get('posts_count', 0)} | {row.get('link_clicks', 0)} | "
            f"{row.get('release_downloads', 0)} | {row.get('stars', 0)} |"
        )

    return "\n".join(lines)


def text_report(rows: list[dict[str, Any]]) -> str:
    total = totals(rows)
    best_download_day = best_row(rows, "release_downloads")
    best_star_day = best_row(rows, "stars")
    conversion = safe_ratio(total["release_downloads"], total["link_clicks"])

    lines = [
        "Launch Metrics Summary",
        "======================",
        f"Days tracked:           {len(rows)}",
        f"Total posts:            {total['posts_count']}",
        f"Total impressions:      {total['impressions']}",
        f"Total link clicks:      {total['link_clicks']}",
        f"Total release downloads:{total['release_downloads']}",
        f"Total stars gained:     {total['stars']}",
        f"Total repo views:       {total['repo_views']}",
        f"Total page views:       {total['page_views']}",
        f"Click->download conv.:  {conversion * 100:.2f}%",
    ]

    if best_download_day:
        lines.append(
            "Best download day:      "
            f"{best_download_day.get('date', 'n/a')} "
            f"({best_download_day.get('release_downloads', 0)})"
        )
    if best_star_day:
        lines.append(
            "Best star day:          "
            f"{best_star_day.get('date', 'n/a')} "
            f"({best_star_day.get('stars', 0)})"
        )

    lines.extend(["", "Daily breakdown:"])
    for row in rows:
        lines.append(
            f"- {row.get('date','')} [{row.get('channel_focus','')}] "
            f"posts={row.get('posts_count', 0)} clicks={row.get('link_clicks', 0)} "
            f"downloads={row.get('release_downloads', 0)} stars={row.get('stars', 0)}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize launch metrics from a CSV tracker."
    )
    parser.add_argument(
        "--csv",
        default="docs/launch_metrics.csv",
        help="Path to CSV metrics file (default: docs/launch_metrics.csv).",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print report in Markdown format.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    path = Path(args.csv)
    rows = load_rows(path)
    if not rows:
        print("No rows found in metrics file.")
        return 0
    report = markdown_report(rows) if args.markdown else text_report(rows)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
