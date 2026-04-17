#!/usr/bin/env python3
"""
Ensures a floating "Back to SME&C Infographics" button is present on
every HTML infographic page. The button links to the library landing
page ("/") so users who arrive directly on an infographic can return
to the index.

Collapsed, the button is a small circular icon in the top-left corner;
on hover, focus, or on coarse-pointer (touch) devices it expands to
reveal the label "Back to SME&C Infographics".

Idempotent: if the button is already present (detected by a unique
anchor + style marker pair) the file is left unchanged. Redirect stubs
(<meta http-equiv="refresh">) and the root index.html library landing
page are skipped.

The button's CSS is injected before </head> and the anchor element is
injected immediately after the opening <body ...> tag.

Usage:
    python3 scripts/ensure-back-button.py          # add button where missing
    python3 scripts/ensure-back-button.py --check  # fail (exit 1) if any
                                                   # file is missing it;
                                                   # do not modify files
"""

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_INDEX = os.path.join(REPO_ROOT, "index.html")

MARKER = 'data-smec-back-button="v1"'
STYLE_MARKER = "/* smec-back-btn v1 */"

BACK_BUTTON_STYLE = (
    "<style>" + STYLE_MARKER + """
.smec-back-btn { position: fixed; top: 12px; left: 12px; z-index: 9999;
  display: inline-flex; align-items: center; justify-content: center;
  gap: 0; width: 40px; height: 40px; padding: 0; border-radius: 20px;
  background: rgba(0, 120, 212, 0.92); color: #fff; text-decoration: none;
  font: 600 13px/1 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18); backdrop-filter: blur(6px);
  transition: width 0.25s ease, padding 0.25s ease, gap 0.2s ease, background 0.2s ease;
  overflow: hidden; white-space: nowrap; }
.smec-back-btn:hover, .smec-back-btn:focus-visible {
  width: auto; gap: 8px; padding: 0 14px 0 10px;
  background: rgba(0, 90, 158, 0.96); color: #fff; text-decoration: none; }
.smec-back-btn:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
.smec-back-btn__icon { flex: 0 0 auto; }
.smec-back-btn__label { max-width: 0; opacity: 0;
  transition: max-width 0.25s ease, opacity 0.2s ease; }
.smec-back-btn:hover .smec-back-btn__label,
.smec-back-btn:focus-visible .smec-back-btn__label { max-width: 260px; opacity: 1; }
@media (hover: none) {
  .smec-back-btn { width: auto; gap: 8px; padding: 0 14px 0 10px; }
  .smec-back-btn__label { max-width: 260px; opacity: 1; }
}
@media (max-width: 600px) { .smec-back-btn { top: 8px; left: 8px; } }
</style>"""
)

BACK_BUTTON_ANCHOR = (
    '<a href="/" class="smec-back-btn" ' + MARKER
    + ' aria-label="Back to SME&amp;C Infographics">'
    '<svg class="smec-back-btn__icon" aria-hidden="true" viewBox="0 0 24 24"'
    ' width="18" height="18"><path fill="currentColor"'
    ' d="M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>'
    '<span class="smec-back-btn__label">Back to SME&amp;C Infographics</span>'
    '</a>'
)

HEAD_CLOSE_RE = re.compile(r"^(?P<indent>[ \t]*)</head>", re.MULTILINE)
BODY_OPEN_RE = re.compile(r"(<body\b[^>]*>)", re.IGNORECASE)
META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\']', re.IGNORECASE
)
ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bdata-smec-back-button\s*=\s*["\']v1["\']', re.IGNORECASE
)

SKIP_DIRS = {".git", "node_modules", ".github"}


def iter_html_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.lower().endswith(".html"):
                yield os.path.join(dirpath, fname)


def ensure_button(filepath: str, check_only: bool = False) -> str:
    """Return one of:
        'added'    - button injected
        'missing'  - button missing (check_only mode)
        'present'  - anchor and style marker both already present
        'skipped'  - redirect stub or root index (not applicable)
        'nohead'   - no </head> tag
        'nobody'   - no <body> tag
    """
    if os.path.abspath(filepath) == ROOT_INDEX:
        return "skipped"

    with open(filepath, encoding="utf-8", newline="") as fh:
        content = fh.read()

    if META_REFRESH_RE.search(content):
        return "skipped"

    has_anchor = bool(ANCHOR_RE.search(content))
    has_style = STYLE_MARKER in content
    if has_anchor and has_style:
        return "present"

    head_match = HEAD_CLOSE_RE.search(content)
    if not head_match:
        return "nohead"
    body_match = BODY_OPEN_RE.search(content)
    if not body_match:
        return "nobody"

    if check_only:
        return "missing"

    # Preserve the file's existing line-ending style.
    nl = "\r\n" if "\r\n" in content else "\n"

    new_content = content

    if not has_style:
        indent = head_match.group("indent")
        style_block = nl.join(
            indent + line if line else line
            for line in BACK_BUTTON_STYLE.splitlines()
        ) + nl
        new_content = (
            new_content[: head_match.start()]
            + style_block
            + new_content[head_match.start() :]
        )
        body_match = BODY_OPEN_RE.search(new_content)
        if not body_match:
            return "nobody"

    if not has_anchor:
        insert_at = body_match.end()
        anchor_block = nl + BACK_BUTTON_ANCHOR + nl
        new_content = (
            new_content[:insert_at] + anchor_block + new_content[insert_at:]
        )

    with open(filepath, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_content)
    return "added"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not modify files; exit 1 if any page is missing the button.",
    )
    args = parser.parse_args()

    totals = {
        "added": [],
        "missing": [],
        "present": [],
        "skipped": [],
        "nohead": [],
        "nobody": [],
    }
    for filepath in sorted(iter_html_files(REPO_ROOT)):
        rel = os.path.relpath(filepath, REPO_ROOT).replace(os.sep, "/")
        status = ensure_button(filepath, check_only=args.check)
        totals[status].append(rel)

    for status, label in (
        ("added", "Added button"),
        ("missing", "Missing button"),
        ("present", "Already present"),
        ("skipped", "Skipped (redirect or root index)"),
        ("nohead", "No </head> found"),
        ("nobody", "No <body> found"),
    ):
        files = totals[status]
        print(f"{label}: {len(files)}")
        for f in files:
            print(f"  - {f}")

    exit_code = 0
    if totals["nohead"] or totals["nobody"]:
        print(
            "ERROR: one or more HTML files are missing <head> or <body> tags.",
            file=sys.stderr,
        )
        exit_code = 1
    if args.check and totals["missing"]:
        print(
            "ERROR: one or more HTML files are missing the SME&C back button. "
            "Run `python3 scripts/ensure-back-button.py` to add it.",
            file=sys.stderr,
        )
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
