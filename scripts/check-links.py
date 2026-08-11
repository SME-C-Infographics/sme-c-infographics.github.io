#!/usr/bin/env python3
"""
Check every external http(s) link in the published infographics and
report broken ones.

Stdlib-only on purpose: matches the "no external build step" norm of the
existing scripts (ensure-tracking.py, ensure-back-button.py,
generate-manifest.py). Uses urllib + a thread pool for parallelism.

Modes:
    python3 scripts/check-links.py
        # report only; exits 0. Writes reports/link-health.json.

    python3 scripts/check-links.py --check
        # exits 1 if any link returns 4xx/5xx or times out. Suitable for
        # warn-only CI steps (don't add this to required checks until
        # the false-positive rate is understood).

Skips:
    - redirect stubs (<meta http-equiv="refresh">)
    - root index.html
    - .git / node_modules / .github / reports directories
    - mailto:, tel:, javascript:, and relative/anchor links (only
      http[s]:// URLs are checked)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_INDEX = os.path.join(REPO_ROOT, "index.html")

META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\']', re.IGNORECASE
)
LINK_RE = re.compile(
    r'(?:href|src)=["\'](https?://[^"\']+)["\']', re.IGNORECASE
)
SKIP_DIRS = {".git", "node_modules", ".github", "reports"}
USER_AGENT = (
    "Mozilla/5.0 (compatible; SMEC-Infographics-LinkCheck/1.0; "
    "+https://sme-c-infographics.github.io/)"
)
DEFAULT_TIMEOUT_S = 12
DEFAULT_WORKERS = 16


def iter_html_files() -> list[str]:
    results: list[str] = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.lower().endswith(".html"):
                continue
            full = os.path.join(root, fname)
            if os.path.abspath(full) == os.path.abspath(ROOT_INDEX):
                continue
            results.append(full)
    return sorted(results)


def collect_links() -> dict[str, list[str]]:
    """Return {url: [repo-relative file paths where it appears]}."""
    index: dict[str, list[str]] = {}
    for path in iter_html_files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        if META_REFRESH_RE.search(content):
            continue
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        for m in LINK_RE.finditer(content):
            url = m.group(1).strip()
            index.setdefault(url, []).append(rel)
    return index


def check_url(url: str, timeout: float) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    # HEAD first (fast); fall back to GET if the server rejects HEAD.
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {
                    "url": url,
                    "status": resp.status,
                    "ok": 200 <= resp.status < 400,
                    "method": method,
                    "final_url": resp.geturl(),
                    "error": None,
                }
        except urllib.error.HTTPError as exc:
            # 405/403 often means HEAD is disallowed; try GET next.
            if method == "HEAD" and exc.code in (400, 403, 405, 501):
                continue
            return {
                "url": url,
                "status": exc.code,
                "ok": False,
                "method": method,
                "final_url": url,
                "error": f"HTTPError {exc.code}: {exc.reason}",
            }
        except urllib.error.URLError as exc:
            if method == "HEAD":
                continue
            return {
                "url": url,
                "status": None,
                "ok": False,
                "method": method,
                "final_url": url,
                "error": f"URLError: {exc.reason}",
            }
        except Exception as exc:  # noqa: BLE001 - we want a structured row
            if method == "HEAD":
                continue
            return {
                "url": url,
                "status": None,
                "ok": False,
                "method": method,
                "final_url": url,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return {
        "url": url,
        "status": None,
        "ok": False,
        "method": "HEAD",
        "final_url": url,
        "error": "Unknown: HEAD and GET both exhausted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--report",
        default=os.path.join("reports", "link-health.json"),
        help="Where to write the JSON report (relative to repo root).",
    )
    args = parser.parse_args()

    links = collect_links()
    urls = sorted(links.keys())
    print(f"Checking {len(urls)} unique link(s) with {args.workers} workers...")

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        future_to_url = {
            ex.submit(check_url, url, args.timeout): url for url in urls
        }
        for fut in concurrent.futures.as_completed(future_to_url):
            row = fut.result()
            row["referenced_in"] = links[row["url"]]
            results.append(row)

    results.sort(key=lambda r: (r["ok"], r["url"]))
    broken = [r for r in results if not r["ok"]]

    report = {
        "summary": {
            "total": len(results),
            "ok": len(results) - len(broken),
            "broken": len(broken),
        },
        "broken": broken,
        "results": results,
    }

    out_path = args.report
    if not os.path.isabs(out_path):
        out_path = os.path.join(REPO_ROOT, out_path)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(
        f"link-health: {report['summary']['ok']}/{report['summary']['total']} ok, "
        f"{report['summary']['broken']} broken. report={out_path}"
    )
    for row in broken[:10]:
        refs = ", ".join(row["referenced_in"][:2])
        extra = "" if len(row["referenced_in"]) <= 2 else f" (+{len(row['referenced_in']) - 2} more)"
        print(f"  BROKEN {row['status']} {row['url']} -- in {refs}{extra}")
    if len(broken) > 10:
        print(f"  ... and {len(broken) - 10} more. See report.")

    if args.check and broken:
        print("::warning::Broken external links found. See report.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
