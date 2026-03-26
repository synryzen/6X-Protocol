#!/usr/bin/env python3
"""Validate GitHub Pages SEO essentials (canonical, sitemap, robots)."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


DOCS_DIR = Path("docs")
SITEMAP_FILE = DOCS_DIR / "sitemap.xml"
ROBOTS_FILE = DOCS_DIR / "robots.txt"


class HeadMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonical: str = ""
        self.og_url: str = ""
        self.robots: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "link":
            rel_value = attr_map.get("rel", "").lower()
            if "canonical" in rel_value.split():
                self.canonical = attr_map.get("href", "").strip()
        elif tag.lower() == "meta":
            prop = attr_map.get("property", "").strip().lower()
            name = attr_map.get("name", "").strip().lower()
            content = attr_map.get("content", "").strip()
            if prop == "og:url":
                self.og_url = content
            if name == "robots":
                self.robots = content


def parse_sitemap_locations(path: Path) -> set[str]:
    tree = ET.parse(path)
    root = tree.getroot()
    namespace = ""
    if root.tag.startswith("{") and "}" in root.tag:
        namespace = root.tag[1 : root.tag.index("}")]
    ns = {"s": namespace} if namespace else {}
    loc_path = ".//s:loc" if namespace else ".//loc"
    locations = set()
    for loc in root.findall(loc_path, ns):
        if loc.text and loc.text.strip():
            locations.add(loc.text.strip())
    return locations


def canonical_to_file(canonical_url: str) -> Path:
    match = re.match(r"^https?://[^/]+(?P<path>/.*)$", canonical_url.strip())
    if not match:
        return Path("")
    url_path = match.group("path")
    repo_prefix = "/6X-Protocol"
    if not url_path.startswith(repo_prefix):
        return Path("")
    rel_path = url_path[len(repo_prefix) :]
    if rel_path in {"", "/"}:
        return DOCS_DIR / "index.html"
    if rel_path.endswith("/"):
        rel_path = f"{rel_path}index.html"
    rel_path = rel_path.lstrip("/")
    return DOCS_DIR / rel_path


def parse_robots_sitemap(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "sitemap":
            return value.strip()
    return ""


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not SITEMAP_FILE.exists():
        errors.append(f"Missing sitemap file: {SITEMAP_FILE}")
        print_report(errors, warnings)
        return 1
    if not ROBOTS_FILE.exists():
        errors.append(f"Missing robots file: {ROBOTS_FILE}")
        print_report(errors, warnings)
        return 1

    sitemap_locations = parse_sitemap_locations(SITEMAP_FILE)
    if not sitemap_locations:
        errors.append("Sitemap has no <loc> entries.")

    robots_sitemap = parse_robots_sitemap(ROBOTS_FILE)
    if not robots_sitemap:
        errors.append("robots.txt is missing a Sitemap entry.")
    elif robots_sitemap not in sitemap_locations and not robots_sitemap.endswith("/sitemap.xml"):
        warnings.append(
            "robots.txt Sitemap URL is not listed in sitemap.xml (usually okay), "
            f"got: {robots_sitemap}"
        )

    html_files = sorted(DOCS_DIR.glob("**/*.html"))
    if not html_files:
        errors.append("No HTML files found under docs/.")

    canonical_urls: set[str] = set()
    for html_file in html_files:
        parser = HeadMetaParser()
        parser.feed(html_file.read_text(encoding="utf-8"))

        if not parser.canonical:
            errors.append(f"{html_file}: missing canonical link.")
            continue
        if not parser.robots:
            warnings.append(f"{html_file}: missing robots meta tag.")
        if not parser.og_url:
            warnings.append(f"{html_file}: missing og:url meta tag.")
        elif parser.og_url != parser.canonical:
            errors.append(
                f"{html_file}: og:url does not match canonical "
                f"({parser.og_url} != {parser.canonical})."
            )
        if not parser.canonical.startswith("https://"):
            errors.append(f"{html_file}: canonical should use https:// ({parser.canonical}).")

        canonical_urls.add(parser.canonical)
        if parser.canonical not in sitemap_locations:
            errors.append(f"{html_file}: canonical not present in sitemap.xml ({parser.canonical}).")

        mapped = canonical_to_file(parser.canonical)
        if not mapped or mapped.resolve() != html_file.resolve():
            errors.append(
                f"{html_file}: canonical path does not map back to this file "
                f"({parser.canonical} -> {mapped})."
            )

    for url in sorted(sitemap_locations):
        mapped = canonical_to_file(url)
        if not mapped:
            warnings.append(f"sitemap URL cannot be mapped to docs file: {url}")
            continue
        if not mapped.exists():
            errors.append(f"sitemap URL points to missing file: {url} -> {mapped}")

    missing_in_sitemap = sorted(set(canonical_urls) - sitemap_locations)
    for url in missing_in_sitemap:
        errors.append(f"Canonical URL missing from sitemap.xml: {url}")

    print_report(errors, warnings)
    if errors:
        return 1
    print(
        f"SEO health check passed: {len(html_files)} HTML pages, "
        f"{len(sitemap_locations)} sitemap URLs."
    )
    return 0


def print_report(errors: list[str], warnings: list[str]) -> None:
    for warning in warnings:
        print(f"[seo-health][warn] {warning}")
    for error in errors:
        print(f"[seo-health][error] {error}")


if __name__ == "__main__":
    raise SystemExit(main())
