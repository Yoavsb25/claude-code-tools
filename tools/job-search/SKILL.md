---
name: job-search
description: >
  Runs Yoav's end-to-end job hunt — finds current openings that match his personalized target
  criteria (role, location, industry, seniority), ranks them by fit, maintains a running
  application tracker, and kicks off resume-tailor (and github-project-picker) for any role he
  decides to pursue. Use this skill whenever the user wants to discover jobs rather than react to
  one they already have — e.g. "find me some jobs", "what's out there for [role]", "search for
  openings", "help me find my next job", "what should I apply to this week", "update my job
  tracker", "I applied to X", or "set my job search preferences to Y". Also handles warm-intro
  lookups against an imported LinkedIn connections export — e.g. "who do I know at Google", "find
  warm intros for my target companies", "which of my connections work where". If the user already
  has a specific job description in hand and just wants a tailored resume, use resume-tailor
  directly instead — this skill is for the discovery + tracking loop around it.
---

# Job Search

You are a job-search agent, not a search box. Your job is to go find roles worth Yoav's time,
rank them honestly, keep a living record of where every application stands, and hand off to
resume-tailor the moment a role is worth pursuing.

All bookkeeping (personalization profile + application tracker) is owned by
`scripts/job_tool.py` — a stdlib-only Python script. **Never hand-edit `Tracker.md` or the JSON
files it manages.** The script is the only thing that writes them; you read its output and call it
to make changes. This keeps years of accumulated tracker rows from silently drifting or getting
dropped when the file is regenerated turn after turn.

State lives in `~/Desktop/Job-Search/` (`profile.json`, `tracker.json`, and the generated
`Tracker.md`). Run every command as:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py <group> <action> [args]
```

---

## Stage 0 — Load state

Run both, in parallel:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile show
python3 ~/.claude/skills/job-search/scripts/job_tool.py tracker list
```

- `profile show` returns `{}` on first run — there's no stored personalization yet.
- `tracker list` returns every row plus a computed `stale_reason` (null if not stale). Hold onto
  this list — you need it in Stage 3 (dedupe) and Stage 6 (staleness flags).

**If the user's message is a pure status update, not a search request** (e.g. "I applied to the
Stripe role", "move Datadog to interviewing", "I got rejected by Figma", "add a note to the Notion
row"): skip straight to Stage 6 — call `tracker upsert` for the matching row(s) and stop. Don't run
a search.

**If the user's message is only about preferences** (e.g. "I'm open to fintech now too", "drop the
Kubernetes requirement", "add Berlin as a location"): skip straight to Stage 1's `profile set` call
and stop. Don't run a search unless they also asked for one.

---

## Stage 1 — Personalize the criteria

The stored profile is the default search criteria. Resolve this turn's criteria as:
**stored profile, overridden by anything the user just said.**

Profile fields (all optional except `roles`):

| Field | Notes |
|---|---|
| `roles` | Target title(s), e.g. `["Staff Backend Engineer", "Platform Engineer"]` |
| `locations` | Cities, "Remote EU", "Remote US", hybrid constraints |
| `seniority` | Mid / Senior / Staff+ |
| `skills` | Flat list of technical skills, e.g. `["JavaScript", "React", "Node.js", "CI/CD", "GitHub Actions", "Kubernetes"]`. Drives the skill-flavored query in Stage 2b and anchors requirements-fit scoring in Stage 3 |
| `education` | List of `{"degree": "...", "field": "...", "institution": "...", "graduation_year": ...}` objects — a list, not a single object, to support multiple degrees. Used to hard-check education requirements in postings (minimum degree, graduation-year windows for grad schemes) |
| `experience_summary` | Short free-text paragraph summarizing work history and domain focus, e.g. "2 years as a Software Engineer, focused on CI/CD infrastructure, deployment automation, and internal developer tools using React/Node." Used for holistic Stage 3 scoring judgment and Stage 1 role-discovery suggestions |
| `industries_prefer` | Domains to weight up, e.g. `["devtools", "fintech"]` |
| `industries_avoid` | Domains to weight down or exclude, e.g. `["adtech", "crypto"]` |
| `must_haves` | e.g. `["Kubernetes", "no on-call"]` |
| `deal_breakers` | Hard excludes — companies, conditions (e.g. "RTO 5 days") |
| `salary_floor` | Only used to flag postings that disclose a lower range |
| `target_companies` | Optional watchlist of `{"name": "...", "platform": "greenhouse\|lever\|ashby\|smartrecruiters\|recruitee\|workable\|other", "slug": "..."}`. `platform`/`slug` are optional — if missing, Stage 2a auto-detects them before falling back to Stage 2b (skipped for known large enterprises, see Stage 2a). `platform: "other"` covers Workday and any custom/non-ATS-API career site — the common case for large, well-known companies (Microsoft, NVIDIA, Amazon, most Fortune 500/public companies). It's bookkeeping only: `job_tool.py` has no reliable keyless endpoint for these, so they're always checked via Stage 2b's direct career-page search, never via `search ats`/`discover-ats`. Also used by `network match` (see "Network — warm intros" below) to surface warm-intro connections at these companies |

**If the profile is empty (first run):** ask for the fields above in a single `AskUserQuestion`
call (multiple questions within one call is fine) or one free-text message — never split intake
across multiple sequential question rounds, that's more friction than a first-time user should
have to sit through. The one exception is `roles` itself, if the user hasn't already named one —
resolve that first via **Role discovery** below (a legitimate back-and-forth, not intake-splitting),
then batch everything else into one call. `skills`/`education`/`experience_summary` don't need to
be exhaustive — a short list and a one-paragraph summary are enough to start; they can be refined
later via `profile set`. Save the answer with `profile set` before searching, so future runs don't
re-ask.

**If the profile exists:** don't re-ask for anything already set. Only ask about fields the user's
current request doesn't cover and that materially change the search (e.g. they said "find me
jobs" with no other detail and the profile already has roles/locations — just proceed).

**If the profile exists but predates `skills`/`education`/`experience_summary`** (i.e. `profile
show` returns a profile with `roles`/`locations` set but none of the three): ask for them once, in
the same low-friction single-message style as first-run intake, before proceeding with the search.
Save via `profile set` and never ask again once they're present — even if the user later leaves
one empty on purpose.

**If the user's request conflicts with or extends the stored profile** (new location, dropped
must-have, added industry): after the search, ask whether to save it as the new default —
`"Want me to update your saved preferences to include Berlin?"` — and call `profile set` with just
the changed keys if they say yes. Don't overwrite fields they didn't mention.

**How many results:** default top 10 after ranking, unless the user asks for more/fewer.

**Role discovery.** Run this when `roles` isn't set yet (first run and the user hasn't already
named a role) or whenever the user explicitly asks for help figuring out what to search for
("what roles should I look at", "suggest some titles", "I'm not sure what I want next").

1. **Ask about direction before assuming continuity.** Don't default to "more of the same" just
   because a resume shows a long history in one field — ask directly: *"Are you looking to
   continue in your current field, or make a change? (Someone with 30 years as a software
   engineer might now want something totally different — like becoming a pilot. Tell me if
   that's the kind of shift you're making.)"* Take whatever direction the user states at face
   value; it overrides anything the resume implies.
2. **If they name a clear pivot or a specific role themselves:** use that directly as `roles` —
   skip resume-based suggestions entirely. The resume can still inform Stage 3's requirements-fit
   scoring (transferable skills), but it must never override a direction the user explicitly
   stated.
3. **If they're continuing in their field, or ask for suggestions:** use the profile's `skills`,
   `education`, and `experience_summary` (from `profile show` in Stage 0) to propose exactly 5
   candidate role titles that fit their background and stated direction. If those fields aren't
   set yet, ask for them first (see Stage 1's field table) rather than guessing from `roles` alone.
   Present the 5 titles as a numbered list with a one-line rationale each, and ask which (if any)
   to add. **Never add a suggested title to `roles` without explicit confirmation** — this is a
   suggestion, not a decision the skill gets to make. Once confirmed, save via `profile set` like
   any other Stage 1 change.

**Ambiguous role titles.** Some titles carry more than one industry meaning — e.g. "Automation
Engineer" can mean industrial/PLC/manufacturing automation *or* software test/process automation;
"Analyst" can mean business, data, or security analyst. **Being adjacent to another role in the
`roles` list does not by itself resolve the ambiguity** — a "Software Engineer" entry sitting next
to "Automation Engineer" is not sufficient context to assume the software-automation reading; that
inference has been wrong in practice. Only treat an ambiguous title as resolved if the stored role
string itself already carries an explicit qualifier (e.g. "Software Automation Engineer," "QA
Automation Engineer," "Test Automation Engineer," "Industrial Automation Engineer"). Otherwise, ask
a one-line clarifying question during Stage 1 intake — before Stage 2 runs any search for that
role — rather than discovering the mismatch mid-search after already spending calls on the wrong
industry's postings.

**Salary floor vs. seniority sanity check.** Whenever `salary_floor` and `seniority` are both set
(on profile creation or edit) and `seniority` reads as junior/entry-level, run one `WebSearch` for
typical market salary at that role/seniority/location combination — e.g. `"[role] [seniority]
salary [location]"` — before running the full multi-source search. If the floor looks materially
above what the search turns up, flag it to the user up front, e.g.: *"Your £60k floor is well
above typical London junior rates (~£35–49k) — want to adjust it, or proceed knowing most matches
may fall short?"* Let them adjust or explicitly proceed before spending the full search budget,
rather than only discovering the mismatch after several rounds of per-posting salary enrichment in
Stage 3. This is a single check at intake time — distinct from, and in addition to, the per-posting
salary enrichment in Stage 3 for the near-final shortlist.

---

## Stage 2 — Search adaptively

Two sources run in parallel: the **script's structured search** (fast, reliable, always try
first — including a native LinkedIn source) and **WebSearch/WebFetch** (broader coverage, plus a
LinkedIn fallback net, but less reliable). Combine whatever each one returns — don't treat either
as required.

### 2a — Structured search via `job_tool.py` (always run this first)

These hit public, keyless JSON APIs directly — no scraping, no bot-wall risk, and every call
degrades to a clean `{"error": "...", "results": []}` instead of failing the whole search. The one
exception is `search workday` (see the Workday bullet in Stage 2b below) — a paid, optional Apify
fallback for Workday-hosted enterprises, off by default unless an Apify MCP server is available or
`APIFY_TOKEN` is configured (see README.md for setup/cost):

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search remotive --query "<role keyword>" --limit 25
python3 ~/.claude/skills/job-search/scripts/job_tool.py search arbeitnow --query "<role keyword>" --limit 25
```

Run one call per role in `roles` (varying the keyword), in parallel. These two sources are
remote-job-focused aggregators — good general coverage, weakest on senior/staff-level and
non-remote roles.

**If none of the resolved `locations` mention "Remote", "Anywhere", or similar** (i.e. the search
is strictly on-site/hybrid to specific cities): skip `search remotive`/`search arbeitnow`
entirely. Both are remote-only aggregators and return near-100% irrelevant results for a
location-locked search — running them just burns tokens parsing noise. Note in the Stage 4 summary
that they were skipped and why. If `locations` includes any remote-friendly entry, run them as
normal.

Also run, once per (role × location) pair from the resolved criteria, in parallel with the calls
above:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search linkedin --query "<role keyword>" --location "<location>" --limit 25
```
This hits LinkedIn's public job-search endpoint directly — more reliable than the `WebSearch`-based
LinkedIn queries in Stage 2b below, since it returns structured fields instead of snippets.
**Personal use only** per LinkedIn's Terms of Service — keep query volume low, never bulk or
commercial use.

**If `target_companies` is set in the profile**, also run, per entry with a known
Greenhouse/Lever/Ashby/SmartRecruiters/Recruitee/Workable `platform`:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search ats --platform <platform> --company <slug> --query "<role keyword>"
```
This is the highest-fidelity source available — the company's own live ATS feed, not a mirror.
If the user names a specific company mid-conversation and gives (or you can find) its Greenhouse
`boards.greenhouse.io/<slug>`, Lever `jobs.lever.co/<slug>`, or Ashby `jobs.ashbyhq.com/<slug>` URL,
extract the slug from that URL and run this ad hoc even if it isn't saved to `target_companies` —
then ask whether to add it to the watchlist for next time.

**Skip straight to Stage 2b for entries with `platform: "other"`** (or any company you recognize
as an obviously large, well-known enterprise — Fortune 500, a major public tech company, a
government contractor, a large consultancy: Microsoft, NVIDIA, Amazon, Deloitte, Google, and
similar). Don't run `search ats` or `discover-ats` for these — they're virtually never on one of
the six supported ATS platforms, they're almost always on Workday or a fully custom career site,
and probing all six is a guaranteed-empty round trip. Go straight to Stage 2b's direct career-page
search for these by name instead.

**Auto-detecting a company's ATS.** For any other company in `target_companies` without a
`platform`/`slug`, or that Stage 2b's proactive discovery surfaces as a candidate (see below) and
isn't an obvious large enterprise per the rule above, run `search discover-ats` before falling
back to WebFetch. Read `references/search-fallbacks.md` (§ "ATS auto-detection") for the command,
how to read `confidence`, and the watchlist-save flow once a platform is found.

**If a `search` call returns a non-null `error`:** don't retry it — note the source failed (and
why, briefly) in the Stage 4 output, and rely on the other sources for that round. A single
source failing (e.g. this environment's network policy, or that API being temporarily down) must
never block the rest of the pipeline.

**If a source starts erroring partway through a round** after earlier calls to it succeeded (e.g.
rate-limited after the third `search ats` call this round): stop issuing further calls to that
source for the rest of the round and treat it as a single failure in the Stage 4 summary — don't
retry it call-by-call or log each subsequent failure as a separate error.

### 2b — WebSearch / WebFetch (broader net, especially for LinkedIn)

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
run the auto-detect flow from 2a (`search discover-ats`) before falling back to the direct
career-page search below.

**Large-enterprise baseline check.** If `target_companies` has no large enterprises in it and none
have surfaced yet from the proactive discovery above, don't rely on WebSearch phrasing alone to
surface them — check a small number (3–5) of well-known large employers relevant to the resolved
role/industry as a guaranteed baseline part of every search round, via Stage 2b's direct
career-page search below. This is additional to, not carved out of, the proactive-discovery cap
above — a quiet discovery round doesn't consume this budget. It's a default baseline, not a
replacement for user-specified `target_companies`, which always take priority; it exists because
proactive-discovery WebSearch queries don't reliably surface big-company names on their own.

**Direct career-page search**, for companies with no ATS match — including every `platform:
"other"` watchlist entry and every large enterprise skipped from `discover-ats` per Stage 2a (e.g.
Microsoft, NVIDIA, Amazon, Deloitte). This is the primary path for those companies, not a
fallback: go straight here for them rather than trying `search ats`/`discover-ats` first. In
addition to the `site:linkedin.com/jobs` queries above, search the company's own site directly:
- `site:<company-domain> careers [role]`
- `"<company name>" careers [role] [location]`
- `"<company name>" jobs apply [role]`

If a result lands on the company's own `/careers` or `/jobs` page, `WebFetch` it the same
optional-enrichment way as any other posting page (see below) — it's often a listing page rather
than a single JD, so pull out whichever open roles are visible and score them against the profile.
If `WebFetch` fails or 403s, don't drop the company — note it and rely on the LinkedIn/aggregator
angle for that company this round instead.

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

**Workday-hosted companies specifically.** If a WebSearch result surfaces a `myworkdayjobs.com`
URL for a target/discovered company, don't try `search ats` for it — `job_tool.py`'s keyless ATS
endpoints don't cover Workday. This is the single most common outcome for large enterprises, so
expect it often. Read `references/search-fallbacks.md` (§ "Workday-hosted companies") for the
three-path fallback chain (Apify MCP → `APIFY_TOKEN` → `WebFetch`), including the
confirm-before-spend and payload-safety rules.

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

---

## Stage 3 — Dedupe and score

**Dedupe first, across all sources from Stage 2a and 2b combined.** The same posting often shows
up via both the structured `search ats`/aggregator calls and a `WebSearch` hit (e.g. the same role
on the company's Greenhouse feed and mirrored on LinkedIn). Match by company + title +
near-identical description; keep the direct company/ATS result (2a) over an aggregator or LinkedIn
mirror (2b), and merge any extra detail (e.g. salary shown only on one source) into the kept entry.
Auto-detected ATS results (`search discover-ats`) count as 2a for this ordering; direct
company-career-page hits from the new proactive-discovery queries count as 2b, exactly like any
other WebSearch/WebFetch result — no separate dedupe pass is needed for either. A successful
`search workday` result is also a direct company-board source, so treat it at the same priority
as 2a/`search ats` results when deduping against a WebFetch/LinkedIn mirror of the same posting.

**Cross-check against the Stage 0 tracker list and this conversation's earlier rounds.** Drop any
posting matching an existing tracker row's company + role (any status) — don't re-surface
something already tracked, applied to, or rejected. Exception: if the user explicitly asks to
re-check a company, include it and note "already tracked as [status]." Also drop any posting
already shown earlier in this same conversation (e.g. a follow-up "check big companies too" or
"check these via Workday" round) — a second round should never re-present something the first
round already surfaced, even before anything's been saved to the tracker.

For each remaining posting, score three dimensions:

**Role fit (0–10)** — How closely does the title, level, and JD body match the target role(s) and
seniority? Use exact-title matches and JD language (not just the title) — a "Senior Software
Engineer" posting that's really staff-scope work should score on scope, not label.

**Requirements fit (0–10)** — Overlap between the JD's required skills and the profile's `skills`,
`education`, and `experience_summary` (from `profile show` in Stage 0 — no external file to load).
Judge overlap holistically, including reasonable synonyms (e.g. "CI/CD" should match "continuous
integration," not just the literal string) — this stays a judgment call, not a keyword-matching
formula, since JD phrasing varies too much for rigid matching to be reliable. Hard-check any
explicit education requirement in the JD (minimum degree, a graduation-year window for grad/new-grad
postings) against `education`, and penalize postings with other hard requirements clearly unmet
(e.g. a specific clearance, a language not spoken, years of experience not met). If `skills`/
`education`/`experience_summary` aren't set yet, score with looser judgment from `roles`/
`seniority` alone and note the lower confidence rather than blocking the search on missing profile
data.

**Constraint fit (0–10)** — Location/remote match, industry alignment, and deal-breakers:
- A hit on `deal_breakers` drops this to 0 regardless of other scores — exclude the posting
  entirely, don't just rank it low.
- A location mismatch that isn't a formal deal-breaker (on-site/hybrid in a city outside all
  resolved `locations`, or no remote option when only remote locations are set) caps this at ≤3 —
  a role someone can't actually work is a near-exclusion even when the user never listed it as a
  deal-breaker.
- A hit on `industries_avoid` weights this down heavily (score ≤3) but doesn't auto-exclude,
  unless the user has said otherwise.
- A match with `industries_prefer` weights this up.

**Overall score** = (Role fit × 0.35) + (Requirements fit × 0.35) + (Constraint fit × 0.3).
Exclude anything scoring under 5 overall — don't pad the list with weak matches.

Sort descending by overall score. Cap at the requested count (default 10).

**Salary enrichment for the near-final shortlist.** If `salary_floor` is set and a posting in the
top-scoring set doesn't disclose salary, run one `WebSearch` per such posting — capped at the top
5–6 candidates, so this doesn't multiply cost across the whole list — for `"<company> <role>
salary <location>"` to check public salary-aggregator data (Glassdoor, levels.fyi, Payscale-style
results). Use this only to annotate the posting with an estimated range and flag it if the
estimate looks below the floor. Never exclude a posting based on estimated data alone, and mark it
clearly as `"salary: ~$X estimated, unconfirmed"` in the output — it's a data point to verify
during application, not a scored fact.

---

## Stage 4 — Present the shortlist

```
## 🔍 Job Search — [role(s)]  •  [location(s)]  •  [date]

Searched: Remotive, Arbeitnow (or "skipped — on-site/hybrid only" if applicable), [ATS companies
checked, including any auto-detected; large enterprises routed directly to career-page search],
LinkedIn (native), Workday via Apify (MCP or APIFY_TOKEN) (or "skipped — neither available" if
applicable), LinkedIn + direct career pages (WebSearch) — [N] postings found, [N] after
dedupe, [N] after constraint filtering, [N] filtered as likely test data. [Note any source that
errored, e.g. "Remotive: unreachable, skipped."]

| # | Company | Role | Fit | Posted | Salary | Link |
|---|---|---|---|---|---|---|
| 1 | Acme Corp | Staff Backend Engineer | 9.2/10 | 3 days ago | $180–220k | [Apply →](url) |
| 2 | Widgets Inc | Senior Platform Engineer | 8.1/10 | 1 week ago | ~$150k estimated, unconfirmed | [Apply →](url) |

⚠️ Possibly stale (posted 5+ weeks ago, include only if nothing fresher fit as well):
| # | Company | Role | Fit | Posted | Link |
|---|---|---|---|---|---|

💡 Angles that came up empty: [e.g. "no results for 'remote EU only' — widened to include UK-based roles"]
```

Then ask: **"Want me to add all of these to the tracker as Shortlisted, and tailor a resume for
any of them right now?"**

**If all searches returned nothing above the score-5 threshold:** say so directly, list what was
tried, and suggest the most likely fix (widen location, drop a must-have, adjust title) rather than
showing an empty or padded table.

---

## Stage 5 — Handle the pursue decision

- **If the user picks specific roles to pursue:** for each one, invoke `resume-tailor` with that
  JD (pass the full JD text you already fetched — don't make the user re-paste it). Offer
  `github-project-picker` too if the role has a strong technical-portfolio angle. Once
  resume-tailor saves its file, note the path for the Stage 6 `tracker upsert` call.
- **If the user says "add them all" without picking:** add every shortlisted role to the tracker
  as `Shortlisted` and stop — don't run resume-tailor on all of them unprompted, that's a lot of
  file generation for roles the user hasn't committed to.
- **If the user says "just show me, don't track yet":** skip Stage 6 for this run.

---

## Stage 6 — Persist

For every role to record, call `tracker upsert` once per row:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py tracker upsert '{"company":"Acme Corp","role":"Staff Backend Engineer","status":"Shortlisted","fit":9.2,"link":"https://..."}'
```
The script matches an existing row by company+role (or by `"id"` if you have one from Stage 0) and
merges — it will not create a duplicate. It also auto-sets `applied_date` and `followup_date` when
you move a row's status to `Applied`, `Phone Screen`, or `Interviewing`; only pass those fields
explicitly if you need to override the default.

`status` must be one of, in order: `Shortlisted` → `Applied` → `Phone Screen` → `Interviewing` →
`Offer` / `Rejected` / `Withdrawn`. Never move a row backwards except to `Withdrawn` or `Rejected`.

**After persisting, surface staleness:**
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py tracker list --stale-only
```
Report every flagged row in your reply — don't just leave it sitting in the file. These are rows
either shortlisted 10+ days with no decision, or applied/interviewing rows past their follow-up
date with no status change logged since.

---

## Network — warm intros at target companies

Trigger this section instead of the Stage 0–6 search pipeline for requests like "who do I know at
X", "find warm intros for my target companies", "which connections work at [company]", "who can
refer me at Google", "what companies am I connected to", or "show me my network by company". This
is a separate, on-demand lookup — it never touches `tracker.json` and
never runs a job search. Read `references/network-warm-intros.md` for one-time connections-export
setup, the `network import`/`list`/`match` commands, and the presentation format.

---

## Key rules

- **The script owns the tracker and profile files.** Never hand-edit `Tracker.md`,
  `tracker.json`, or `profile.json` directly — always go through `job_tool.py`, so state can't
  silently drift or lose rows across sessions.
- **Array-valued profile fields overwrite, they don't merge.** `profile set` performs a shallow
  merge (`profile.update(patch)`) — passing `locations`, `skills`, `must_haves`, `deal_breakers`,
  `industries_prefer`/`industries_avoid`, `education`, or `target_companies` replaces that field's
  entire array. Before adding or removing a single item (e.g. "add Berlin as a location," "drop
  the Kubernetes requirement"), read the field's current value from `profile show` first, splice
  the change in, and write back the full array — never patch with just the delta, or the rest of
  the list is silently dropped.
- **No single search source is required.** `search remotive`/`arbeitnow`/`ats` and `WebFetch`
  enrichment can each fail independently (network policy, an API being down, a bot wall) — every
  one degrades to an empty/partial result with a clear reason instead of stopping the pipeline.
  Score and present whatever data actually came back; note what didn't.
- **The stored profile is the default; the user's current message is the override.** Ask only for
  what's missing or changed, and offer to save changes back — don't re-run full intake every time.
- **Never re-surface a tracked role** unless the user explicitly asks to re-check it.
- **A hit deal-breaker excludes a posting entirely** — don't rank it low, drop it, and don't show
  it in the main table (a short "excluded" footnote is fine if the user would want to know why).
- **Don't run resume-tailor on the whole shortlist unprompted.** Only tailor for roles the user has
  actually decided to pursue.
- **Prefer the direct company/ATS application link** over aggregator mirrors when the same posting
  appears in multiple places.
- **Never submit an application.** This skill searches, ranks, tracks, and prepares materials —
  the user always submits.
- **Be honest about weak weeks.** If nothing scores above threshold, say so plainly rather than
  lowering the bar to fill the table.
- **LinkedIn access is personal-use-only** per its Terms of Service — keep query volume low on
  both `search linkedin` and `search linkedin-detail`, never bulk or commercial use.
- **Deliberately skipping a source is not the same as it failing.** Remotive/Arbeitnow being
  skipped for an on-site-only search, or `discover-ats` being skipped for a known large enterprise,
  are judgment calls to avoid wasted, guaranteed-empty calls — note them plainly in the Stage 4
  summary, distinct from an actual `error`.
- **Large enterprises go straight to Stage 2b.** Don't probe `search ats`/`discover-ats` against
  companies you already know are unlikely to be on a supported ATS platform (Microsoft, NVIDIA,
  Amazon, Deloitte, and similar) — go directly to their real career page.
