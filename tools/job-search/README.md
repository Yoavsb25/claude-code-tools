# job-search

Runs the end-to-end job hunt: finds current openings matching a personalized profile
(role/location/industry/seniority), ranks them by fit, tracks every application through a
bookkeeping script, and hands off to `resume-tailor` (and `github-project-picker`) for any role
worth pursuing.

## How it works

1. **Load state** — reads the stored personalization profile and the current tracker via
   `scripts/job_tool.py`, so it never re-asks for known preferences or re-surfaces a role already
   tracked, applied to, or rejected.
2. **Personalize** — merges the stored profile (target roles, locations, seniority,
   preferred/avoided industries, must-haves, deal-breakers) with anything new the user says this
   turn, and offers to save changes back for next time.
3. **Search** — queries public, keyless job-board APIs directly via `job_tool.py search`
   (Remotive, Arbeitnow, and any watchlisted company's Greenhouse/Lever/Ashby/SmartRecruiters/
   Recruitee/Workable feed — auto-detected from just a company name via `search discover-ats` if
   the platform/slug aren't already known), plus `WebSearch`/`WebFetch` for broader coverage
   (LinkedIn, Indeed, and companies' own `/careers` pages directly) — including proactively
   discovering companies the user hasn't named and industry-specific angles. Every source degrades
   gracefully to a clear error instead of breaking the run if it's unreachable or blocked.
4. **Dedupe and score** — merges duplicate postings, drops anything already tracked or hitting a
   deal-breaker, and ranks the rest on role fit, requirements fit, and constraint fit (location,
   industry, deal-breakers).
5. **Present a shortlist** and, for roles the user decides to pursue, kicks off `resume-tailor`
   (and optionally `github-project-picker`) using the JD already fetched.
6. **Persist** — records every tracked role via `job_tool.py tracker upsert` (never by hand-editing
   the markdown) and surfaces stale applications or undecided shortlisted roles.

## Bookkeeping script

`scripts/job_tool.py` is a stdlib-only Python script that owns two JSON files plus a generated
markdown view — it is the only thing that should ever write them:

```bash
python3 scripts/job_tool.py profile show
python3 scripts/job_tool.py profile set '{"roles":["Staff Backend Engineer"],"locations":["Remote EU"]}'
python3 scripts/job_tool.py tracker list [--status Applied] [--stale-only]
python3 scripts/job_tool.py tracker upsert '{"company":"Acme Corp","role":"Staff Backend Engineer","status":"Applied"}'
python3 scripts/job_tool.py tracker render
python3 scripts/job_tool.py search remotive --query "backend" [--category X] [--limit 25]
python3 scripts/job_tool.py search arbeitnow --query "backend" [--limit 25] [--max-pages 3]
python3 scripts/job_tool.py search ats --platform greenhouse|lever|ashby|smartrecruiters|recruitee|workable --company <slug> [--query X]
python3 scripts/job_tool.py search discover-ats --company "Acme Corp" [--slug-hint acme] [--query X]
python3 scripts/job_tool.py search discover-workday --url <career-page or myworkdayjobs.com URL> [--company X] [--query Y]
python3 scripts/job_tool.py search workday-jobs --slug <tenant>/<wd_host>/<site> [--company X] [--query Y]
python3 scripts/job_tool.py search workday --url <company myworkdayjobs.com URL> [--query X] [--location Y] [--limit 25]
python3 scripts/job_tool.py search discover-comeet --url <career-page URL> [--company X] [--query Y]
python3 scripts/job_tool.py search comeet-jobs --slug <token>:<company_uid> [--company X] [--query Y]
python3 scripts/job_tool.py search jobs-index [--company X] [--domain Y] [--query Z] [--location "City, Region, Country"] [--ats workday,oraclecloud,...] [--limit 25]
python3 scripts/job_tool.py network import --csv "<path to LinkedIn Connections.csv>"
python3 scripts/job_tool.py network list [--company "<name>"]
python3 scripts/job_tool.py network match [--company "<name>"]
```

State lives in `~/Desktop/Job-Search/` by default (override with `JOB_SEARCH_DIR`):
`profile.json`, `tracker.json` (source of truth), `connections.json` (imported LinkedIn
connections), and the generated `Tracker.md`. Moving a row's status to `Applied`, `Phone Screen`,
or `Interviewing` auto-computes `applied_date`/`followup_date`; `tracker list --stale-only` flags
shortlisted roles idle 10+ days and applied/interviewing roles past their follow-up date with no
status change since.

## Optional: warm intros from your LinkedIn connections

`network match` cross-references an imported LinkedIn connections list against your
`target_companies` watchlist to surface people you already know at companies you're targeting.
This uses **LinkedIn's own official data export** (Settings & Privacy → Data Privacy → "Get a
copy of your data" → request "Connections"), not scraping — no session cookie, no API key, no
account risk, just a `Connections.csv` with real Company/Position columns. See
`SKILL.md`'s "Network — warm intros" section for the full walkthrough.

The `search` subcommands call Remotive, Arbeitnow, and six ATS platforms' public job-board APIs
directly (`urllib`, no dependencies, no API key): Greenhouse, Lever, Ashby, SmartRecruiters,
Recruitee, and Workable. Every call prints a JSON object with a `results` list; a failure (network
policy, outage, unknown company slug) comes back as `{"error": "...", "results": []}` rather than a
stack trace, so one dead source never blocks the others.

`search discover-ats --company "<name>"` auto-detects which of those six platforms (if any) a
company uses, and its slug, from just the company name — no need to already know or paste a
board URL. It probes a handful of plausible slug guesses per platform and reports a `confidence`
(`high` = postings actually found, `low` = a platform resolved with zero postings — some ATS
platforms don't 404 on unknown slugs, so this is a guess, `none` = nothing matched). Workday isn't
supported by these six keyless endpoints — it has no universal keyless GET endpoint of that shape
— but it gets its own free, keyless path below rather than requiring Apify.

## Workday coverage (free by default)

Large enterprises (Microsoft, NVIDIA, Amazon, most Fortune 500s) are almost never on one of the
six ATS platforms above — a lot of them are on Workday instead. `search discover-workday --url
<a career-page URL>` fetches that page's own HTML, looks for the `myworkdayjobs.com` link it
normally contains in its static markup (even when the rest of the page is otherwise
JS-rendered), and — once found — queries Workday's own public CXS JSON API directly for the full,
structured posting list (title, location(s), type, posted date, apply link). No scraping, no
paid Actor, no setup: it works the same way `discover-ats` does, with the same `confidence`
contract (`high`/`low`/`none`). Once a tenant's found, save it to `target_companies` with
`platform: "workday"` and that call's `detected_slug`, and future rounds can skip straight to
`search workday-jobs --slug <that value>` — no repeat HTML fetch needed.

`discover-workday` fetches every matching posting's own detail page (not just the compact search
list) before returning results — this matters because a posting's primary office can be outside
the location you care about while still listing it as one of several hiring sites, which the
compact list alone doesn't always surface. It's parallelized (8 concurrent detail fetches) to stay
fast even for a large board.

**When this isn't enough:** `confidence: "none"` means no Workday link was findable in that page's
static HTML — not proof the company isn't Workday-hosted (the URL guess might be wrong, or the
link only appears after JS execution). That's what the optional Apify fallback below, or
Playwright, is for.

## Comeet coverage (also free by default)

Same idea as Workday, for a different (smaller-scale but real) ATS: `search discover-comeet --url
<a career-page URL>` reads the page's own HTML for its inline `COMEET.init({"token": ...,
"company-uid": ...})` widget config — both values are public, visible to any site visitor via
view-source — then queries Comeet's own positions API directly. Unlike Workday, one request
returns every posting's full detail already (location, department, employment type, apply URL,
last-updated date), so there's no per-posting detail fetch needed once detected. Same `confidence`
contract, same save-to-`target_companies` flow (`platform: "comeet"`, slug `"<token>:<company_uid>"`,
fetch directly next time with `search comeet-jobs --slug <that value>`). A `confidence: "none"`
result means try `search jobs-index` next (below) before WebSearch/WebFetch/Playwright — its ATS
coverage includes Comeet, so it can catch a company this script's own free detection missed.

**One caution surfaced while building this:** `comeet-` CSS class names in a page's markup are not
proof of a real Comeet integration on their own — one company investigated had leftover
Comeet-styled CSS classes but its actual job data came from an embedded Greenhouse API call
instead. `discover-comeet` only trusts an actual `COMEET.init(` config block, not class names, so
this isn't a risk in practice — but keep it in mind if you're ever tempted to guess a company's
platform from its CSS alone.

## Optional: broad ATS coverage via jobs-index (paid, covers everything else)

Workday and Comeet detection above are free but narrow — they only cover those two specific
platforms. `search jobs-index --company "<name>" --location "<City, Region, Country>"` is a paid
Apify Actor (`fantastic-jobs/career-site-job-listing-api`) that queries a pre-built index of
**175k+ company career sites across 54 ATS platforms** — Oracle Cloud, SuccessFactors, iCIMS,
Phenom People, ADP, Paycor, and dozens more this script has no dedicated free integration for,
plus everything it already covers. This is the thing to reach for once a company comes back empty
from `discover-ats`, `discover-workday`, *and* `discover-comeet` — before falling through to
WebSearch/Playwright, not instead of trying the free paths first.

It's also the direct fix for a different problem: instead of guessing role-title phrasing for
free-text search (the LinkedIn/WebSearch approach elsewhere in this skill), you query by exact
organization/domain plus AI-classified filters (`aiExperienceLevelFilter`, `aiWorkArrangementFilter`,
etc.) — filtering on *meaning*, not string-matching whatever synonym a company happens to use for a
role.

**Setup:** same `APIFY_TOKEN` as the Workday Apify fallback below — if you've already set that up,
this works immediately, no extra configuration.

**Cost (verified live):** at Apify's FREE pricing tier, **~$0.012/job + a flat $0.01 per run**.
`--limit` defaults to 25 (kept deliberately small in `job_tool.py` — see
`JOBS_INDEX_DEFAULT_LIMIT`), so a default call costs well under $1 — comfortably inside the
platform's free $5/month credit for occasional use. Raising `--limit` scales cost linearly, so do
it deliberately, not casually.

**Two things verified directly, both worth knowing before you rely on this:**
- The Actor **rejects `limit` below 10** with an HTTP 400 — `job_tool.py` clamps any smaller value
  up to 10 automatically, so this only matters if you're calling the Actor directly outside this
  script.
- `--location` needs the exact `"City, Region/State, Country"` phrase format in English (e.g.
  `"London, England, United Kingdom"`, not `"London, UK"`) — a mismatched format silently returns
  zero rows rather than erroring, so an empty result isn't proof a company has nothing open there
  until you've double-checked the format.

Like the Workday Apify fallback, this always confirms target companies with you before running —
it's a paid call, not a free keyless one. Override the Actor with `APIFY_JOBS_INDEX_ACTOR_ID` if
you ever need a different one from the [Apify Store](https://apify.com/store) (a different Actor
would need its own field-mapping update in `cmd_search_jobs_index` in `job_tool.py`).

## Optional: Workday coverage via Apify (fallback only)

For the rare company where `discover-workday` can't find a Workday link in the career page's
static HTML at all, `search workday` is a paid fallback: it runs a maintained Apify Actor
(`automation-lab/workday-jobs-scraper` by default) against a company's `myworkdayjobs.com` URL and
returns structured job data via browser automation instead of a direct API call.

This is entirely optional — the skill works exactly as before with zero setup if you never touch
this. There are two independent ways to enable it, and the skill prefers whichever is available:

- **An Apify MCP server configured directly in your Claude Code environment** (`mcp__apify__*`
  tools) — if present, the skill calls the same `automation-lab/workday-jobs-scraper` Actor
  through it directly, no environment variable needed.
- **The `APIFY_TOKEN` environment variable**, used by `job_tool.py search workday` (setup below) —
  the fallback path when no Apify MCP server is configured.

Either way, the skill always confirms target companies with you before running a paid Actor call.

1. Create a free account at [apify.com](https://apify.com) and copy your API token.
2. Set `APIFY_TOKEN` in your environment. With no token set, `search workday` degrades like any
   other source (`{"error": "APIFY_TOKEN not set...", "results": []}`), and the skill falls back
   to `WebFetch` as before.
3. Cost: pay-per-event, roughly **$3–3.50 per 1,000 jobs** (plus a small per-run start fee) on
   Apify's free tier — covers on the order of 1,000+ jobs/month on the platform's free $5/month
   credit, comfortably enough for occasional large-enterprise checks.
4. If `automation-lab/workday-jobs-scraper` is deprecated or you prefer a different Actor from the
   [Apify Store](https://apify.com/store), override it with `APIFY_WORKDAY_ACTOR_ID` — note a
   different Actor may have a different input/output schema, which would require updating the
   field mapping in `cmd_search_workday` in `job_tool.py`.

## Scheduling a daily run

To have this run automatically every morning instead of on request, set it up as a scheduled cloud
agent via the `schedule` skill — the prompt it runs should ask for the full Stage 0–7 pipeline
(search, score, two-table shortlist, connections enrichment, save-to-file, auto-shortlist to the
tracker) exactly as SKILL.md's "Scheduled daily runs" section describes, since there's no one
online to answer Stage 4's pursue-decision question in real time.

## Usage

Copy `SKILL.md` and `scripts/job_tool.py` into `~/.claude/skills/job-search/` (or install via the
registry), then say:

> "Find me some jobs — Staff Backend Engineer, remote"
> "What's out there for a senior platform role this week?"
> "I'm open to fintech now too, add that to my preferences"
> "I applied to the Acme Corp role, update the tracker"
> "Move the Widgets Inc application to interviewing"

## Output

- A ranked shortlist (default top 20 per category — public and private companies, scored/capped
  independently) printed in the conversation as two markdown tables.
- The same shortlist saved to `~/Desktop/Job-Search/searches/<date>-job-search-results.md` every
  run.
- A running tracker at `~/Desktop/Job-Search/Tracker.md`, generated from `tracker.json` — edit
  through the script, not the file.
- Tailored resumes via `resume-tailor` for any role the user chooses to pursue.

## Requirements

Python 3.9+ (stdlib only, no dependencies) for `job_tool.py search`/tracker/profile, which now
includes free, keyless Workday and Comeet coverage via `search discover-workday`/`search
workday-jobs` and `search discover-comeet`/`search comeet-jobs` (see "Workday coverage (free by
default)" and "Comeet coverage (also free by default)" above) — no MCP server or token needed for
the common case.
Broader discovery also uses `WebSearch`/`WebFetch`. If a `playwright` MCP server is configured, the
skill also uses it as an optional fallback to render JS-heavy company career pages that `WebFetch`
can't parse (raw HTML only, no JS execution) — the skill works fine without it, just with reduced
coverage of custom career pages that render listings client-side. If `APIFY_TOKEN` is set (an
Apify MCP server also covers the Workday-specific fallback, but not `jobs-index`), the skill also
gets two paid sources: a fallback for the rarer case where `discover-workday` can't find a
company's Workday tenant at all (see "Optional: Workday coverage via Apify (fallback only)"
above), and `search jobs-index`'s much broader 54-platform coverage for companies matching none of
the free structured paths (see "Optional: broad ATS coverage via jobs-index" above) — both
entirely optional. Works best alongside `resume-tailor` and `github-project-picker` for the
hand-off step.

> **Note:** Requirements-fit scoring (Stage 3) and resume-based role suggestions (Stage 1's Role
> discovery) run entirely off the `skills`, `education`, and `experience_summary` fields in
> `profile.json` — set them via `profile set` (or answer the intake questions on first run). No
> external file path to adapt.
