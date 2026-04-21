#!/usr/bin/env python3
"""
Report-only LLM-assisted content freshness check.

For each HTML infographic, extracts the visible text and asks an Azure
OpenAI chat model whether anything looks stale (dated product names,
out-of-date pricing, sunsetted services, wrong version numbers, etc.).
Emits one markdown file per page under reports/content-suggestions/.

This script NEVER modifies page content. Output is review-only; humans
decide what to edit. This is the safe seam for LLM involvement.

Cost guardrails:
  - caches results by SHA-256 of the input text so re-running is free
    when nothing changed
  - truncates visible text to --max-chars (default 8000) before sending
  - stdlib-only HTTP (urllib)
  - --dry-run prints the request payload but doesn't call the API

Required environment (production runs):
    AZURE_OPENAI_ENDPOINT     https://<resource>.openai.azure.com
    AZURE_OPENAI_API_KEY      key
    AZURE_OPENAI_DEPLOYMENT   chat deployment name (e.g. gpt-4o-mini)
    AZURE_OPENAI_API_VERSION  e.g. 2024-10-21 (default if unset)

Usage:
    python3 scripts/suggest-content-updates.py --dry-run
    python3 scripts/suggest-content-updates.py
    python3 scripts/suggest-content-updates.py --only fabric/
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(REPO_ROOT, "reports", "content-suggestions")
CACHE_PATH = os.path.join(REPO_ROOT, "reports", ".content-suggestions-cache.json")

CATEGORIES = {
    "azure-databases",
    "fabric",
    "foundry",
    "github-copilot",
    "avd",
    "app-platform-services",
    "azure-openai",
    "defender-for-cloud",
    "infrastructure",
}

META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\']', re.IGNORECASE
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
TAG_RE = re.compile(r"<[^>]+>")

SYSTEM_PROMPT = (
    "You are a content freshness reviewer for a library of SME&C "
    "(Microsoft Small, Medium & Corporate) customer-facing infographics "
    "about Azure and Microsoft 365 products. You are given the visible "
    "text of one infographic. Identify anything that is likely outdated "
    "or now inaccurate: renamed products (e.g. Azure AD, Cognitive "
    "Services), sunsetted services, end-of-life dates that have passed, "
    "pricing figures that may have changed, deprecated SKU names, or "
    "references to preview features that have since GA'd. Be concise. "
    "If the page looks current, say so in one sentence. Return findings "
    "as a markdown bullet list, each bullet starting with the exact "
    "phrase to update, then '→', then the suggested update, then a "
    "short reason. Do not invent facts; if you're unsure, flag it as "
    "'needs human verification'."
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _title(content: str, fallback: str) -> str:
    match = TITLE_RE.search(content)
    if not match:
        return fallback
    title = html.unescape(match.group(1))
    return re.sub(r"\s+", " ", title).strip() or fallback


def visible_text(content: str) -> str:
    no_scripts = SCRIPT_STYLE_RE.sub(" ", content)
    stripped = TAG_RE.sub(" ", no_scripts)
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def iter_target_files(only: str | None) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for folder in sorted(CATEGORIES):
        abs_folder = os.path.join(REPO_ROOT, folder)
        if not os.path.isdir(abs_folder):
            continue
        for fname in sorted(os.listdir(abs_folder)):
            if not fname.lower().endswith(".html"):
                continue
            if fname.lower() == "index.html":
                continue
            full = os.path.join(abs_folder, fname)
            rel = os.path.relpath(full, REPO_ROOT).replace("\\", "/")
            if only and not rel.startswith(only.rstrip("/")):
                continue
            results.append((full, rel))
    return results


def load_cache() -> dict[str, Any]:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def call_azure_openai(
    endpoint: str,
    deployment: str,
    api_version: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float,
) -> str:
    url = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={api_version}"
    )
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "api-key": api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def slug(rel: str) -> str:
    return rel.replace("/", "__").replace(".html", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call the API; print what would be sent.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Restrict to files whose repo-relative path starts with PREFIX.",
    )
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--force", action="store_true", help="Ignore cache.")
    args = parser.parse_args()

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
    api_version = os.environ.get(
        "AZURE_OPENAI_API_VERSION", "2024-10-21"
    )

    live = not args.dry_run
    if live and not (endpoint and api_key and deployment):
        print(
            "ERROR: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and "
            "AZURE_OPENAI_DEPLOYMENT must be set (or pass --dry-run).",
            file=sys.stderr,
        )
        return 2

    os.makedirs(REPORT_DIR, exist_ok=True)
    cache = load_cache()
    files = iter_target_files(args.only)
    print(
        f"suggest-content-updates: {len(files)} page(s). "
        f"mode={'dry-run' if args.dry_run else 'live'}."
    )

    for full, rel in files:
        content = _read(full)
        if META_REFRESH_RE.search(content):
            continue
        title = _title(content, os.path.basename(rel))
        text = visible_text(content)
        if len(text) > args.max_chars:
            text = text[: args.max_chars] + " [...truncated]"

        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cache_hit = cache.get(rel, {}).get("hash") == key
        if cache_hit and not args.force and not args.dry_run:
            print(f"  cache-hit  {rel}")
            continue

        user_prompt = (
            f"TITLE: {title}\nPATH: {rel}\n\nVISIBLE TEXT:\n{text}"
        )

        if args.dry_run:
            print(f"  dry-run    {rel}  ({len(text)} chars would be sent)")
            continue

        try:
            suggestion = call_azure_openai(
                endpoint=endpoint,
                deployment=deployment,
                api_version=api_version,
                api_key=api_key,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                timeout=args.timeout,
            )
        except urllib.error.HTTPError as exc:
            print(f"  http-error {rel}  {exc.code} {exc.reason}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  error      {rel}  {type(exc).__name__}: {exc}")
            continue

        out_path = os.path.join(REPORT_DIR, f"{slug(rel)}.md")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(
                f"# Content freshness review: {title}\n\n"
                f"> Source page: `{rel}` — review these suggestions and apply "
                "by hand where appropriate.\n\n"
                f"{suggestion}\n"
            )
        cache[rel] = {"hash": key, "report": os.path.basename(out_path)}
        save_cache(cache)
        print(f"  wrote      {rel} -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
