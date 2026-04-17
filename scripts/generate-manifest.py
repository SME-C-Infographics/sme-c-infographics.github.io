#!/usr/bin/env python3
"""
Scans each infographic category folder for HTML files, extracts their
<title> tags (falling back to the filename), and writes manifest.json
at the repository root so the front page can link to them dynamically.
"""

import html
import json
import os
import re

# Category folder name → display name mapping (order preserved in output)
CATEGORIES = {
    "azure-databases": "Azure Databases",
    "fabric": "Fabric",
    "foundry": "Foundry",
    "github-copilot": "GitHub Copilot",
    "avd": "AVD",
    "app-platform-services": "App Platform Services",
    "azure-openai": "Azure OpenAI",
    "defender-for-cloud": "Defender for Cloud",
    "infrastructure": "Infrastructure"
}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def extract_title(filepath: str, fallback: str) -> str:
    try:
        with open(filepath, encoding="utf-8", errors="replace") as fh:
            content = fh.read(4096)  # only read beginning of file
        match = TITLE_RE.search(content)
        if match:
            # Decode HTML entities (e.g. &amp; → &, &mdash; → —) and
            # collapse any internal whitespace that came from line breaks
            # inside the <title> tag.
            title = html.unescape(match.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                return title
    except OSError:
        pass
    return fallback


def main():
    manifest = {}
    for folder, display_name in CATEGORIES.items():
        category_path = os.path.join(REPO_ROOT, folder)
        entries = []
        if os.path.isdir(category_path):
            for fname in sorted(os.listdir(category_path)):
                if not fname.lower().endswith(".html"):
                    continue
                if fname.lower() == "index.html":
                    continue
                filepath = os.path.join(category_path, fname)
                title = extract_title(filepath, os.path.splitext(fname)[0])
                entries.append({"file": fname, "title": title})
        manifest[folder] = {
            "displayName": display_name,
            "items": entries,
        }

    manifest_path = os.path.join(REPO_ROOT, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Manifest written to {manifest_path}")
    for folder, data in manifest.items():
        print(f"  {folder}: {len(data['items'])} item(s)")


if __name__ == "__main__":
    main()
