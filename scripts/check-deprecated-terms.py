#!/usr/bin/env python3
"""
Scan HTML pages for deprecated product names / outdated terminology
defined in scripts/terminology.json, and optionally rewrite them.

Idempotent: running twice in a row with --apply produces no changes on
the second run. Rules skip matches that are already adjacent to their
replacement (e.g. "Microsoft Entra ID (previously Azure Active
Directory)" is left alone).

Per-page exceptions:
    Wrap any intentional use of a deprecated term with the inline marker
    pair to exempt it from both --check failures and --apply rewrites:

        <!-- smec-keep-term -->Azure OpenAI Service<!-- /smec-keep-term -->

    Use this when the page is teaching a rename, comparing the old and
    new names, or otherwise needs the legacy term to read correctly.
    Exempted matches are still recorded in the JSON report under the
    top-level "exempted" key so reviewers can audit them. Unmatched
    open/close markers fail --check.

Modes:
    python3 scripts/check-deprecated-terms.py
        # report only; exits 0. Writes reports/deprecated-terms.json
        # and prints a short summary.

    python3 scripts/check-deprecated-terms.py --check
        # exits 1 if any deprecated term is found; does not modify files.
        # Suitable for warn-only CI.

    python3 scripts/check-deprecated-terms.py --apply
        # rewrites matches per terminology.json. By default only rules
        # at severity=high are applied; pass --min-severity medium or
        # --min-severity low to include lower-severity rules.

Redirect stubs (<meta http-equiv="refresh">) and the root index.html are
skipped, matching the pattern used by ensure-tracking.py /
ensure-back-button.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMS_PATH = os.path.join(os.path.dirname(__file__), "terminology.json")
ROOT_INDEX = os.path.join(REPO_ROOT, "index.html")

META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\']', re.IGNORECASE
)
SKIP_DIRS = {".git", "node_modules", ".github", "reports"}
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}

# Per-page inline exception markers. Authors wrap a span where a deprecated
# term is intentional (e.g. when the page is teaching the rename) with:
#
#     <!-- smec-keep-term -->Azure OpenAI Service<!-- /smec-keep-term -->
#
# Any rule match whose [start, end) is fully contained inside one of these
# blocks is exempted from --check failures and from --apply rewrites. The
# exemption is recorded separately in the JSON report under "exempted" so
# reviewers can audit what's been intentionally bypassed.
#
# Nesting is NOT supported. Rule-id targeting is intentionally NOT supported
# in v1 — keep the marker minimal.
KEEP_TERM_OPEN_RE = re.compile(r"<!--\s*smec-keep-term\s*-->", re.IGNORECASE)
KEEP_TERM_CLOSE_RE = re.compile(r"<!--\s*/\s*smec-keep-term\s*-->", re.IGNORECASE)
KEEP_TERM_BLOCK_RE = re.compile(
    r"<!--\s*smec-keep-term\s*-->.*?<!--\s*/\s*smec-keep-term\s*-->",
    re.DOTALL | re.IGNORECASE,
)


def find_keep_term_spans(content: str) -> list[tuple[int, int]]:
    """Return [(start, end), ...] for every well-formed keep-term block.
    The whole marker pair (including comments) is treated as protected."""
    return [(m.start(), m.end()) for m in KEEP_TERM_BLOCK_RE.finditer(content)]


def find_malformed_keep_terms(content: str) -> tuple[int, int]:
    """Return (unmatched_open_count, unmatched_close_count) — anything not
    swallowed by KEEP_TERM_BLOCK_RE."""
    consumed: list[tuple[int, int]] = find_keep_term_spans(content)

    def _outside(idx: int) -> bool:
        return not any(s <= idx < e for s, e in consumed)

    opens = sum(1 for m in KEEP_TERM_OPEN_RE.finditer(content) if _outside(m.start()))
    closes = sum(1 for m in KEEP_TERM_CLOSE_RE.finditer(content) if _outside(m.start()))
    return opens, closes


def is_in_keep_term(match: re.Match, keep_spans: list[tuple[int, int]]) -> bool:
    """True iff the match is fully contained inside a keep-term block."""
    return any(s <= match.start() and match.end() <= e for s, e in keep_spans)


def load_rules() -> list[dict[str, Any]]:
    with open(TERMS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    rules = data.get("rules", [])
    for rule in rules:
        rule["compiled"] = re.compile(rule["pattern"])
        if rule.get("severity") not in SEVERITY_ORDER:
            raise ValueError(
                f"rule '{rule.get('id')}' has invalid severity "
                f"'{rule.get('severity')}'; expected one of {sorted(SEVERITY_ORDER)}"
            )
    return rules


def is_already_fixed(content: str, match: re.Match, replacement: str) -> bool:
    """True if the match already sits inside a parenthetical clarification
    right after its replacement, e.g.
        'Microsoft Entra ID (previously Azure Active Directory)'
    We want to leave those alone so history/migration copy still reads.
    """
    start = match.start()
    # Look back up to 80 characters for the replacement phrase.
    window_start = max(0, start - 80)
    preceding = content[window_start:start]
    if replacement in preceding and "(previously" in preceding.lower():
        return True
    # Also skip when the match is inside href="..." or src="..." since
    # URLs are stable identifiers we shouldn't rewrite blindly.
    quote_left = content.rfind('"', 0, start)
    quote_right = content.find('"', match.end())
    if quote_left != -1 and quote_right != -1:
        attr_window = content[max(0, quote_left - 20):quote_left]
        if re.search(r"\b(?:href|src)\s*=\s*$", attr_window, re.IGNORECASE):
            return True
    return False


def scan_file(
    path: str, rules: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, int]]:
    """Returns (hits, exempted, (unmatched_open, unmatched_close))."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    if META_REFRESH_RE.search(content):
        return [], [], (0, 0)

    keep_spans = find_keep_term_spans(content)
    malformed = find_malformed_keep_terms(content)

    hits: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    for rule in rules:
        for m in rule["compiled"].finditer(content):
            if is_already_fixed(content, m, rule["replacement"]):
                continue
            line = content.count("\n", 0, m.start()) + 1
            entry = {
                "rule_id": rule["id"],
                "pattern": rule["pattern"],
                "match": m.group(0),
                "replacement": rule["replacement"],
                "severity": rule.get("severity", "medium"),
                "line": line,
                "span": [m.start(), m.end()],
            }
            if is_in_keep_term(m, keep_spans):
                entry["reason"] = "smec-keep-term"
                exempted.append(entry)
            else:
                hits.append(entry)
    return hits, exempted, malformed


def apply_fixes(
    path: str, rules: list[dict[str, Any]], min_severity: int
) -> int:
    with open(path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    if META_REFRESH_RE.search(content):
        return 0

    total = 0
    for rule in rules:
        if SEVERITY_ORDER[rule.get("severity", "medium")] < min_severity:
            continue
        pattern: re.Pattern[str] = rule["compiled"]
        replacement: str = rule["replacement"]

        # Recompute keep-term spans before each rule because earlier rules
        # may have rewritten content and shifted offsets.
        keep_spans = find_keep_term_spans(content)

        # Walk matches right-to-left so indices stay valid across edits.
        matches = list(pattern.finditer(content))
        for m in reversed(matches):
            if is_already_fixed(content, m, replacement):
                continue
            if is_in_keep_term(m, keep_spans):
                continue
            content = content[: m.start()] + replacement + content[m.end():]
            total += 1

    if total:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return total


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any deprecated term is found; do not modify files.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite deprecated terms per terminology.json.",
    )
    parser.add_argument(
        "--min-severity",
        choices=sorted(SEVERITY_ORDER, key=lambda s: SEVERITY_ORDER[s]),
        default="high",
        help=(
            "Severity threshold for --apply. Defaults to 'high' so "
            "lower-severity rules require an explicit opt-in. Has no "
            "effect in --check or report mode (those always report all "
            "rules)."
        ),
    )
    parser.add_argument(
        "--report",
        default=os.path.join("reports", "deprecated-terms.json"),
        help="Where to write the JSON report (relative to repo root).",
    )
    args = parser.parse_args()

    rules = load_rules()
    files = iter_html_files()
    min_sev = SEVERITY_ORDER[args.min_severity]

    report: dict[str, Any] = {"files": {}, "exempted": {}, "summary": {}}
    malformed_files: list[dict[str, Any]] = []
    total_hits = 0
    total_exempted = 0
    total_applied = 0

    for path in files:
        hits, exempted, malformed = scan_file(path, rules)
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        if args.apply:
            applied = apply_fixes(path, rules, min_sev)
            total_applied += applied
            # Re-scan post-apply so the report reflects remaining issues
            # (should be zero for rules at/above the severity threshold
            # if our is_already_fixed guard is correct).
            hits, exempted, malformed = scan_file(path, rules)
        if hits:
            report["files"][rel] = hits
            total_hits += len(hits)
        if exempted:
            report["exempted"][rel] = exempted
            total_exempted += len(exempted)
        unmatched_open, unmatched_close = malformed
        if unmatched_open or unmatched_close:
            malformed_files.append(
                {
                    "path": rel,
                    "unmatched_open": unmatched_open,
                    "unmatched_close": unmatched_close,
                }
            )

    report["summary"] = {
        "files_scanned": len(files),
        "files_with_hits": len(report["files"]),
        "total_hits": total_hits,
        "files_with_exemptions": len(report["exempted"]),
        "exempted_hits": total_exempted,
        "malformed_keep_term_files": malformed_files,
        "total_applied": total_applied,
        "mode": "apply" if args.apply else ("check" if args.check else "report"),
        "min_severity_for_apply": args.min_severity,
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

    summary = report["summary"]
    print(
        f"deprecated-terms: {summary['total_hits']} hit(s) across "
        f"{summary['files_with_hits']}/{summary['files_scanned']} file(s). "
        f"mode={summary['mode']}. report={out_path}"
    )
    if total_exempted:
        print(
            f"  {total_exempted} exempted hit(s) across "
            f"{summary['files_with_exemptions']} file(s) "
            f"(smec-keep-term)."
        )
    if args.apply and total_applied:
        print(f"  applied {total_applied} replacement(s).")
    if malformed_files:
        print(
            f"::warning::{len(malformed_files)} file(s) have unmatched "
            f"smec-keep-term markers; see report."
        )

    if args.check and (total_hits or malformed_files):
        if total_hits:
            print("::warning::Deprecated terminology found. See report.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
