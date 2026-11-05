#!/usr/bin/env python3
"""Publish partner-events/*.md into the marked region of the partner events page.

Uses only the Python standard library. --validate-only checks source submissions;
--check also verifies generated content without writing. Site chrome is preserved.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "partner-events"
PAGE = ROOT / "events" / "partner-events.html"
START = "<!-- smec-partner-events v1 -->"
END = "<!-- /smec-partner-events -->"
REQUIRED = {
    "title", "partner", "start", "end", "format", "location",
    "registration_url", "cost", "topics",
}
FORMATS = {"Virtual", "In person", "Hybrid"}
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})")


def parse_datetime(value: str, field: str) -> datetime:
    if not TIMESTAMP.fullmatch(value):
        raise ValueError(f"{field} must be YYYY-MM-DDTHH:MM with Z or a UTC offset")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError(f"{field} has an invalid UTC offset")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid date/time: {value}") from exc


def parse_event(path: Path) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.md", path.name):
        raise ValueError("filename must be kebab-case and end in .md")
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("start the file with a --- metadata block")
    try:
        boundary = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("close the metadata block with ---") from exc
    fields = {}
    for line in lines[1:boundary]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or key not in REQUIRED:
            raise ValueError(f"unknown or malformed metadata field: {line}")
        if key in fields:
            raise ValueError(f"duplicate metadata field: {key}")
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{key}: invalid double-quoted string") from exc
        elif value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise ValueError(f"{key}: unclosed single-quoted string")
            value = value[1:-1].replace("''", "'")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must contain text")
        if any(ord(char) < 32 for char in value):
            raise ValueError(f"{key} must be a single line without control characters")
        fields[key] = value.strip()
    missing = REQUIRED - fields.keys()
    if missing:
        raise ValueError("missing required fields: " + ", ".join(sorted(missing)))
    start = parse_datetime(fields["start"], "start")
    end = parse_datetime(fields["end"], "end")
    if end <= start:
        raise ValueError("end must be later than start")
    if fields["format"] not in FORMATS:
        raise ValueError("format must be Virtual, In person, or Hybrid")
    url = fields["registration_url"]
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("registration_url is not a valid URL") from exc
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or "\\" in url or any(char.isspace() for char in url)
        or (port is not None and port == 0)
    ):
        raise ValueError("registration_url must be an absolute HTTPS URL without credentials")
    topics = [topic.strip() for topic in fields["topics"].split(",")]
    if any(not topic for topic in topics) or len(set(topics)) != len(topics):
        raise ValueError("topics must be a comma-separated list without empty or duplicate topics")
    body = "\n".join(lines[boundary + 1:]).strip()
    if not body:
        raise ValueError("add a description below the metadata block")
    return {
        **fields, "id": path.stem, "topics": topics, "body": body,
        "start_date": start, "end_date": end,
    }


def load_events(directory: Path = SOURCE) -> list[dict]:
    if not directory.is_dir():
        raise ValueError(f"source directory not found: {directory}")
    events = []
    errors = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("_"):
            continue
        if path.is_symlink() or path.is_dir() or path.suffix.lower() != ".md":
            errors.append(f"{path.name}: only event .md files belong in this directory")
            continue
        try:
            events.append(parse_event(path))
        except (ValueError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        raise ValueError("\n".join(errors))
    return sorted(events, key=lambda event: (event["start_date"], event["id"]))


def render_description(body: str) -> str:
    """Render paragraphs and unordered lists; never interpret raw HTML."""
    blocks = []
    paragraph = []
    bullets = []

    def flush():
        if paragraph:
            blocks.append("<p>" + html.escape(" ".join(paragraph)) + "</p>")
            paragraph.clear()
        if bullets:
            blocks.append("<ul>" + "".join(
                "<li>" + html.escape(item) + "</li>" for item in bullets
            ) + "</ul>")
            bullets.clear()

    for line in body.splitlines():
        if not line.strip():
            flush()
        elif line.startswith(("- ", "* ")):
            if paragraph:
                flush()
            bullets.append(line[2:])
        else:
            if bullets:
                flush()
            paragraph.append(line.strip())
    flush()
    return "\n".join(blocks)


def fallback_time(value: datetime) -> str:
    offset = value.strftime("%z")
    return value.strftime("%b %d, %Y, %H:%M") + f" UTC{offset[:3]}:{offset[3:]}"


def render_event(event: dict) -> str:
    esc = html.escape
    attributes = {
        "start": event["start"], "end": event["end"],
        "partner": event["partner"], "format": event["format"],
        "topics": json.dumps(event["topics"], ensure_ascii=False),
    }
    data = " ".join(f'data-{key}="{esc(value, quote=True)}"' for key, value in attributes.items())
    tags = "".join(f'<span class="tag">{esc(topic)}</span>' for topic in event["topics"])
    return f"""<article class="event-card" id="event-{event['id']}" {data}>
  <div class="card-eyebrow"><span>{esc(event['partner'])}</span><span class="tag">{esc(event['format'])}</span></div>
  <h3>{esc(event['title'])}</h3>
  <p class="event-time"><time datetime="{esc(event['start'])}">{fallback_time(event['start_date'])}</time>
    to <time datetime="{esc(event['end'])}">{fallback_time(event['end_date'])}</time></p>
  <p class="event-location">{esc(event['location'])}</p>
  <p class="event-cost">Cost: {esc(event['cost'])}</p>
  <div class="event-description">{render_description(event['body'])}</div>
  <div class="tags" aria-label="Topics">{tags}</div>
  <a class="register" href="{esc(event['registration_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Register with {esc(event['partner'])}<span class="sr-only"> for {esc(event['title'])} (opens in a new tab)</span> &rarr;</a>
</article>"""


def update_page(content: str, events: list[dict]) -> str:
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("page must contain exactly one pair of partner event markers")
    start = content.index(START) + len(START)
    end = content.index(END)
    if start > end:
        raise ValueError("partner event markers are reversed")
    cards = "\n".join(render_event(event) for event in events)
    return content[:start] + "\n" + cards + "\n" + content[end:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail if generated cards are stale; do not write.")
    mode.add_argument("--validate-only", action="store_true", help="Validate Markdown only; do not write.")
    args = parser.parse_args()
    try:
        events = load_events()
        if args.validate_only:
            print(f"Validated {len(events)} partner event(s).")
            return 0
        content = PAGE.read_text(encoding="utf-8")
        updated = update_page(content, events)
        if updated == content:
            print(f"Partner events are up to date ({len(events)} event(s)).")
        elif args.check:
            print("Partner events page is stale. Run scripts/generate-partner-events.py.", file=sys.stderr)
            return 1
        else:
            PAGE.write_text(updated, encoding="utf-8", newline="\n")
            print(f"Published {len(events)} partner event(s) to {PAGE.relative_to(ROOT)}.")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Partner events error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
