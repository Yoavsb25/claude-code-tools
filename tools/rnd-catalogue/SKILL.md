---
name: rnd-catalogue
description: >
  Builds and maintains a running inventory of every open R&D role (Engineering, Product, Data) at
  Yoav's watchlisted companies (profile.json's target_companies, shared with job-search) in London
  or remote-UK — grouped by company, flagged for what's new or closed since the last run. Pure
  inventory: no fit scoring, no tracker writes. Use this whenever Yoav wants to see what a company
  he likes actually has open right now, rather than searching by keyword — e.g. "what's open at my
  target companies", "check my watchlist for R&D roles", "catalogue my companies", "what does
  NVIDIA have open", "resolve the ATS platforms for my watchlist" (setup mode), or "run the R&D
  catalogue". If he wants roles scored against his profile or wants to apply, hand the ones he
  likes to job-search or resume-tailor directly — this skill only inventories, it never scores or
  tracks.
---

# R&D Catalogue

You are building a browsable inventory of what Yoav's watchlisted companies (`target_companies`
in `profile.json`, shared with `job-search`) currently have open in Engineering, Product, and
Data — filtered to London/remote-UK, with no fit scoring and no tracker writes. That boundary is
deliberate: this skill answers "what does this company have open", `job-search` answers "what
should I apply to."

All fetching reuses `job-search`'s `scripts/job_tool.py` directly — this skill has no HTTP code
of its own. It owns exactly one small piece of state `job_tool.py` doesn't already model: the
open/closed posting catalogue, via `scripts/catalogue_store.py`. **Never hand-edit
`catalogue.json`** — same rule as `job-search`'s tracker/profile files.

This skill has two modes. Which one runs is decided by what the user asked for:

- **Setup mode** — resolves ATS platforms for watchlist companies that don't have one yet. Run
  it once, and again whenever new companies are added to the watchlist. Triggers: "resolve the
  ATS platforms", "set up the catalogue", "add X to my watchlist" (if X has no platform), or
  automatically the first time catalogue mode finds unresolved companies (see Catalogue mode
  Stage 0).
- **Catalogue mode** — the recurring inventory run. Triggers: "what's open at my target
  companies", "catalogue my companies", "run the R&D catalogue", "what does [watchlisted
  company] have open".

---

## Setup mode

### Stage 0 — Partition the watchlist

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile show
```

Read `target_companies`. Partition into:
- **Resolved** — has both `platform` and `slug`.
- **Unresolved** — has neither.
- **`other`** — `platform: "other"` (a known custom career site, confirmed not on any of the six
  ATS platforms or Workday/Comeet).

If everything is already resolved, say so and stop — nothing to do.

### Stage 1 — Find each unresolved company's career-page URL

`discover-workday` and `discover-comeet` both require a `--url` to scan (they read that page's
HTML for an embedded tenant link or widget config — `discover-ats` doesn't need this, it guesses
slugs directly from the company name). For each unresolved company, in order:

1. If the profile entry already has a `careers_url` (saved from a prior setup run), use it.
2. Otherwise try the obvious pattern first — `https://www.<company-domain-guess>.com/careers` —
   by just passing it straight to Stage 2's `discover-workday`/`discover-comeet` calls below; a
   wrong guess degrades to `confidence: "none"`/no error, it doesn't cost anything extra to try.
3. If the guess is clearly wrong (e.g. you don't know the company's domain at all) or both
   Stage 2 calls come back empty for it, run one `WebSearch` for `"<Company Name>" careers page`
   and take the top result's URL.

**This is the one WebSearch this mode allows, and it's finding a URL, not reading job listings**
— it never substitutes for the structured API calls in Stage 2, and this skill never falls
through to WebFetch/Playwright scraping of a custom career site the way `job-search`'s Stage 2b
does. That's an intentional, narrower boundary than `job-search` has.

Save whatever URL you end up using back to that company's `target_companies` entry as
`careers_url` (splice into the full array via `profile set`, same as Stage 4 below) even if
discovery ultimately misses — it saves the WebSearch on the next setup run.

### Stage 2 — Run the free structured-discovery sweep

For each unresolved company, run all three in parallel:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-ats --company "<Company Name>"
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-workday --url "<career-page URL from Stage 1>" --company "<Company Name>"
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-comeet --url "<career-page URL from Stage 1>" --company "<Company Name>"
```
Read `~/.claude/skills/job-search/references/search-fallbacks.md` (in `job-search`'s directory —
read it from there, don't copy it) for the `confidence` contract: `"high"` means trust it,
`"low"` means a real board with zero current postings (not a miss), `"none"` means try the next
source.

### Stage 3 — One paid fallback, with confirmation

If all three of Stage 2 come back `confidence: "none"` for a company, **ask the user before
spending anything further**: `"[Company] isn't on any free source — want me to check the paid
jobs-index for it? (see job-search's README for cost)"`. If yes:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search jobs-index --company "<Company Name>" --limit 25
```
This is still a structured API, not scraping — it's `job-search`'s own paid fallback, reused
here rather than reimplemented. If the user declines, or this also misses, the company is
excluded from the catalogue (see Stage 5) — don't fall through to WebFetch/Playwright.

### Stage 4 — Persist every hit

For every company Stage 2 or 3 resolved, read the current `target_companies` fresh, splice in
`platform`/`slug` (and `careers_url` from Stage 1) by matching `name` case-insensitively, and
write back the **full array** — `profile set` replaces `target_companies` wholesale, it does not
merge:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile set '{"target_companies": [ ...existing entries unchanged..., {"name": "<Company>", "platform": "<platform>", "slug": "<slug>", "careers_url": "<url>"} ]}'
```

### Stage 5 — Report coverage

```
## 🔧 R&D Catalogue — setup
Resolved this run: N — [Company (platform)], ...
Already resolved: M
Excluded — no API found: K — [Company], ... (career page: <url> if found, for manual reference)
```
End with: **"Run the catalogue now?"** if any companies are resolved and this wasn't triggered
automatically from catalogue mode's Stage 0.

---

## Catalogue mode

### Stage 0 — Load state

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile show
python3 ~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py list
```
Use only resolved `target_companies` entries (has `platform` + `slug`). If any are unresolved
and setup mode hasn't been run yet, mention it in the closing summary and offer to run setup
mode — but proceed with whatever's already resolved rather than blocking the whole run on it.

If the user's request names one specific watchlisted company (e.g. "what does NVIDIA have
open"), this is still Catalogue mode, just scoped to that company: restrict Stage 1's fetch to
just that company's `target_companies` entry, and in Stage 4 use
`catalogue_store.py list --company "<name>"` instead of the bare `list` call, so the presented
table only covers that one company. With no company named, proceed as below and sweep the whole
watchlist.

### Stage 1 — Fetch every resolved company's full board

No `--query` on any of these — that's what makes it a whole-board fetch instead of a keyword
search. Run all companies in parallel:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search ats --platform <platform> --company <slug> --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search workday-jobs --slug <slug> --company "<name>" --location-hint "United Kingdom" --job-family-groups "Engineering,R&D,Research,Research & Development,Product,Product Management,Data,Data Science,Data & Analytics,AI,AI/ML,Machine Learning,Software Engineering,Hardware Engineering" --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search comeet-jobs --slug <slug> --company "<name>" --limit 500
```
`--job-family-groups` is `references/rnd-departments.md`'s Include list, verbatim, comma-joined —
this filters Workday's own index to R&D-category postings server-side, before any detail fetch
happens. `--location-hint` now resolves to an exact facet match (not the old fuzzy text guess),
so it's both cheap and reliable — always pass both for `workday-jobs`, they're harmless on small
boards and dramatically narrow large ones (a category+location-filtered query returns a handful
to a few dozen results even for a 2,000-posting board, well under any detail-fetch budget
concern).

A company whose call returns a non-null `error` is skipped for this run, not treated as "zero
postings" — note it in the Stage 4 summary and make sure it's **excluded** from the
`--companies` list passed to Stage 3, so `catalogue_store.py` doesn't wrongly mark its previously
open postings as closed just because this run couldn't reach it.

### Stage 2 — Filter to London/remote-UK, R&D department (title as fallback only)

For every posting from Stage 1:
- **Location**: keep if it's London, or marked/tagged remote in a way that includes the UK
  (judge from `location`/`remote`/`tags` — same holistic judgment `job-search` already applies,
  no separate script for this). For Workday postings already fetched with `--job-family-groups`,
  this is still needed — the category filter doesn't replace the location judgment, since a
  posting can list the UK as one of several eligible sites without the compact text saying so
  plainly (see the multi-location note in `job_tool.py`'s own `fetch_workday_postings`
  docstring).
- **R&D scope — department first**: if the posting's `tags` has a usable value (not empty, not a
  company-specific label that means nothing on its own — see `references/rnd-departments.md`'s
  "Fallback trigger" section), match it against that file's Include/Exclude lists and stop there.
  **Do not also check the title for these** — a department match is decisive on its own,
  Workday's own categorization has been directly verified to catch cases (pre-sales-flavored
  "Solutions Architect" titles) that title-matching alone got wrong.
- **R&D scope — title fallback**: only when `tags` is empty or generic, fall through to
  `references/rnd-titles.md`'s title-matching (unchanged from before this change).
- **Workday postings specifically**: since Stage 1 already fetched with `--job-family-groups` set
  to the Include list, every returned posting is *by construction* already in an Include
  department — there's no `tags` data to double-check against (Workday postings still come back
  with empty `tags`, see `job_tool.py`'s Workday integration), so treat a Workday posting from
  this fetch as already department-matched; only the location judgment above still applies to it.
  **One caveat**: `--job-family-groups` degrades silently if none of the Include list's names
  match that tenant's actual category facet (a real possibility — Workday descriptors vary, e.g.
  a tenant might use "Engineering & Technology" instead of "Engineering") — in that case Workday
  returns its *entire* unfiltered board, not an empty one, and every posting in it would be
  wrongly treated as department-matched by the rule above. If a Workday company's fetch returns
  an implausibly large or obviously non-R&D-heavy set of postings (e.g. mostly Sales/Retail
  titles), treat that as a signal the facet didn't resolve for this tenant and fall back to
  `references/rnd-titles.md`'s title-matching for that company instead of trusting the
  department-matched assumption.

Before building the filtered array to pass into Stage 3, normalize every posting's `company`
field to the matching `target_companies` entry's `name` — not whatever `job_tool.py search`
returned. `search ats` in particular echoes back the ATS **slug** (e.g. `"monzo"`), not the
display name (`"Monzo"`); since Stage 3's `--companies` list is built from `name`, leaving the
slug in place means `catalogue_store.py` can never match that posting to a queried company, so it
silently never gets marked closed.

### Stage 3 — Diff and persist

```bash
python3 ~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py diff-and-save '<JSON array of Stage 2's filtered postings>' --companies "<comma-separated names of companies actually queried successfully in Stage 1>"
```
Each posting object needs at least `company`, `title`, `location`, `url`. The script returns
`{"new": [...], "closed": [...], "unchanged_count": N, "pruned_count": N}` and persists the
merged `catalogue.json` — this is the only thing that writes that file.

### Stage 4 — Present, grouped by company

```bash
python3 ~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py list
```
Build one table per company from this (now-updated) open list, flagging 🆕 next to any row whose
`key` was in Stage 3's `new` output. Below the tables, a short "closed since last run" list from
Stage 3's `closed` output, grouped by company.

```
## 🗂️ R&D Catalogue — [date]

Checked N companies ([list]). Skipped: [unresolved companies, or "none"]. Errors: [companies
whose fetch failed this run, or "none"].

### Acme Corp
| Role | Location | First seen | Link |
|---|---|---|---|
| 🆕 Staff Backend Engineer | London | 2026-09-22 | [Apply →](url) |
| Platform Engineer | Remote UK | 2026-09-01 | [Apply →](url) |

**Closed since last run:** Widgets Inc — Senior Data Engineer
```
No fit score, no salary column, no Skills Fit column — pure inventory.

### Stage 5 — Save the snapshot

Write the exact markdown from Stage 4 to
`~/Desktop/Job-Search/rnd-catalogue/<date>-catalogue.md` (create the `rnd-catalogue/` directory
first if needed). Re-running the same day overwrites that day's file, same convention as
`job-search`'s `searches/` directory.

### Stage 6 — Hand off, don't chain

Close with: **"Want any of these scored or a resume tailored? Hand the ones you like to
job-search or resume-tailor directly."** Never invoke either automatically — the user decides
which rows are worth that next step.

---

## Key rules

- **`catalogue_store.py` owns `catalogue.json`.** Never hand-edit it — same reasoning as
  `job-search`'s tracker/profile files: state can't silently drift or lose rows across runs.
- **`job_tool.py` owns all fetching.** This skill never adds its own HTTP code — every posting
  comes from a `job_tool.py search` call, reused exactly as `job-search` calls it.
- **`target_companies` is shared state.** Setup mode's `profile set` calls follow the same
  splice-the-full-array discipline `job-search` documents — read fresh, splice, write back whole,
  never patch with just the delta.
- **No scraping fallback, ever.** If `discover-ats`/`discover-workday`/`discover-comeet`/
  `jobs-index` all miss, the company is excluded and reported — this skill never falls through to
  WebFetch/Playwright reading of a custom career site. That's `job-search`'s Stage 2b, deliberately
  out of scope here.
- **Pure inventory — no scoring, no tracker writes.** This skill never calls `tracker upsert` and
  never computes a fit score. If the user wants either, point them at `job-search`.
- **A company that errors this run is excluded from Stage 3's `--companies` list**, not treated
  as having zero postings — otherwise its real open postings would get wrongly marked closed.
