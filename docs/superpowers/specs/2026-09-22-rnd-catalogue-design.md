# rnd-catalogue — design spec

Date: 2026-09-22
Status: approved by Yoav, pending implementation plan

## Problem

`job-search` discovers roles via keyword search (Remotive, Arbeitnow, LinkedIn, ad hoc ATS
queries). Yoav also keeps a watchlist of 50 companies he already likes
(`profile.json`'s `target_companies`) and wants a different question answered for those:
**"what does this company's whole R&D org currently have open?"** — not filtered by a search
keyword, not scored, just a complete inventory to skim.

`job_tool.py`'s `search ats` / `search workday-jobs` / `search comeet-jobs` already support
fetching a company's entire board (`--query` is optional) — this is a new orchestration and
presentation layer on top of existing fetch capability, not new scraping.

## Company coverage today (2026-09-22 snapshot)

Of 50 `target_companies`:
- **21 resolved** — `platform` + `slug` already stored, fetchable today.
- **20 unresolved** — no `platform` at all (e.g. Wix, Monday.com, Meta, Uber, Revolut, Oracle,
  Sony, DAZN, Formula 1, Cisco).
- **9 `other`** — known custom career site, no keyless API (Google, Apple, Microsoft,
  Salesforce, OpenAI, Dell, ServiceNow, Elbit Systems, Amdocs).

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Boundary vs. job-search | Pure inventory — no fit scoring, no tracker writes. job-search unchanged. |
| R&D scope | Engineering + Product + Data titles (not just Engineering; not whatever the company's own dept taxonomy says). |
| Location | London + remote-UK only (matches profile's `locations`). |
| Cadence | Living catalogue with diffing — persisted state, new/closed detection across runs, not just a fresh snapshot every time. |
| Coverage strategy | **Option A** — resolve ATS platforms once via a setup mode, then every catalogue run is pure structured-API reads. No inline discovery mixed into the daily run. |

## Architecture

New sibling skill: `~/.claude/skills/rnd-catalogue/`. Two modes, one skill:

- **Setup mode** — run once, and again whenever companies are added to the watchlist or a
  previously-unresolved company's board becomes discoverable.
- **Catalogue mode** — the recurring inventory run.

No new HTTP-fetching code. All fetching continues to live solely in job-search's
`job_tool.py`, invoked as a subprocess exactly the way job-search's own SKILL.md instructs the
agent to call it. `job_tool.py` stays the single source of truth for ATS/Workday/Comeet
request-and-parse logic; rnd-catalogue only adds orchestration (in its SKILL.md, followed by
the agent) and one small new state-owning script for what job_tool.py doesn't already model.

### File layout

```
~/.claude/skills/rnd-catalogue/
  SKILL.md
  README.md
  references/
    rnd-titles.md          # Engineering/Product/Data title keyword list + exclude list
  scripts/
    catalogue_store.py     # stdlib-only; owns catalogue.json (diff + persist), unittest-tested
    test_catalogue_store.py

~/Desktop/Job-Search/rnd-catalogue/
  catalogue.json            # canonical state: open + recently-closed postings, first/last_seen
  <date>-catalogue.md        # dated snapshot per run, same pattern as job-search's searches/
```

`references/search-fallbacks.md` is **not** copied — rnd-catalogue's setup mode reads it
directly from job-search's directory (`~/.claude/skills/job-search/references/search-fallbacks.md`)
so the ATS-discovery contract and large-enterprise custom-site pattern table stay single-sourced.

## Setup mode

1. `job_tool.py profile show` → partition `target_companies` into resolved / unresolved / `other`.
2. For each unresolved company: `search discover-ats` → `search discover-workday` →
   `search discover-comeet`, same fallback order and `confidence` contract job-search's Stage
   2a already documents.
3. On a hit: read current `target_companies` fresh, splice in the resolved
   `platform`/`slug`, write back the **full array** via `profile set` (array fields overwrite,
   not merge — same hazard job-search's Key Rules documents; restated here since both skills
   touch this field).
4. Anything still unresolved after all three discovery attempts, and anything tagged `other`,
   is reported and excluded from the catalogue. **No WebFetch/scraping fallback** — that's
   job-search's Stage 2b territory and deliberately out of scope here; rnd-catalogue only ever
   reads structured APIs.
5. Report: "N resolved this run, M already resolved, K excluded (no API) — [names]."

## Catalogue mode

1. Load profile; use only resolved `target_companies` entries. Note skipped
   unresolved/`other` entries in the summary rather than silently omitting them.
2. Fetch every resolved company's full board in parallel, no `--query`, `--limit 500`:
   - `search ats --platform <p> --company <slug>`
   - `search workday-jobs --slug <slug> --company <name> --location "London"` (location is a
     pagination hint that biases Workday's 150-job scan budget toward relevant postings — see
     `fetch_workday_postings`'s `location_hint` behavior — not a guarantee, so results still
     need the location filter in step 3)
   - `search comeet-jobs --slug <slug> --company <name>`
3. Client-side filtering (job_tool.py's `search ats` has no location parameter, so this step
   lives here, not in job_tool.py):
   - **Location**: London or remote-UK-eligible, judged from each posting's location/remote
     fields.
   - **R&D scope**: title matched against `references/rnd-titles.md`'s Engineering/Product/Data
     keyword list. Where a `departments`/`categories` field is present (Greenhouse/Lever expose
     this), use it as a corroborating signal — exclude a title match sitting in an obviously
     non-R&D department (Sales, Marketing, HR, Finance, Legal, Customer Success) rather than
     auto-including on title alone.
4. Diff against stored state via `catalogue_store.py`: pass this run's full filtered posting
   list, get back `{new: [...], closed: [...], unchanged_count}`. The script persists the
   merged `catalogue.json` — new rows get `first_seen`, existing rows get `last_seen` bumped,
   rows missing from this run get `closed_date` set (not deleted). Rows closed 30+ days are
   pruned on the next run.
5. Present grouped-by-company markdown tables (role, location, first-seen/posted, link, 🆕 for
   new-this-run) plus a "closed since last run" note per company. **No fit score, no salary, no
   Skills Fit column** — pure inventory per the approved boundary.
6. Save the run's markdown to `~/Desktop/Job-Search/rnd-catalogue/<date>-catalogue.md`.
7. Close with a pointer, not an automatic handoff: "Want any of these scored or tailored? Hand
   them to job-search or resume-tailor directly." No skill invocation happens automatically.

## Data model — `catalogue.json`

```json
{
  "postings": {
    "<platform>:<company-slug>:<posting-id-or-url>": {
      "company": "Acme Corp",
      "title": "Staff Backend Engineer",
      "location": "London",
      "link": "https://...",
      "first_seen": "2026-09-22",
      "last_seen": "2026-09-22",
      "closed_date": null
    }
  }
}
```

`catalogue_store.py` exposes (mirroring `job_tool.py`'s ownership pattern for `tracker.json`):
- `diff-and-save` — stdin/arg JSON of this run's posting list → prints `{new, closed,
  unchanged_count}`, writes updated `catalogue.json`.
- Pruning of 30+-day-closed rows happens inside `diff-and-save`, not a separate command.

**Never hand-edit `catalogue.json`** — same rule as `tracker.json`/`profile.json`.

## Error handling

Same contract as job-search: every `job_tool.py search` call degrades to
`{"error": "...", "results": []}`, never raises. A single company/source failing is noted in
the coverage summary and never blocks the rest of the run.

## Testing

`scripts/test_catalogue_store.py`, stdlib `unittest` (this environment has no `pytest`; run via
`python3 -m unittest`), matching `job-search/scripts/test_job_tool.py`'s convention. Covers:
new/closed/unchanged detection, `first_seen`/`last_seen` bookkeeping, `closed_date` set on
disappearance, pruning of rows closed 30+ days.

## Explicitly out of scope

- Fit/skills scoring of any kind.
- Writing to `tracker.json`.
- Any WebFetch/scraping fallback for companies with no keyless API.
- Automatic handoff into job-search or resume-tailor.

## Environment note

This project directory and `~/.claude` are not usable git repositories in this environment
(`git` fails here due to an unresolved Xcode license agreement) — this spec is saved to disk
only, not committed.
