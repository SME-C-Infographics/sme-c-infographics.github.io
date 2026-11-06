# Adding a Partner Event

The [partner events page](https://sme-c-infographics.github.io/events/partner-events.html)
lists **partner-hosted events for customers**. Each event comes from one Markdown
(`.md`) file in [`partner-events/`](../partner-events/). Add or edit a file through
a pull request; no HTML editing, command line, or local tools are required.

Prefer AI assistance? Use the
[copy-and-paste partner event agent instructions](partner-event-agent-instructions.md)
to prepare the file, create your fork, and open a PR from pasted event details.

## 1. Fork and copy the template

1. Fork this repository on GitHub (or **Sync fork** if you already have a fork).
2. Open [`partner-events/_template.md`](../partner-events/_template.md) and copy
   its raw contents.
3. In **your fork**, open `partner-events/`, choose **Add file > Create new file**
   (or **Upload files** if you have prepared the Markdown file).
4. Use a unique kebab-case filename such as
   `2026-12-10-contoso-azure-workshop.md`. Do not start it with `_`: files
   beginning with `_` are templates and are not published.
5. Paste the template and replace every example value, including the registration
   URL, with confirmed event details. Do not publish the template as a real event.

## 2. Fill in the event details

Keep the opening and closing `---` lines. The metadata between them is a small,
flat subset of YAML: one `field: value` per line. All ten fields are required.
Use plain text or quoted strings, not nested YAML, arrays, or multiline values.
Double-quoted values use JSON-style escaping; single quotes inside single-quoted
values are doubled (for example, `'Partner''s workshop'`). Inline YAML comments
are not supported; comment lines beginning with `#` are allowed.

| Field | What to enter |
|---|---|
| `title` | Customer-facing event title |
| `partner` | Hosting partner's organization name |
| `start` | Start date/time with an explicit UTC offset, such as `2026-12-10T10:00-06:00` |
| `end` | End date/time, later than `start`, in the same format |
| `format` | Exactly `Virtual`, `In person`, or `Hybrid` |
| `location` | `Online`, or the venue and city; for hybrid events include both |
| `registration_url` | Full `https://` registration URL, without embedded credentials |
| `cost` | `Free`, a price with currency, or a clear pricing description |
| `topics` | Comma-separated topics, such as `Azure, AI, Microsoft Fabric` |

Use the offset that applies **on the event date**, accounting for daylight saving
time. `Z` is also accepted for UTC, for example `2026-12-10T16:00Z`.
Times use 24-hour hours and minutes; do not include seconds. Different offsets on
`start` and `end` are supported for an event spanning a clock change.

Below the closing `---`, write a short description for customers: audience,
takeaways, and prerequisites. The page supports **plain-text paragraphs and
unordered lists** (lines beginning with `- ` or `* `). Other Markdown formatting
is displayed literally, and raw HTML is displayed as text, not executed.
The registration button is generated from `registration_url`.

Only share public event information. Do not include attendee lists, private
meeting links, access codes, or personal contact details.

## 3. Open a pull request

Commit the file to your fork, then choose **Contribute > Open pull request**.
Explain who is hosting and confirm that the event is intended for customers.
Submit only the Markdown event file; you do not need to update the HTML page.

The **Validate Partner Events** workflow checks filenames, required fields,
dates, formats, and registration URL syntax. Errors name the file and problem.
It also uploads a `partner-events-preview` artifact: download it from the
workflow run, unzip it, and open the HTML file to preview the listing. Fork PRs
receive the same validation without needing write permissions. A first-time
fork contributor may need a maintainer to approve the workflow run.

A maintainer reviews the public details and verifies the registration link
before merging. After merge, **Ensure Site Chrome** regenerates the page and
applies the site's normal chrome automatically. Allow time for that workflow
and GitHub Pages publishing to finish.

## Updating or removing a listing

Edit the same `.md` file in a new PR to correct details or change registration.
Delete that file through a PR to remove the listing. Use one file per event
occurrence; give separate dates their own files.

Upcoming and live events are shown by default. Once `end` has passed, an event
moves to the **Past events** view automatically in the browser; it is not deleted.
Past events appear newest first. Visitors can search, combine partner/format/topic
filters, use the format shortcuts in the hero, and filter by the event's starting
month in their own timezone. The hero counts summarize all submitted events and
partners, with a separate upcoming/live count; they do not change with filters.
With JavaScript disabled, all events remain readable with their original UTC
offsets.

## Maintainer reference

`events/partner-events.html` owns the layout and interaction. Only the region
between `<!-- smec-partner-events v1 -->` and `<!-- /smec-partner-events -->`
is generated. Do not hand-edit event cards; update their source Markdown instead.
The generator preserves all other HTML, including injected site-chrome markers.
No framework, package manager, YAML library, or site build system is needed.

Optional local commands (contributors are **not** required to run them):

```bash
python3 scripts/generate-partner-events.py --validate-only
python3 scripts/generate-partner-events.py
python3 scripts/generate-partner-events.py --check
python3 -m unittest discover -s scripts/tests -p "test_partner_events.py"
```

Generation is deterministic and idempotent. `--validate-only` never writes;
`--check` exits non-zero for invalid source or stale generated cards without
writing. Both the same-repo PR fixer and the post-merge chrome workflow generate
cards before applying site chrome. The post-merge workflow also handles
Markdown-only changes from forks.
