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
python3 /Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/scripts/job_tool.py profile show
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
python3 /Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/scripts/job_tool.py search discover-ats --company "<Company Name>"
python3 /Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/scripts/job_tool.py search discover-workday --url "<career-page URL from Stage 1>" --company "<Company Name>"
python3 /Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/scripts/job_tool.py search discover-comeet --url "<career-page URL from Stage 1>" --company "<Company Name>"
```
Read `/Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/references/search-fallbacks.md` (in `job-search`'s directory —
read it from there, don't copy it) for the `confidence` contract: `"high"` means trust it,
`"low"` means a real board with zero current postings (not a miss), `"none"` means try the next
source.

### Stage 3 — One paid fallback, with confirmation

If all three of Stage 2 come back `confidence: "none"` for a company, **ask the user before
spending anything further**: `"[Company] isn't on any free source — want me to check the paid
jobs-index for it? (see job-search's README for cost)"`. If yes:
```bash
python3 /Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/scripts/job_tool.py search jobs-index --company "<Company Name>" --limit 25
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
python3 /Users/yoavsborovsky/GitHub/claude-code-tools/.worktrees/rnd-catalogue/tools/job-search/scripts/job_tool.py profile set '{"target_companies": [ ...existing entries unchanged..., {"name": "<Company>", "platform": "<platform>", "slug": "<slug>", "careers_url": "<url>"} ]}'
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
```
