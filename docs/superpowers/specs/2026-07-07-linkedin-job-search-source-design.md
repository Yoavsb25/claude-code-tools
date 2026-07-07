# LinkedIn Job Search Source — Design Spec
**Date:** 2026-07-07
**Status:** Approved

## Context

`tools/job-search`'s `job_tool.py` already searches Remotive, Arbeitnow, and direct company ATS
feeds (Greenhouse/Lever/Ashby) via `search <source>` subcommands — all keyless JSON APIs, no
scraping. LinkedIn coverage today comes only from `WebSearch`/`WebFetch` in SKILL.md's Stage 2b,
which is explicitly called out as unreliable: LinkedIn's own posting pages frequently return 403s
to automated fetches, so LinkedIn results are often scored from a WebSearch snippet alone.

Inspiration: `MadsLorentzen/ai-job-search`'s `linkedin-search` skill, a zero-dependency
TypeScript/Bun CLI that hits LinkedIn's public `jobs-guest` endpoints directly (no auth) with
regex-based HTML parsing and retry/backoff. This spec ports that approach into `job_tool.py`,
in stdlib Python, following the existing `search` subcommand conventions.

## Goals

- Add a `search linkedin` subcommand returning postings in the existing `posting()` shape, sourced
  from LinkedIn's public `jobs-guest` search endpoint — no auth, no new dependency.
- Add a `search linkedin-detail` subcommand to fetch a single posting's full description and
  criteria (seniority, employment type, job function, industries) — LinkedIn's search-card HTML
  never includes a description, unlike the other three sources.
- Fix the specific reliability gap in SKILL.md Stage 2b: enrichment via `WebFetch` on a
  `linkedin.com/jobs/view/...` URL should use `linkedin-detail` instead.
- Match the existing error-handling contract: a fetch failure becomes an `"error"` string with
  empty results, never a stack trace or an aborted run.

## Non-Goals

- Replacing Stage 2b's `site:linkedin.com/jobs` WebSearch queries — those stay as a fallback net
  alongside the new native source (some coverage may not appear in the guest search endpoint).
- Any other job portal (Danish or otherwise) from the reference repo — out of scope.
- Automated tests for `job_tool.py` — the tool has none today for any source; this follows the
  same live-usage validation pattern as remotive/arbeitnow/ats.
- Login/authenticated LinkedIn access of any kind.

## Architecture

Two new subcommands in the existing `search` subparser group, alongside `remotive`/`arbeitnow`/`ats`:

```
search linkedin --query Q --location L [--jobage N] [--remote remote|hybrid|onsite]
                 [--page N] [--limit N]
  → http_get_html_backoff(SEARCH_URL + querystring)
  → parse_job_cards(html)          # chunked regex parse, one bad card can't break the rest
  → maps each card into posting()  # source="linkedin", description=None (cards have none)
  → print_search_result(...)       # same {"source","error","results"} contract as today

search linkedin-detail --id ID_OR_URL [--limit-desc-chars N]
  → normalize_job_id(input)        # raw id | jobs/view/<id> URL | urn:li:jobPosting:<id>
  → http_get_html_backoff(DETAIL_URL/id)
  → parse_job_detail(html)         # regex parse: description, seniority, employment type,
                                    # job function, industries, apply URL
  → print_detail_result(...)       # new helper: {"source","error","result"} — singular, not a list
```

`linkedin`'s search results reuse the existing `posting()` fields exactly
(`source, title, company, location, remote, url, tags, salary, posted_date, description`) so all
four sources stay interchangeable for Stage 3 dedupe/scoring. The job ID needed for
`linkedin-detail` is parsed straight out of the `url` a search result already contains — no new
field is added to `posting()`.

## Fetching & Parsing

**`http_get_html_backoff(url)`** — new function, separate from the existing `http_get_json`
(which stays untouched for the other three sources). Sends:
- User-Agent: a standard desktop browser string (LinkedIn's guest endpoint is sensitive to
  looking like a normal browser AJAX request)
- Headers: `Accept`, `Accept-Language`, `X-Requested-With: XMLHttpRequest`

Retry/backoff on HTTP 429 or 5xx: up to 6 retries, starting at 500ms delay, doubling each retry
capped at 8s, plus 0–500ms random jitter. A 404 returns `("", None)` (treated as "not found," not
an error). Any other non-2xx or network failure returns `(None, "<reason>")`, matching
`http_get_json`'s existing `(data, err)` tuple convention so both search commands share one
error-handling path.

**`parse_job_cards(html)`** — splits the response on `data-entity-urn="urn:li:jobPosting:` and
parses each resulting chunk independently via regex: id, title (from the card's `<h3>` title or
its `sr-only` fallback span), company + company URL (from the subtitle `<h4>`), location, and
posted date (`datetime` attribute). A malformed chunk is skipped, not fatal to the batch.

**`parse_job_detail(html)`** — regex-extracts title, company (+ URL), location, the full
description (converting `<br>` and block-tag closes to newlines *before* stripping tags, so
paragraph structure survives), the job-criteria block (seniority / employment type / job function
/ industries via label→value pairs), and the apply URL.

**HTML entity decoding** — small helper for named entities (`&amp;`, `&lt;`, etc.) plus numeric
and hex character references (`&#233;`, `&#xE9;`) — titles and company names routinely contain
these.

## CLI Flags

`search linkedin`:
| Flag | Notes |
|---|---|
| `--query` | Keyword search |
| `--location` | **Required** — LinkedIn's endpoint needs it; maps 1:1 to profile's `locations` entries |
| `--jobage <days>` | Maps to `f_TPR=r{days*86400}` |
| `--remote {remote,hybrid,onsite}` | Maps to `f_WT` (2/3/1) |
| `--page <n>` | 1-indexed; offset = `(page-1)*10` |
| `--limit <n>` | Client-side cap, default 25 |

`search linkedin-detail`:
| Flag | Notes |
|---|---|
| `--id` | Required. Accepts a raw numeric ID, a `jobs/view/<id>` URL, or a `urn:li:jobPosting:<id>` URN |

## Legal / Personal-Use Notice

Automated access to LinkedIn's public pages is against its Terms of Service. Both the module
docstring in `job_tool.py` and the SKILL.md addition carry the same warning as the reference
repo: personal use only, keep query volume low, no bulk or commercial use.

## SKILL.md Changes

- **Stage 2a** (structured search, always run first) gains a new call, run once per
  (role × location) pair from the resolved criteria, in parallel with the existing
  remotive/arbeitnow/ats calls:
  ```bash
  python3 ~/.claude/skills/job-search/scripts/job_tool.py search linkedin --query "<role keyword>" --location "<location>" --limit 25
  ```
- **Stage 2b** keeps its `site:linkedin.com/jobs` WebSearch queries unchanged (fallback net,
  runs alongside the native source per the Non-Goals above).
- **Stage 2b enrichment** updated: for any result whose URL is a `linkedin.com/jobs/view/...`
  link, use `search linkedin-detail --id <url>` instead of `WebFetch` — replaces the specific
  unreliable step (LinkedIn 403s on WebFetch) with the native endpoint.
- **Stage 4**'s "Searched:" summary line adds `LinkedIn (native)` alongside the existing
  `LinkedIn (WebSearch)` mention.
- **Key rules** gains one line: LinkedIn access is personal-use-only per its ToS — keep query
  volume low, no bulk/commercial use.

## Testing

`job_tool.py` has no unit-test harness for any of its four sources today — all are validated by
live usage. This addition follows the same pattern: a manual smoke test running `search linkedin`
with a real query/location (confirming non-null title/company/url on real results) and
`linkedin-detail` on one of those result URLs (confirming a clean, readable description with no
leftover HTML tags or unescaped entities). No pytest baseline applies to this tool.
