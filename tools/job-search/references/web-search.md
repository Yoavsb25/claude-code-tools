# Stage 2b — WebSearch / WebFetch (broader net, especially for LinkedIn)

Read from SKILL.md Stage 2b. Runs alongside Stage 2a's structured search.

Run `WebSearch` queries built from the resolved criteria, varying phrasing. Prefer patterns that
resolve to individual posting pages over generic phrasing that tends to surface aggregator
listing/landing pages (Glassdoor "N jobs in..." pages, Totaljobs category pages) — those cost a
query without returning a scoreable result:
- `site:linkedin.com/jobs [role] [location]`
- `site:linkedin.com/jobs "[role]" remote`
- `"[role]" hiring [location] 2026`
- Plain-language query combining role + location + must-haves, e.g. `Staff Backend Engineer
  remote Kubernetes hiring`

**If `skills` is set**, add exactly one additional query per role blending the role title with the
top 2–3 skills, e.g. `Software Engineer React Node CI/CD hiring London` — additive to the queries
above, not a replacement. Bounded to one extra query per role, not one per skill, to keep volume
in check.

**If `industries_prefer` is set**, add targeted queries per industry, e.g. `[role] fintech
[location] hiring`.

**Proactive company discovery.** Don't only check companies the user already named. Run
`WebSearch` queries aimed at surfacing companies matching the profile, not just individual
postings — aggregator/listicle results here are expected and fine, since only company names get
extracted from them, unlike the per-role queries above where an aggregator hit is a wasted query:
- `"who is hiring" [role] [industries_prefer] 2026`
- `best [industries_prefer] companies to work for [locations] 2026`
- `[industries_prefer] startups hiring [role]`

Pull candidate company names out of these results, plus the `company` field of any
Remotive/Arbeitnow hits from 2a, that aren't already in `target_companies` or the Stage 0 tracker
list. Cap this at roughly the top 5 newly-surfaced companies per round — this widens the net, it
isn't meant to fan out into dozens of speculative lookups per search. For each candidate company,
run the auto-detect flow from 2a (`search discover-ats`, then `search discover-workday`) before
falling back to the direct career-page search below.

**Large-enterprise baseline check.** If `target_companies` has no large enterprises in it and none
have surfaced yet from the proactive discovery above, don't rely on WebSearch phrasing alone to
surface them — check a small number (3–5) of well-known large employers relevant to the resolved
role/industry as a guaranteed baseline part of every search round, via Stage 2b's direct
career-page search below. This is additional to, not carved out of, the proactive-discovery cap
above — a quiet discovery round doesn't consume this budget. It's a default baseline, not a
replacement for user-specified `target_companies`, which always take priority; it exists because
proactive-discovery WebSearch queries don't reliably surface big-company names on their own.

**Direct career-page search**, for companies with no ATS, Workday, Comeet, or `jobs-index` match —
i.e. every `platform: "other"` watchlist entry, and every large enterprise where `discover-ats`
(skipped per Stage 2a's rule), `discover-workday`/`discover-comeet` (tried per "Workday-hosted
companies specifically" below), and `search jobs-index` (see further below — try this before
falling all the way through to WebSearch/Playwright, it covers far more platforms than this
script's own dedicated integrations) all came back empty (e.g. Google, Salesforce — see the
pattern table). This is the last-resort path once every structured-data option is exhausted, not
the first thing to try. In addition to the `site:linkedin.com/jobs` queries above, search the
company's own site directly:
- `site:<company-domain> careers [role]`
- `"<company name>" careers [role] [location]`
- `"<company name>" jobs apply [role]`

If a result lands on the company's own `/careers` or `/jobs` page, `WebFetch` it the same
optional-enrichment way as any other posting page (see below) — it's often a listing page rather
than a single JD, so pull out whichever open roles are visible and score them against the profile.
If `WebFetch` fails or 403s, don't drop the company — note it and rely on the LinkedIn/aggregator
angle for that company this round instead.

**Known large-enterprise career sites (verified patterns).** Don't spend a generic
"fetch-the-homepage" call on a large enterprise before checking whether it's already documented.
Read `references/search-fallbacks.md` (§ "Known large-enterprise career-site patterns") for
verified listing-page URLs and per-company notes (Unity, NVIDIA, Google, Microsoft, Salesforce,
Palo Alto Networks, Amdocs so far) — a homepage fetch (via `WebFetch` or a generic
search-then-scrape tool) almost always lands on marketing content or an empty JS shell instead of
the actual job list, wasting a call. When you learn a new large enterprise's pattern this way
(a working filtered-listing URL, a confirmed Workday/ATS tenant, or a confirmed "custom SPA, no
keyless route, use Playwright"), add it to that table so the next run doesn't rediscover it from
scratch.

**Checking a specific company: location-first, not title-first.** A `<company> + <one role title>`
query silently under-covers roles and misses postings when the company uses a different internal
title for the same job family (e.g. Google's "Customer Engineer" vs. "Solutions Engineer"). Also,
a company not in `target_companies` can be missed even with a great-fitting posting, since
market-wide role searches only return a capped, relevance-ranked slice of citywide results — if the
user asks about a specific posting that didn't come up, check whether its company was in
`target_companies` before diagnosing anything else. Read `references/search-fallbacks.md`
(§ "Checking a specific company") for the location-first method, known title synonyms, and a
documented reliability caveat about bare company-name queries before concluding a target/large
enterprise has nothing open.

**Workday-hosted companies specifically.** Try this *before* WebSearch/Playwright for any
target/discovered large enterprise, not just after one turns up a `myworkdayjobs.com` URL by
chance — Workday is the single most common ATS among large enterprises, and detecting it is a
free, keyless, one-shot check:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-workday --url "<company careers-page URL>" --company "<Company Name>" --query "<role keyword>"
```
- `--url` can be a guessed careers URL (`https://<company-domain>/careers`), one already surfaced
  by an earlier WebSearch this round, or (if you already know it) the company's
  `myworkdayjobs.com` URL directly — either form works, `discover-workday` detects which.
- `confidence: "high"` or `"low"` means it found a Workday tenant — treat the returned postings as
  a Stage 2a-equivalent direct-source result (same dedupe priority as `search ats`), and offer to
  save `platform: "workday"` / that `detected_slug` to `target_companies` so future rounds skip
  straight to `search workday-jobs` (no re-discovery HTML fetch needed).
- `confidence: "none"` means no Workday link was found in that page's HTML — not necessarily
  proof the company isn't Workday-hosted (the URL guess might be wrong, or the real link is only
  reachable after JS execution). Same idea for `discover-comeet` and its `COMEET.init(...)` widget
  config. Once both come back empty, try `search jobs-index` (below) before falling through to
  WebFetch/Playwright.

**Broad coverage for everything else: `search jobs-index` (paid, try before WebSearch/Playwright).**
A company matching none of the free discover-ats/discover-workday/discover-comeet paths is *not*
necessarily a dead end — those only cover a handful of platforms. `search jobs-index` queries a
pre-built index spanning 54 ATS platforms (Oracle Cloud, SuccessFactors, iCIMS, Phenom People, and
many more this script has no dedicated integration for), via structured filters instead of
free-text role-title guessing:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search jobs-index --company "<Company Name>" --location "<City, Region, Country>" --limit 25
```
- This requires `APIFY_TOKEN` and is a **paid** call (unlike every other source covered so far) —
  confirm target companies with the user before running it, same rule as the paid `search workday`
  Actor. It's cheap by design (`--limit` defaults to 25, costing well under $1 at Apify's free
  pricing tier — see `references/search-fallbacks.md` for exact numbers), but it's still real money, not a free keyless
  check.
- `--location` must be the exact `"City, Region/State, Country"` phrase format (English names, no
  abbreviations — e.g. `"London, England, United Kingdom"`, not `"London, UK"`) — a mismatched
  format silently returns zero rows rather than erroring, so don't conclude "nothing open" from an
  empty result without double-checking the location string first.
- Omit `--query`/title filters entirely for a per-company check and just filter the results
  yourself afterward (same "pull the full board" philosophy as `search ats`) — the AI-classified
  filters (`--work-arrangement`, ATS `--ats` list) are more useful for narrowing a *market-wide*
  scan than for a single already-known company.
- Treat a real result here the same as a Stage 2a direct-source hit for dedupe priority. If it
  finds a working ATS worth remembering (e.g. reveals a company is on Oracle Cloud or Comeet), note
  it in `references/search-fallbacks.md`'s pattern table so a future session knows without a paid
  call — even though `jobs-index` itself doesn't need that table to keep working.

**JS-rendered career pages (Playwright fallback).** `WebFetch` only reads raw HTML and can't
execute JavaScript, so some custom/non-ATS career pages that render listings client-side come back
as an empty shell. Read `references/search-fallbacks.md` (§ "JS-rendered career pages") for when
and how to fall back to `mcp__playwright__browser_*` tools.

**Sanity-check company names before spending a detail-fetch call.** LinkedIn's public jobs index
occasionally surfaces synthetic/placeholder listings — company names containing patterns like
"test company", "sample", "demo", or otherwise clearly not a real employer. Skip these without
calling `linkedin-detail`/`WebFetch` on them, and don't include them in the shortlist; note in the
Stage 4 summary how many were filtered as likely test data.

**For a LinkedIn result** (any `linkedin.com/jobs/view/...` URL, whether it came from Stage 2a's
native search or a WebSearch hit below): use
`search linkedin-detail --id <the-url>` instead of `WebFetch` for enrichment. This replaces the
step that previously 403'd on LinkedIn specifically with the same native endpoint Stage 2a uses.

`WebSearch` results include a title, company, URL, and a synthesized snippet — that snippet alone
is usually enough to score a posting (Stage 3). Treat `WebFetch` on the actual posting page as
**optional enrichment, not a requirement**: try it on the most promising links to get full JD
text, exact posted date, and salary if disclosed — but many job-board pages (LinkedIn especially,
sometimes Greenhouse/Lever's own HTML front-end) return 403s to automated fetches, independent of
anything about the specific posting.

**If `WebFetch` fails on a posting:** don't drop the result and don't retry — score it from the
`WebSearch` snippet alone and mark it `"JD: snippet only — verify on posting page"` in the output.
A failed enrichment call is a normal, expected outcome, not an error to surface loudly.

**Recency filter:** prioritize postings from the last 2–3 weeks. Postings older than ~6 weeks are
often stale (role filled or closed) — still include them if nothing fresher matches well, but flag
them as "possibly stale."

**If every source for a given angle comes back empty:** try a broader phrasing (drop a must-have,
widen location) before giving up on that angle. Note in the final output which angles came up
empty and which sources errored.
