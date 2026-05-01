# Automated Page Updates — Exploration

> **Status:** spike on branch `explore/automated-page-updates`. Not yet merged.

This document is the living design record for an exploration into automating
updates of the HTML infographics in this repo. The goal is to layer more
automation on top of the existing **site chrome** scripts (`ensure-tracking.py`,
`ensure-back-button.py`, `generate-manifest.py`) so that content stays fresh,
links stay healthy, styling stays consistent, and bulk edits are safe — without
changing the fork-and-upload contributor flow described in
[adding-an-infographic-to-the-website.md](adding-an-infographic-to-the-website.md).

## Scope

In scope:

- **Inventory & audit** — a read-only report of what's on every page.
- **Freshness checks** — broken links, deprecated product names.
- **Chrome expansion** — `<meta>` description, Open Graph tags, favicon, a11y
  checks. Same idempotent, marker-based, `--check`-capable pattern as the
  existing scripts.
- **Agent-driven content refresh** — the audit JSON reports are turned
  into one GitHub issue per stale page, assigned to the Copilot coding
  agent, which opens a draft PR for human review. No third-party LLM
  secrets.
- **Bulk templating** — a generic idempotent "find block / replace block"
  helper for site-wide edits.

Out of scope (for this branch):

- Rewriting the CoWork authoring path.
- Adopting a static-site generator.
- Moving off GitHub Pages.
- Changing the fork-and-upload contributor flow.

## Design principles (ported from the existing chrome scripts)

Every script that modifies pages must:

1. Be **idempotent** — running twice in a row is a no-op on the second run.
2. Carry a **version marker** (e.g. `/* smec-meta v1 */`) so future schema
   bumps are detectable.
3. Support a **`--check` mode** that exits non-zero when a file is missing the
   expected state, without modifying anything. Matches
   [scripts/ensure-tracking.py](../scripts/ensure-tracking.py) and
   [scripts/ensure-back-button.py](../scripts/ensure-back-button.py).
4. **Skip redirect stubs** (pages with `<meta http-equiv="refresh">`) and the
   root `index.html` library landing page.
5. **Skip** the `.git`, `node_modules`, and `.github` directories.

Every read-only auditing/reporting script should emit machine-readable output
(JSON) so results can be diffed over time and surfaced as CI artifacts.

## Phased plan

- **Phase 1 — Discovery:** `scripts/audit-pages.py` produces an inventory JSON.
- **Phase 2 — Freshness:** `scripts/check-links.py`,
  `scripts/check-deprecated-terms.py`, `scripts/terminology.json`.
- **Phase 3 — Chrome expansion:** `scripts/ensure-meta.py`,
  `scripts/ensure-favicon.py`, `scripts/ensure-a11y.py`.
- **Phase 4 — Agent-driven content refresh:**
  `scripts/open-copilot-review-issues.py` + monthly scheduled workflow
  (`copilot-page-review.yml`) that turns audit findings into one
  GitHub issue per page and assigns the Copilot coding agent.
- **Phase 5 — Bulk templating:** `scripts/apply-template-change.py`.
- **Phase 6 — CI wiring:** extend `ensure-site-chrome.yml` and
  `fix-site-chrome-pr.yml`; add `audit-site.yml` (warn-only on PRs) and
  `copilot-page-review.yml` (monthly Copilot agent review).
- **Phase 7 — Docs:** finalize this document, update `README.md` pointers.

Findings from each phase are appended below as the spike progresses.

## Findings

### Baseline (before the spike)

- 11 published infographics across 9 category folders.
- Every page already had the Umami tracking snippet and the floating
  back button (existing chrome scripts).
- No page had: `<meta name="description">`, Open Graph tags, Twitter
  card tags, or a favicon link.
- No `<img>` tags in the corpus — imagery is inline SVG — so the image
  `alt` checker is dormant but wired in for future contributions.
- 53 distinct external links across the 11 pages. 1 was returning 404
  at the time of the first scan (`https://azure.microsoft.com/pricing/`
  referenced by `foundry/microsoft-ai-decision-guide.html`).
- 6 occurrences of the legacy phrase "Azure OpenAI Service" in one
  page; the terminology map treats this as `severity: low` and does not
  auto-rewrite by default (review recommended).

### What's automated now

| Script | Behavior | Idempotent marker |
|---|---|---|
| `scripts/audit-pages.py` | Read-only inventory of every page → `reports/audit.json` | n/a |
| `scripts/check-links.py` | HEAD/GET every external http(s) link → `reports/link-health.json` | n/a |
| `scripts/check-deprecated-terms.py` | Scan / optionally rewrite terms from `terminology.json` | n/a |
| `scripts/ensure-tracking.py` (existing) | Inject Umami analytics snippet | `data-website-id=...` |
| `scripts/ensure-back-button.py` (existing) | Inject floating back button | `data-smec-back-button="v1"` |
| `scripts/ensure-meta.py` | Inject description / OG / Twitter tags | `<!-- smec-meta v1 -->` |
| `scripts/ensure-favicon.py` | Inject favicon `<link>` pointing at `/favicon.svg` | `<!-- smec-favicon v1 -->` |
| `scripts/ensure-a11y.py` | Read-only a11y report → `reports/a11y.json` | n/a |
| `scripts/generate-manifest.py` (existing) | Regenerate `manifest.json` | n/a |
| `scripts/apply-template-change.py` | Idempotent bulk HTML edits from a JSON spec | `<!-- smec-tmpl:<id> -->` |
| `scripts/open-copilot-review-issues.py` | Turn audit JSON reports into per-page issue bodies for the Copilot coding agent | n/a |

### What's human-only (by design)

- Writing meaningful alt text for any future images.
- Reviewing, editing, and merging Copilot-authored freshness PRs.
  The agent opens the draft; a human is always the last step before
  anything lands on `main`.
- Deciding whether a deprecated-terms rule is safe to auto-apply (most
  rules ship at `severity: low` or `medium` and require review; the
  high-severity ones — Azure AD → Entra ID, Cognitive Services → Azure
  AI Services, Form Recognizer → Document Intelligence — are safe to
  `--apply` when they appear). Pages that legitimately need the legacy
  term (e.g. a decision guide explaining the rename) can wrap the
  occurrence inline with
  `<!-- smec-keep-term -->Azure OpenAI Service<!-- /smec-keep-term -->`
  to exempt it from both `--check` and `--apply`. Exempted matches are
  still surfaced in `reports/deprecated-terms.json` under a top-level
  `exempted` map so the bypass list stays auditable; unmatched
  open/close markers fail `--check`.
- Composing the content of any bulk-templating spec before applying it.

### Workflows

- `ensure-site-chrome.yml` (post-merge, main) — now runs tracking,
  back button, meta, favicon, and manifest in one sequential commit.
- `fix-site-chrome-pr.yml` (PR auto-fix, same-repo PRs only) — same
  sequence, commits into the PR branch.
- `audit-site.yml` (PR, warn-only) — runs the three checkers
  (`check-deprecated-terms`, `ensure-a11y`, `check-links`) with
  `continue-on-error: true` and uploads `reports/*.json` as an
  artifact. Not in the required-checks list; revisit once the
  false-positive rate is understood.
- `copilot-page-review.yml` (monthly schedule + manual) — runs the
  three auditors, then `open-copilot-review-issues.py` to build one
  markdown body per page with findings. For each page it opens an
  issue titled `Review <path>` (deduped against existing open issues)
  and assigns the Copilot coding agent via the GraphQL
  `replaceActorsForAssignable` mutation. Copilot then opens a draft
  PR per issue; humans review and merge. If the Copilot coding agent
  isn't enabled on the repo the issues are still created, unassigned,
  so a human can pick them up.

  **Token requirement for Copilot auto-start:** assignments made by
  `github-actions[bot]` (which is what `${{ secrets.GITHUB_TOKEN }}`
  authenticates as) do **not** trigger the Copilot coding agent to
  start work — same design reason `GITHUB_TOKEN` events don't cascade
  into other workflows. To actually kick off Copilot from this
  workflow, create a repo or org secret named `COPILOT_ASSIGN_TOKEN`
  containing a **fine-grained PAT** owned by a user who has Copilot
  access on this repo. Required scopes: `Issues: Read and write`,
  `Contents: Read`, `Metadata: Read`. Fine-grained is strongly
  preferred over a classic PAT (which would grant broad `repo` write).
  When the secret is absent the workflow still runs: it creates the
  issues and **intentionally leaves them unassigned**, emits a
  `core.warning`, and flags it in the step summary — rather than
  assigning under `GITHUB_TOKEN` and silently reproducing the exact
  bug this setup was meant to fix. A human can re-assign Copilot
  manually to unblock, or the PAT secret can be added.

### Outstanding decisions / follow-ups

1. Add an Open Graph image asset (`/og-default.png` or similar) and a
   matching injection rule in `ensure-meta.py` once a design exists.
2. Re-evaluate `audit-site.yml` after ~1 month: should any checker be
   promoted from `continue-on-error` to required?
3. Decide whether to auto-apply the high-severity terminology rules on
   post-merge (would need `check-deprecated-terms.py --apply` in
   `ensure-site-chrome.yml`; currently PR-only reporting).
4. Confirm the Copilot coding agent is enabled on the repo before the
   first scheduled run of `copilot-page-review.yml`, **and** create
   the `COPILOT_ASSIGN_TOKEN` secret (fine-grained PAT, `issues: write`
   + `contents: read` + `metadata: read`) — otherwise issues are
   created but Copilot does not auto-start on them.
5. Tune the per-page issue body in `open-copilot-review-issues.py`
   after the first real Copilot PR — especially the guardrails block,
   which is the agent's primary steering signal.
6. Consider adding a `copilot-review` label to the repo so the
   workflow can tag created issues (it falls back silently if the
   label is absent).
