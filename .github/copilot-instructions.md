# Copilot Instructions — SME&C Infographics

Static GitHub Pages site (no build step, no framework, no package manager). Each
infographic is a **fully self-contained HTML file** with inline CSS / SVG / JS,
dropped into a category folder at the repo root (`azure-databases/`, `fabric/`,
`foundry/`, `github-copilot/`, `avd/`, `app-platform-services/`,
`defender-for-cloud/`, `azure-sql/`, `events/`, `infrastructure/`).
`index.html` is the library landing page; `manifest.json` is the generated
catalog it reads from.

## Architecture: site chrome is automated, not hand-edited

Per-page chrome (analytics, floating back button, SEO/OG meta block, favicon,
manifest entry) is **injected by Python scripts in `scripts/`**, not by the
contributor. Don't hand-edit these blocks in HTML files — re-run the relevant
script instead.

Every chrome script follows the same contract (see
`docs/automated-page-updates.md`):

1. **Idempotent** — running twice is a no-op the second time.
2. Carries a **version marker** the script greps for to detect prior injections,
   e.g. `<!-- smec-meta v1 -->`, `<!-- smec-favicon v1 -->`,
   `data-smec-back-button="v1"`, `data-website-id=<umami-id>`,
   `<!-- smec-tmpl:<id> -->` for bulk templating.
3. Supports `--check` (exits non-zero if any file is missing the expected
   state, modifies nothing) — this is what CI calls.
4. **Skips** redirect stubs (`<meta http-equiv="refresh">`), the root
   `index.html`, and the `.git`, `node_modules`, `.github` directories.

When adding a new chrome script, mirror this contract or it will not fit the
existing CI wiring (`ensure-site-chrome.yml`, `fix-site-chrome-pr.yml`,
`audit-site.yml`).

Read-only auditors (`audit-pages.py`, `check-links.py`,
`check-deprecated-terms.py`, `ensure-a11y.py`, `check-accuracy-staleness.py`)
emit JSON / Markdown into `reports/` so results can be diffed and uploaded as
CI artifacts.

## Common commands

```bash
# Apply all site chrome locally (what post-merge CI runs)
python3 scripts/ensure-tracking.py
python3 scripts/ensure-back-button.py
python3 scripts/ensure-meta.py
python3 scripts/ensure-favicon.py
python3 scripts/generate-manifest.py

# Verify a single chrome rule without modifying anything (CI-equivalent)
python3 scripts/ensure-meta.py --check

# Run an auditor (writes JSON under reports/)
python3 scripts/audit-pages.py
python3 scripts/check-links.py
python3 scripts/check-deprecated-terms.py            # report only
python3 scripts/check-deprecated-terms.py --apply    # rewrite (review first!)
python3 scripts/ensure-a11y.py
python3 scripts/check-accuracy-staleness.py --max-age-days 28

# Bulk HTML edits via a JSON spec (see scripts/specs/example.json)
python3 scripts/apply-template-change.py scripts/specs/<spec>.json
```

There is no test suite, linter, or package manifest. The site has no build
step — opening any `.html` file in a browser is the local preview.

## Key conventions

- **New infographic = new HTML file** in the matching category folder, kebab-
  case filename (e.g. `sql-migration-guide.html`), fully self-contained (no
  external CSS / JS / image refs). The manifest, meta, favicon, tracking, and
  back button are all added automatically post-merge — do not pre-populate them
  in the PR.
- **Don't add `<meta name="description">`, OG tags, favicon `<link>`, the Umami
  script, or the floating back button manually.** The `ensure-*` scripts own
  those regions and will refuse to touch already-marked blocks. Hand-written
  versions without the marker can cause double-injection.
- **Terminology rules** live in `scripts/terminology.json` with a `severity`
  field. `high` (e.g. Azure AD → Entra ID, Cognitive Services → Azure AI
  Services, Form Recognizer → Document Intelligence) is safe to `--apply`;
  `low` / `medium` are report-only by default and need human review.
- **Page freshness** is tracked via a `smec:last-accuracy-check` meta tag
  stamped by `scripts/stamp-accuracy-date.py`. The weekly accuracy-review
  workflow flags pages older than 28 days.
- **Redirect stubs** (pages whose entire job is `<meta http-equiv="refresh">`)
  are intentionally excluded from every chrome script — preserve that pattern
  if you add one.
- **Don't depend on a static-site generator, framework, or package manager.**
  Plain HTML + Python stdlib scripts is a deliberate constraint
  (`docs/automated-page-updates.md`, "Out of scope").

## Workflows / Copilot agent integration

- `ensure-site-chrome.yml` — post-merge on `main`, runs all `ensure-*` scripts +
  `generate-manifest.py` in one sequential commit (avoids push races).
- `fix-site-chrome-pr.yml` — same sequence on same-repo PRs, commits into the
  PR branch.
- `audit-site.yml` — PR, `continue-on-error: true`, uploads `reports/*.json` as
  an artifact. Not a required check.
- `copilot-page-review.yml` (monthly) and `accuracy-review.yml` (weekly,
  Thursdays) — turn audit JSON into one issue per stale page and assign the
  Copilot coding agent.

**Important:** assignments made under `GITHUB_TOKEN` (i.e.
`github-actions[bot]`) do **not** start the Copilot coding agent. These two
workflows look for a `COPILOT_ASSIGN_TOKEN` secret (fine-grained PAT with
`issues: write`, `contents: read`, `metadata: read`) and, if absent,
**intentionally leave issues unassigned** rather than silently failing to
trigger the agent. Don't "fix" this by falling back to `GITHUB_TOKEN` for the
assignment step.

The two review workflows cross-deduplicate by label (`accuracy-review`,
`copilot-review`) and by an HTML marker comment in the issue body
(`<!-- copilot-accuracy-review v1 -->`, `<!-- copilot-page-review v1 -->`,
plus `<!-- page: <path> -->`). Preserve those markers if you edit the
generators.

## Contributor flow (don't break this)

The published contributor path is **fork → upload HTML through the GitHub web
UI → open PR** (`docs/adding-an-infographic-to-the-website.md`). No CLI
required. Changes that would force contributors to clone, run scripts, or
install tooling locally are out of scope for this repo.
