# Search Fallbacks — ATS Auto-Detection, Workday, Comeet, jobs-index, and JS-Rendered Career Pages

Conditional detail for Stage 2 of `job-search`'s SKILL.md. Only read this file when one of the
trigger conditions below actually applies — SKILL.md tells you when to branch here; this file
tells you what to do once you have.

## Checking a specific company (location-first method)

**When to run this:** whenever you're checking a specific `target_companies` entry or a
large-enterprise baseline company — as an alternative to `<company> + <one role title>` queries,
which are unreliable: they silently under-cover roles (checking only 1-2 of the profile's `roles`
titles per company misses the rest), and they miss postings entirely when the company uses a
different internal title for the same job family. Known synonyms worth trying before concluding a
company has nothing open in a given family:

| Job family | Common alternate titles |
|---|---|
| Solutions/pre-sales engineering | Google: "Customer Engineer" · Microsoft: "Cloud Solution Architect" / "Technical Specialist" · AWS: "Solutions Architect" |
| Customer-embedded software engineering | OpenAI, Anthropic, Palantir-style AI labs: "Forward Deployed Engineer" (a software-engineer/solutions-engineer hybrid — won't match a plain "Software Engineer" or "Solutions Engineer" query) |

**The method**, since the result set for one named company is naturally bounded (unlike an
open-ended market-wide search, where title-based querying is still necessary):
1. **Known ATS (`search ats`), or a known Workday/Comeet tenant (`search workday-jobs`/`search
   comeet-jobs`):** omit `--query` entirely and pull the full board (raise `--limit` as needed),
   then filter the results down to the profile's `locations` yourself.
2. **Unknown platform:** try `search discover-ats`, then `search discover-workday` and `search
   discover-comeet` (all free), then `search jobs-index` (paid, confirm with the user first — see
   "Broad ATS coverage via jobs-index" below) before falling back to `search linkedin --query
   "<Company Name>"` (company name only, no role) `--location "<location>"`, which returns that
   company's actual open postings at that location across whatever titles they use.
3. **Either way, evaluate every remaining posting against the profile holistically** — title,
   scope, and description against `roles`/`skills`/`experience_summary` — rather than
   pre-filtering by whether the title matches one of the profile's role strings. A posting can be
   an excellent fit under a title nobody would have thought to search for. This is exactly the
   pool Stage 3's "adjacent roles at a specifically-checked company" exception draws from — pull
   the full board first, score everything, and let that exception catch the ones that don't hit
   the main bar but are still worth surfacing because of *which* company they're at.

This is slower per company than a single title query, but far more thorough — reserve it for named
`target_companies` and large-enterprise baseline checks, not the open market-wide search across all
of Stage 2a/2b, where there's no natural per-company boundary to exploit this way.

**A company not in `target_companies` can still be missed even with a great-fitting posting.**
Market-wide role searches (`search linkedin --query "<role>"` with no company) only return a
capped, relevance/recency-ranked slice (`--limit`) of what can be thousands of matching postings
citywide — there's no guarantee a specific company's specific posting surfaces in that slice, even
when it's an excellent fit. The only reliable way to guarantee a specific company gets checked is
to add it to `target_companies` (or run an ad hoc per-company check per the method above). If the
user asks about a specific posting that didn't come up, check whether its company was actually in
`target_companies` before diagnosing anything else — that's the most common reason, and the fix is
adding the company to the watchlist, not just tweaking query phrasing.

**Company-name-only queries are unreliable for short/common names.** Tested directly: a bare
`--query "Palo Alto Networks"` (distinctive, multi-word) correctly returned ~10 real postings from
that company. But bare queries for short or common single-word names — `"NVIDIA"`, `"Intel"`,
`"Dell"`, `"Microsoft"`, `"Salesforce"`, `"Amdocs"`, `"ServiceNow"` — returned unrelated noise with
zero actual postings from that company, even though some of these companies do have open London
roles (confirmed separately). Always check the `company` field of returned results actually
matches before concluding "nothing found" — if it doesn't, don't trust the negative result; fall
back to the direct career-page/Workday route (below) instead of reporting the company as having no
openings.

## Known large-enterprise career-site patterns

**Why this table exists:** a generic "search the web, then fetch/scrape whatever URL comes back"
approach reliably fails on large-enterprise career sites — it lands on the homepage or a marketing
landing page, not the actual filtered job list, because these sites are either JS-rendered SPAs or
gate their real listing behind a specific query-string pattern that a bare company-name search
doesn't surface. Each row below was verified directly (not guessed) by actually fetching the URL
and confirming real postings came back. Update this table whenever you verify a new company's
pattern — don't let this knowledge evaporate at the end of a session.

| Company | Platform / pattern | What actually works | Notes |
|---|---|---|---|
| NVIDIA | Workday (`nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite` — note the `en-US` locale prefix isn't part of the site name; `detect_workday_tenant()` strips it) | `search discover-workday --url https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite --company "NVIDIA"` (or `search workday-jobs --slug nvidia/wd5/NVIDIAExternalCareerSite` once saved to `target_companies` — verified live: `detected_slug` comes back as `nvidia/wd5/NVIDIAExternalCareerSite`, 3 segments, no locale) | Confirmed Workday tenant — never try `search ats`/`discover-ats` for it. Free `discover-workday` replaces the old paid-Apify-first approach for this one. |
| Salesforce | Custom site, but has a working filtered-listing URL | Construct and fetch `https://careers.salesforce.com/en/jobs/?search=<role keyword>&country=United+Kingdom&pagesize=20#results` directly (WebFetch or Playwright) — do not fetch the bare `careers.salesforce.com` homepage, it returns marketing content with no listings. | `discover-ats` returns nothing (not on any of the 6 supported platforms) — expected, don't retry it. |
| Palo Alto Networks | Custom site (Phenom People platform) | Use the location-taxonomy URL directly, e.g. `https://jobs.paloaltonetworks.com/en/location/london-jobs/47263/2635167-6269131-2643743/4` (find the numeric taxonomy path via one WebSearch for `"Palo Alto Networks" London jobs`, then reuse it) — the listing page itself is large (100K+ chars of markdown when scraped), so prefer targeted extraction (grep/search within fetched content for role keywords) over reading it in full. | Bare-name LinkedIn search (`search linkedin --query "Palo Alto Networks"`) does work reasonably here per the "Checking a specific company" section above — this is the one exception among this table's companies. |
| Google | Custom site, server-rendered | `https://www.google.com/about/careers/applications/jobs/results` returns real listings even via a plain fetch and supports `&page=N` for pagination — but no confirmed location/query-string filter param (untested: `&location=`). Prefer `search linkedin --query "Customer Engineer" --location "London"` instead (Google's own internal title for Solutions Engineering roles — see the synonym table above) since it reliably surfaces real London Google postings without needing the careers-site's facet UI. | Don't use "Software Engineer" as the query for Google via LinkedIn — the company itself doesn't reliably surface that way; London Google postings found this way have skewed heavily towards Customer Engineer / Cloud / TPM roles, not generalist SWE. |
| Microsoft | Mixed — no confirmed keyless API, not a confirmed Workday tenant | `careers.microsoft.com` homepage is a JS shell with no listings from a plain fetch. `microsoft.ai/careers/` (Microsoft AI's own vertical career page) DOES render full listings via a plain fetch, including London roles — use that directly for AI/ML-flavored roles. For general Microsoft SWE roles, no verified fast path yet — fall back to Playwright (`browser_navigate` + `browser_snapshot`) on `careers.microsoft.com`. | Bare-name LinkedIn search for "Microsoft" returns noise (documented in "Checking a specific company" above) — don't rely on it here either. |
| Amdocs | Unconfirmed — not Workday (checked, no `myworkdayjobs.com` tenant found), not on any of the 6 supported ATS platforms | No verified fast path yet. `jobs.amdocs.com/careers` — try Playwright first; if that's not configured in the install, fall back to WebSearch snippets and note the gap rather than guessing. | Bare-name LinkedIn search for "Amdocs" returns noise — don't rely on it. |
| Unity | Confirmed **not** on any of the 6 supported ATS platforms (tested via `discover-ats` — a `smartrecruiters` slug match returned 0 results and is very likely an unrelated company's board given "unity" is a common slug word; don't trust it) — **is** a confirmed Workday tenant, found via `discover-workday` | `search discover-workday --url https://unity.com/careers/positions --company "Unity Technologies"` (or `search workday-jobs --slug unitytech/wd1/Unity` once saved) — `unity.com/careers/positions` is a Next.js page but still links out to its `unitytech.wd1.myworkdayjobs.com` tenant in static HTML, so detection works without Playwright. Verified live: 126 total open postings company-wide. | Superseded: this row used to say "no confirmed keyless endpoint, use Playwright/LinkedIn" — that's no longer true now that `discover-workday` exists. Don't use `discover-ats`'s low-confidence SmartRecruiters hit as a real match. |

## ATS auto-detection

**When to run this:**
- A company in `target_companies` has no `platform`/`slug` set, or
- Stage 2b's proactive discovery surfaces a candidate company that isn't an obvious large
  enterprise (see SKILL.md's large-enterprise skip rule).

**Command:**
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-ats --company "<company name>" --query "<role keyword>"
```

**What it does:** probes slug guesses derived from the company name (concatenated/hyphenated
forms, with and without legal suffixes like "Inc"/"Ltd") against each supported ATS platform's
keyless JSON API — Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable, in that order —
and returns whichever combination actually resolves.

**Reading `confidence` in the response:**
- `"high"` — postings were actually found. Trust this.
- `"low"` — the endpoint responded without error but returned zero postings. Some platforms don't
  distinguish "unknown slug" from "real board, no current openings" — treat this as a guess, not a
  confirmed miss.
- `"none"` — nothing matched any platform/slug combination tried. Fall back to Stage 2b's direct
  career-page search for this company, targeting its real domain directly, not just LinkedIn.

**If `detected_platform` is non-null:**
1. Treat the returned postings as Stage 2a results (same dedupe priority as any other `search
   ats` call).
2. After presenting the shortlist, ask the user: `"Found <Company>'s job board on <platform>
   (<slug>, confidence: <level>) — want me to save that to your watchlist?"`
3. If yes: read the current `target_companies` from `profile show` (Stage 0's copy, or a fresh
   call if this is late in a long turn), add or update the entry by matching `name`
   case-insensitively, and write back the **full merged array** — `profile set` replaces
   `target_companies` wholesale (`profile.update(patch)` is a shallow merge), so never patch with
   just the new entry, or the rest of the watchlist is silently dropped:
   ```bash
   python3 ~/.claude/skills/job-search/scripts/job_tool.py profile set '{"target_companies": [ ...existing entries unchanged..., {"name": "<Company>", "platform": "<platform>", "slug": "<slug>"} ]}'
   ```

## Workday-hosted companies

**When this applies:** any target/discovered large enterprise, whether or not a `myworkdayjobs.com`
URL has surfaced yet — Workday is the single most common ATS among large enterprises, so it's
worth checking proactively rather than only reacting to a WebSearch hit that happens to mention it.

**Try `search discover-workday` first, always** (see SKILL.md's "Workday-hosted companies
specifically" in Stage 2a for the exact command and how to read `confidence`). It's free, keyless,
and — because it fetches every posting's own detail page rather than trusting the compact search
list's location text — it catches postings a naive scrape would miss: a role whose *primary*
office is elsewhere but which also lists the target location as one of several hiring sites (found
and fixed by cross-checking Unity's live board against unity.com/careers directly in a browser —
a real gap, not a hypothetical one). Only fall through to the paths below when `discover-workday`
returns
`confidence: "none"` — meaning no Workday link was findable in that career page's static HTML at
all (the URL guess may be wrong, or the real link only appears after JS execution).

**Three fallback paths, in order, once `discover-workday` comes back empty:**

1. **`mcp__apify__*` tools available in this session** (check the deferred-tools list —
   independent of any environment variable). Preferred path:
   - Confirm the target company list with the user first, unless they already named the companies
     explicitly — this is a paid call regardless of which path runs it.
   - Call `mcp__apify__fetch-actor-details` on `automation-lab/workday-jobs-scraper` to confirm
     its input schema.
   - Call `mcp__apify__call-actor` with the company's `myworkdayjobs.com` URL, a role keyword, and
     location.
   - Default `maxJobs` to 10 (well under the Actor's own 20–50 default) rather than pulling
     everything.
   - Fetch results with a `fields` projection (`title,location,postedDate,url,compensation`
     first) before pulling full descriptions — only fetch full descriptions for the subset that
     survives that first pass. A large unprojected result set can overflow tool output entirely
     and get dumped to a file instead of returned inline, which defeats the point of a quick
     check.

2. **Else, `APIFY_TOKEN` configured for this install.** Run:
   ```bash
   python3 ~/.claude/skills/job-search/scripts/job_tool.py search workday --url <the myworkdayjobs.com URL> --query "<role keyword>" --location "<location>"
   ```
   - Same graceful-degradation contract as every other source (a bad URL or Actor hiccup degrades
     to `{"error": ..., "results": []}`, never blocks the rest of the run).
   - Same confirm-before-spend and lean-query discipline as path 1: confirm target companies with
     the user first unless already named.
   - Don't run this as a blanket re-check every round — reserve it for `target_companies`
     watchlist entries and the proactive-discovery hits already covered by the "~5
     newly-discovered companies per round" cap in SKILL.md's Stage 2b, the same restraint applied
     to the Playwright fallback below.

3. **Neither available, or the call errors.** Fall back to `WebFetch` on the public career-page
   listing directly — same optional-enrichment/graceful-degradation treatment as any other page in
   Stage 2b.

## Comeet-hosted companies

**When this applies:** any target/discovered company, checked alongside (not instead of)
`discover-ats` and `discover-workday` — Comeet is a smaller-scale ATS than Workday but showed up
for multiple companies in a single discovery sweep (LSports, WSC Sports were both confirmed
live), so it's worth a routine check, not just a reactive one.

**Try `search discover-comeet` as part of the same pass as `discover-workday`:**
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-comeet --url "<company careers-page URL>" --company "<Company Name>" --query "<role keyword>"
```
- Detection reads the career page's own HTML for an inline `COMEET.init({"token": ...,
  "company-uid": ...})` widget-config call — both values are public (any site visitor can see them
  via view-source; Comeet's own client-side JS uses them the same way), so treating them as a
  public tenant identifier and saving them to `target_companies` is safe, same as Workday's
  tenant/site.
- Unlike Workday, a single successful call returns every posting's full detail already (location,
  department, employment type, apply URL, last-updated timestamp) — no per-posting detail fetch or
  pagination needed, so this is actually a *cheaper* structured source than Workday once detected.
- `confidence: "high"`/`"low"` → save `platform: "comeet"` and the returned `detected_slug`
  (`"<token>:<company_uid>"`) to `target_companies`; future rounds call `search comeet-jobs --slug
  <that value>` directly, no re-discovery HTML fetch needed.
- `confidence: "none"` → not Comeet-hosted, or the widget config is loaded by deferred/lazy-loaded
  JS the static HTML fetch can't see (confirmed to happen — e.g. LSports' page uses a WordPress
  lazy-load plugin that hides the config from a plain fetch even though the site is genuinely
  Comeet-hosted). If you have independent reason to suspect a company is Comeet-hosted anyway
  (e.g. `comeet` CSS classes or a `comeet.co`/`comeet.com` script reference show up in the raw
  HTML even without the full config), that's a hint worth a Playwright follow-up rather than
  giving up — a rendered page may expose the config a static fetch can't. **Caution:** matching
  `comeet-` CSS class *names* alone is not proof of a real Comeet integration — one investigated
  company (Aidoc) had Comeet-styled CSS classes left over in its markup but its actual job data
  came from a Greenhouse API call embedded in the page's JS instead. Confirm the literal
  `COMEET.init(` call (or a genuine `comeet.co`/`comeet.com` script `src`) before trusting the
  platform guess — a CSS class name alone proves nothing about what's actually serving the data.
- If `discover-comeet` can't find it (including the LSports-style lazy-load case above), try
  `search jobs-index` next (below) before WebSearch/WebFetch/Playwright — its ATS list includes
  `comeet` explicitly, so it can cover a Comeet-hosted company this script's own free detection
  missed.

## Broad ATS coverage via jobs-index (paid, covers what nothing else does)

**When this applies:** a company comes back empty from `discover-ats`, `discover-workday`, *and*
`discover-comeet` — i.e. every free structured-data path has been exhausted. Don't drop straight
to WebSearch/Playwright from here; try this first.

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search jobs-index --company "<Company Name>" --location "<City, Region, Country>" --limit 25
```

**What it is:** a pre-built, continuously-updated index (Apify Actor
`fantastic-jobs/career-site-job-listing-api`) of 175k+ company career sites across 54 ATS
platforms — including several this script will likely never get a dedicated free integration for
(Oracle Cloud, SuccessFactors, iCIMS, Phenom People, ADP, Paycor, and more), plus every platform it
already does (Workday, Comeet, Greenhouse, Lever, etc.). Verified live: a call against "Amazon" +
"London, England, United Kingdom" returned 10 real, current London postings — a company that
earlier discovery sweeps couldn't resolve any other way.

**Cost — this is the one thing to get right before running it:**
- **Paid, requires `APIFY_TOKEN`.** Confirm target companies with the user first, unless already
  named explicitly — same rule as the `search workday` Apify fallback.
- At Apify's FREE pricing tier: **~$0.012/job + a flat $0.01 per run.** `--limit` defaults to 25
  (`JOBS_INDEX_DEFAULT_LIMIT` in `job_tool.py`), so a default call costs well under $1. Don't raise
  `--limit` casually — it scales cost linearly.
- **The Actor rejects `limit` below 10 with an HTTP 400** (verified directly). `job_tool.py`
  clamps any smaller value up to 10 automatically, so this isn't something you need to handle
  yourself, but don't be surprised if a very small `--limit` you asked for returns more rows than
  requested.

**Two gotchas verified directly, both silent-failure risks:**
- **`--location` needs the exact `"City, Region/State, Country"` phrase format, English names, no
  abbreviations** — e.g. `"London, England, United Kingdom"`, not `"London, UK"` or `"London,
  England"`. A malformed location string doesn't error, it just silently returns zero rows. If a
  location-filtered call comes back empty, double check the format before concluding the company
  has nothing open there.
- The actor-id-with-slash form (`fantastic-jobs/career-site-job-listing-api`, URL-encoded to
  `fantastic-jobs%2Fcareer-site-job-listing-api` by `job_tool.py`) works fine against Apify's API —
  confirmed directly, this is not a bug, don't "fix" it to the tilde form.

**Usage pattern:** for a per-company check, omit `--query`/title filters and just pull everything
(`organizationSearch`/`domainFilter` only) — same "pull the full board, filter yourself" approach
as `search ats`. The AI-classified filters (`--work-arrangement`, `--ats`, and the underlying
Actor's broader experience-level/taxonomy filters not yet exposed as CLI flags) are more useful for
a market-wide scan than a single already-known company. If a call reveals which real ATS a company
is on, add a row to the pattern table below so a future session can try that path for free first.

## JS-rendered career pages (Playwright fallback)

**When this applies:** `WebFetch` only reads raw HTML — it can't execute JavaScript, so many
custom/non-ATS career pages that render listings client-side come back as an empty shell (no job
titles, mostly boilerplate/nav text).

**What to do, if `mcp__playwright__browser_*` tools are available in the current environment:**
1. `browser_navigate` to the career-page URL.
2. `browser_snapshot` to read the rendered accessibility tree and extract the actual listings from
   it.

**Guardrails:**
- This is slower than `WebFetch` — only use it on pages that look genuinely JS-rendered (not just
  short), never as a first resort.
- Keep it within the same "cap ~5 newly-discovered companies per round" budget from Stage 2b's
  proactive discovery.
- If Playwright tools aren't configured in a given install (this MCP server isn't guaranteed to be
  present), skip this step entirely and fall back to the WebSearch snippet exactly as before —
  this is optional enrichment on top of optional enrichment, never a hard requirement.
