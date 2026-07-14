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
python3 scripts/job_tool.py search workday --url <company myworkdayjobs.com URL> [--query X] [--location Y] [--limit 25]
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
supported by these keyless endpoints — it has no universal keyless GET endpoint — companies on
Workday are found via `search workday` (see below) if `APIFY_TOKEN` is configured, or the skill's
`WebSearch`/`WebFetch` track otherwise, along with any other company whose career page isn't on a
supported ATS.

## Optional: Workday coverage via Apify

Large enterprises (Microsoft, NVIDIA, Amazon, most Fortune 500s) are almost never on one of the
six ATS platforms above — they're usually on Workday, whose career sites render listings
client-side, so `WebFetch` alone often returns an empty shell. `search workday` closes this gap
by running a maintained Apify Actor (`automation-lab/workday-jobs-scraper` by default) against a
company's `myworkdayjobs.com` URL and returning structured job data — the same reliability as
every other source, not a coin-flip.

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

## Optional: Excel export

`scripts/export_xlsx.py` turns a search run's shortlist into a two-sheet `.xlsx` workbook (Public
Companies / Private Companies, per Stage 4's standing public/private split), with a clickable
"Apply →" hyperlink per row and a Connections column from Stage 4.5's warm-intro lookup. Unlike
`job_tool.py`, this script needs `openpyxl`, a third-party package — kept in its own file so the
core stdlib-only bookkeeping script never gains a hard dependency.

One-time setup:
```bash
python3 -m venv ~/.claude/skills/job-search/.venv
source ~/.claude/skills/job-search/.venv/bin/activate
pip install openpyxl
```

Then run it (see its module docstring for the exact input JSON shape):
```bash
~/.claude/skills/job-search/.venv/bin/python3 ~/.claude/skills/job-search/scripts/export_xlsx.py --input payload.json
```

This is entirely optional — if the venv/`openpyxl` isn't set up, the script exits with setup
instructions and the skill falls back to the markdown tables already shown in the conversation,
same graceful-degradation contract as every other optional integration here.

## Scheduling a daily run

To have this run automatically every morning instead of on request, set it up as a scheduled cloud
agent via the `schedule` skill — the prompt it runs should ask for the full Stage 0–7 pipeline
(search, score, two-table shortlist, connections enrichment, Excel export, auto-shortlist to the
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

- A ranked shortlist table printed in the conversation.
- A running tracker at `~/Desktop/Job-Search/Tracker.md`, generated from `tracker.json` — edit
  through the script, not the file.
- Tailored resumes via `resume-tailor` for any role the user chooses to pursue.

## Requirements

Python 3.9+ (stdlib only, no dependencies) for `job_tool.py search`/tracker/profile. Broader
discovery also uses `WebSearch`/`WebFetch`. If a `playwright` MCP server is configured, the skill
also uses it as an optional fallback to render JS-heavy company career pages that `WebFetch` can't
parse (raw HTML only, no JS execution) — the skill works fine without it, just with reduced
coverage of custom career pages that render listings client-side. If an Apify MCP server is
configured, or `APIFY_TOKEN` is set, the skill also gets reliable structured coverage of
Workday-hosted large enterprises (see "Optional: Workday coverage via Apify" above) — again,
entirely optional, and either one is enough on its own. Works best alongside `resume-tailor` and
`github-project-picker` for the hand-off step.

> **Note:** Requirements-fit scoring (Stage 3) and resume-based role suggestions (Stage 1's Role
> discovery) run entirely off the `skills`, `education`, and `experience_summary` fields in
> `profile.json` — set them via `profile set` (or answer the intake questions on first run). No
> external file path to adapt.
