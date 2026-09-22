# rnd-catalogue

Builds a running inventory of every open Engineering/Product/Data role, in London or remote-UK,
at the companies on Yoav's watchlist (`job-search`'s `target_companies`) — grouped by company,
flagged for what's new or closed since the last run. Pure inventory: no fit scoring, no tracker
writes. For scored, trackable results, use `job-search` directly.

## How it works

1. **Setup mode** (run once, and again when companies are added) — resolves an ATS platform for
   every watchlist company that doesn't have one yet, via `job-search`'s own
   `discover-ats`/`discover-workday`/`discover-comeet` (and, with confirmation, the paid
   `jobs-index`), and saves the result back to the shared `target_companies` list.
2. **Catalogue mode** (the recurring run) — fetches every resolved company's *entire* current
   board (no keyword filter), keeps only London/remote-UK postings in Engineering, Product, or
   Data (see `references/rnd-titles.md`), diffs against the last run's snapshot, and presents one
   table per company with new postings flagged and closed ones noted.

## Bookkeeping script

`scripts/catalogue_store.py` is a stdlib-only Python script that owns one JSON file — it's the
only thing that should ever write it:

```bash
python3 scripts/catalogue_store.py diff-and-save '<JSON array of this run's postings>' --companies "Acme Corp,Widgets Inc"
python3 scripts/catalogue_store.py list [--company "Acme Corp"]
```

State lives in `~/Desktop/Job-Search/rnd-catalogue/` by default (override with `JOB_SEARCH_DIR`,
same env var `job-search` uses): `catalogue.json` (source of truth for open/closed postings) and
a dated `<date>-catalogue.md` snapshot per run. Postings missing from a run are marked
`closed_date` rather than deleted, and pruned after 30 days closed.

All fetching is done by `job-search`'s `scripts/job_tool.py` — this skill has no HTTP code of
its own and depends on `job-search` being installed alongside it
(`references/search-fallbacks.md` is read directly from `job-search`'s directory, not copied).

## Design spec

See `~/Desktop/Job-Search/docs/superpowers/specs/2026-09-22-rnd-catalogue-design.md` for the full
design rationale.

## Tests

```bash
cd scripts && python3 -m unittest test_catalogue_store -v
```
