#!/usr/bin/env python3
"""
Read-only inventory/audit of every published HTML infographic.

Walks the category folders used by generate-manifest.py, parses each page,
and emits a JSON report with everything that might matter for downstream
automation: titles, head-tag hygiene, tracking/back-button markers,
external links, image sources, and patterns that often drift over time
(years, deprecated product names, pricing strings).

The script is intentionally pure — it never modifies pages. Its output
feeds later automations (link checker, deprecated-terms fixer, content-
freshness LLM, CI reports).

Usage:
    python3 scripts/audit-pages.py
        # writes reports/audit.json and prints a short summary

    python3 scripts/audit-pages.py --out reports/audit.json
        # custom output path

    python3 scripts/audit-pages.py --stdout
        # print JSON to stdout instead of writing a file
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mirror of scripts/generate-manifest.py so both stay in lockstep.
CATEGORIES = {
    "azure-databases": "Azure Databases",
    "fabric": "Fabric",
    "foundry": "AI & Foundry",
    "github-copilot": "GitHub Copilot",
    "avd": "AVD",
    "app-platform-services": "App Platform Services",
    "defender-for-cloud": "Defender for Cloud",
    "infrastructure": "Infrastructure",
}

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\']', re.IGNORECASE
)
META_DESC_RE = re.compile(
    r'<meta\s+[^>]*name=["\']description["\'][^>]*>', re.IGNORECASE
)
META_CHARSET_RE = re.compile(r'<meta\s+[^>]*charset=', re.IGNORECASE)
META_VIEWPORT_RE = re.compile(
    r'<meta\s+[^>]*name=["\']viewport["\']', re.IGNORECASE
)
HTML_LANG_RE = re.compile(r"<html[^>]*\blang=", re.IGNORECASE)
OG_TAG_RE = re.compile(
    r'<meta\s+[^>]*property=["\']og:([a-z:]+)["\']', re.IGNORECASE
)
TWITTER_TAG_RE = re.compile(
    r'<meta\s+[^>]*name=["\']twitter:([a-z:]+)["\']', re.IGNORECASE
)
FAVICON_RE = re.compile(
    r'<link\s+[^>]*rel=["\'](?:shortcut\s+)?icon["\']', re.IGNORECASE
)
LINK_HREF_RE = re.compile(
    r'<a\s+[^>]*href=["\'](https?://[^"\']+)["\']', re.IGNORECASE
)
IMG_SRC_RE = re.compile(
    r'<img\s+[^>]*src=["\']([^"\']+)["\']([^>]*)>', re.IGNORECASE
)
SCRIPT_SRC_RE = re.compile(
    r'<script\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE
)
BODY_TEXT_STRIP_RE = re.compile(r"<[^>]+>")
YEAR_RE = re.compile(r"\b(20\d{2})\b")
# Simple pricing patterns like "$30/mo", "$20/user", "$0.01 per 1K".
PRICE_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/|per\b)", re.IGNORECASE)
EOL_RE = re.compile(
    r"\b(?:end[-\s]of[-\s](?:life|support)|EOL|EOS)\b", re.IGNORECASE
)

# Markers from existing chrome scripts.
TRACKING_MARKER = 'data-website-id="9478c1a0-93c6-4c21-855a-69e50e15cbc4"'
BACK_BUTTON_MARKER = 'data-smec-back-button="v1"'


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _extract_title(content: str, fallback: str) -> str:
    match = TITLE_RE.search(content)
    if not match:
        return fallback
    title = html.unescape(match.group(1))
    title = re.sub(r"\s+", " ", title).strip()
    return title or fallback


def _visible_text(content: str) -> str:
    # Drop <script>/<style> blocks first, then strip tags. Good enough for
    # lexical scans (years, product names, pricing).
    no_scripts = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        " ",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    stripped = BODY_TEXT_STRIP_RE.sub(" ", no_scripts)
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def audit_page(path: str, rel_path: str) -> dict[str, Any]:
    content = _read(path)
    is_redirect = bool(META_REFRESH_RE.search(content))
    fallback = os.path.splitext(os.path.basename(path))[0]
    title = _extract_title(content, fallback)

    og_tags = sorted({m.group(1).lower() for m in OG_TAG_RE.finditer(content)})
    twitter_tags = sorted(
        {m.group(1).lower() for m in TWITTER_TAG_RE.finditer(content)}
    )
    external_links = sorted(
        {m.group(1) for m in LINK_HREF_RE.finditer(content)}
    )
    img_tags = IMG_SRC_RE.findall(content)
    images = [
        {
            "src": src,
            "has_alt": bool(re.search(r'\balt=', rest, re.IGNORECASE)),
        }
        for src, rest in img_tags
    ]
    script_srcs = sorted({m.group(1) for m in SCRIPT_SRC_RE.finditer(content)})

    text = _visible_text(content)
    years = sorted({int(y) for y in YEAR_RE.findall(text)})
    prices = sorted(set(PRICE_RE.findall(text)))[:10]
    eol_mentions = bool(EOL_RE.search(text))

    return {
        "path": rel_path.replace("\\", "/"),
        "title": title,
        "byte_size": os.path.getsize(path),
        "is_redirect_stub": is_redirect,
        "chrome": {
            "has_tracking": TRACKING_MARKER in content,
            "has_back_button": BACK_BUTTON_MARKER in content,
            "has_meta_description": bool(META_DESC_RE.search(content)),
            "has_meta_charset": bool(META_CHARSET_RE.search(content)),
            "has_meta_viewport": bool(META_VIEWPORT_RE.search(content)),
            "has_html_lang": bool(HTML_LANG_RE.search(content)),
            "has_favicon": bool(FAVICON_RE.search(content)),
            "og_tags": og_tags,
            "twitter_tags": twitter_tags,
        },
        "counts": {
            "external_links": len(external_links),
            "images": len(images),
            "images_missing_alt": sum(1 for i in images if not i["has_alt"]),
            "script_srcs": len(script_srcs),
        },
        "external_links": external_links,
        "script_srcs": script_srcs,
        "images": images,
        "content_signals": {
            "years_mentioned": years,
            "price_strings": prices,
            "mentions_eol_or_eos": eol_mentions,
            "visible_text_length": len(text),
        },
    }


def collect_pages() -> list[tuple[str, str]]:
    """Return (absolute_path, repo_relative_path) tuples for every HTML
    infographic in the known category folders."""
    pages: list[tuple[str, str]] = []
    for folder in CATEGORIES:
        category_path = os.path.join(REPO_ROOT, folder)
        if not os.path.isdir(category_path):
            continue
        for fname in sorted(os.listdir(category_path)):
            if not fname.lower().endswith(".html"):
                continue
            if fname.lower() == "index.html":
                continue
            abs_path = os.path.join(category_path, fname)
            rel_path = os.path.relpath(abs_path, REPO_ROOT)
            pages.append((abs_path, rel_path))
    return pages


def build_report() -> dict[str, Any]:
    pages = collect_pages()
    entries = [audit_page(abs_path, rel) for abs_path, rel in pages]

    summary = {
        "total_pages": len(entries),
        "pages_missing_tracking": sum(
            1 for e in entries if not e["chrome"]["has_tracking"]
        ),
        "pages_missing_back_button": sum(
            1 for e in entries if not e["chrome"]["has_back_button"]
        ),
        "pages_missing_meta_description": sum(
            1 for e in entries if not e["chrome"]["has_meta_description"]
        ),
        "pages_missing_og_tags": sum(
            1 for e in entries if not e["chrome"]["og_tags"]
        ),
        "pages_missing_favicon": sum(
            1 for e in entries if not e["chrome"]["has_favicon"]
        ),
        "pages_missing_html_lang": sum(
            1 for e in entries if not e["chrome"]["has_html_lang"]
        ),
        "images_missing_alt": sum(
            e["counts"]["images_missing_alt"] for e in entries
        ),
        "total_external_links": sum(
            e["counts"]["external_links"] for e in entries
        ),
    }
    return {"summary": summary, "pages": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=os.path.join("reports", "audit.json"),
        help="Output JSON path (relative to repo root). Default: reports/audit.json",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout instead of writing a file.",
    )
    args = parser.parse_args()

    report = build_report()
    payload = json.dumps(report, indent=2, ensure_ascii=False)

    if args.stdout:
        sys.stdout.write(payload + "\n")
        return 0

    out_path = args.out
    if not os.path.isabs(out_path):
        out_path = os.path.join(REPO_ROOT, out_path)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(payload + "\n")

    summary = report["summary"]
    print(f"Audit written to {out_path}")
    print(f"  pages: {summary['total_pages']}")
    for key in (
        "pages_missing_tracking",
        "pages_missing_back_button",
        "pages_missing_meta_description",
        "pages_missing_og_tags",
        "pages_missing_favicon",
        "pages_missing_html_lang",
        "images_missing_alt",
    ):
        print(f"  {key}: {summary[key]}")
    print(f"  total_external_links: {summary['total_external_links']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
