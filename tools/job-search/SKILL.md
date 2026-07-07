---
name: job-search
description: >
  Runs Yoav's end-to-end job hunt — finds current openings that match his personalized target
  criteria (role, location, industry, seniority), ranks them by fit, maintains a running
  application tracker, and kicks off resume-tailor (and github-project-picker) for any role he
  decides to pursue. Use this skill whenever the user wants to discover jobs rather than react to
  one they already have — e.g. "find me some jobs", "what's out there for [role]", "search for
  openings", "help me find my next job", "what should I apply to this week", "update my job
  tracker", "I applied to X", or "set my job search preferences to Y". If the user already has a
  specific job description in hand and just wants a tailored resume, use resume-tailor directly
  instead — this skill is for the discovery + tracking loop around it.
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
| `industries_prefer` | Domains to weight up, e.g. `["devtools", "fintech"]` |
| `industries_avoid` | Domains to weight down or exclude, e.g. `["adtech", "crypto"]` |
| `must_haves` | e.g. `["Kubernetes", "no on-call"]` |
| `deal_breakers` | Hard excludes — companies, conditions (e.g. "RTO 5 days") |
| `salary_floor` | Only used to flag postings that disclose a lower range |
| `target_companies` | Optional watchlist of `{"name": "...", "platform": "greenhouse\|lever\|ashby", "slug": "..."}` — companies to check directly via Stage 2's `search ats` (see below) |

**If the profile is empty (first run):** ask for the fields above in one conversational message,
then save the answer with `profile set` before searching, so future runs don't re-ask.

**If the profile exists:** don't re-ask for anything already set. Only ask about fields the user's
current request doesn't cover and that materially change the search (e.g. they said "find me
jobs" with no other detail and the profile already has roles/locations — just proceed).

**If the user's request conflicts with or extends the stored profile** (new location, dropped
must-have, added industry): after the search, ask whether to save it as the new default —
`"Want me to update your saved preferences to include Berlin?"` — and call `profile set` with just
the changed keys if they say yes. Don't overwrite fields they didn't mention.

**How many results:** default top 10 after ranking, unless the user asks for more/fewer.

---

## Stage 2 — Search adaptively

Two sources run in parallel: the **script's structured search** (fast, reliable, always try
first) and **WebSearch/WebFetch** (broader coverage, including LinkedIn, but less reliable).
Combine whatever each one returns — don't treat either as required.

### 2a — Structured search via `job_tool.py` (always run this first)

These hit public, keyless JSON APIs directly — no scraping, no bot-wall risk, and every call
degrades to a clean `{"error": "...", "results": []}` instead of failing the whole search:

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search remotive --query "<role keyword>" --limit 25
python3 ~/.claude/skills/job-search/scripts/job_tool.py search arbeitnow --query "<role keyword>" --limit 25
```

Run one call per role in `roles` (varying the keyword), in parallel. These two sources are
remote-job-focused aggregators — good general coverage, weakest on senior/staff-level and
non-remote roles.

**If `target_companies` is set in the profile**, also run, per entry:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search ats --platform <platform> --company <slug> --query "<role keyword>"
```
This is the highest-fidelity source available — the company's own live ATS feed, not a mirror.
If the user names a specific company mid-conversation and gives (or you can find) its Greenhouse
`boards.greenhouse.io/<slug>`, Lever `jobs.lever.co/<slug>`, or Ashby `jobs.ashbyhq.com/<slug>` URL,
extract the slug from that URL and run this ad hoc even if it isn't saved to `target_companies` —
then ask whether to add it to the watchlist for next time.

**If a `search` call returns a non-null `error`:** don't retry it — note the source failed (and
why, briefly) in the Stage 4 output, and rely on the other sources for that round. A single
source failing (e.g. this environment's network policy, or that API being temporarily down) must
never block the rest of the pipeline.

### 2b — WebSearch / WebFetch (broader net, especially for LinkedIn)

Run `WebSearch` queries built from the resolved criteria, varying phrasing:
- `site:linkedin.com/jobs [role] [location]`
- `site:linkedin.com/jobs "[role]" remote`
- `"[role]" hiring [location] 2026`
- Plain-language query combining role + location + must-haves, e.g. `Staff Backend Engineer
  remote Kubernetes hiring`

**If `industries_prefer` is set**, add targeted queries per industry, e.g. `[role] fintech
[location] hiring`.

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

**Cross-check against the Stage 0 tracker list.** Drop any posting matching an existing row's
company + role (any status) — don't re-surface something already tracked, applied to, or
rejected. Exception: if the user explicitly asks to re-check a company, include it and note
"already tracked as [status]."

For each remaining posting, score three dimensions:

**Role fit (0–10)** — How closely does the title, level, and JD body match the target role(s) and
seniority? Use exact-title matches and JD language (not just the title) — a "Senior Software
Engineer" posting that's really staff-scope work should score on scope, not label.

**Requirements fit (0–10)** — Overlap between the JD's required skills and Yoav's profile. Load
`~/Desktop/Work/SysAid/profile-summaries/overall-profile.md` for his skill set if not already in
context this session. Penalize postings with hard requirements he clearly doesn't meet (e.g. a
specific clearance, a language he doesn't speak, years of experience he doesn't have).

**Constraint fit (0–10)** — Location/remote match, industry alignment, and deal-breakers:
- A hit on `deal_breakers` drops this to 0 regardless of other scores — exclude the posting
  entirely, don't just rank it low.
- A hit on `industries_avoid` weights this down heavily (score ≤3) but doesn't auto-exclude,
  unless the user has said otherwise.
- A match with `industries_prefer` weights this up.

**Overall score** = (Role fit × 0.4) + (Requirements fit × 0.4) + (Constraint fit × 0.2).
Exclude anything scoring under 5 overall — don't pad the list with weak matches.

Sort descending by overall score. Cap at the requested count (default 10).

---

## Stage 4 — Present the shortlist

```
## 🔍 Job Search — [role(s)]  •  [location(s)]  •  [date]

Searched: Remotive, Arbeitnow, [ATS companies checked], LinkedIn (WebSearch) — [N] postings found,
[N] after dedupe, [N] after constraint filtering. [Note any source that errored, e.g. "Remotive:
unreachable, skipped."]

| # | Company | Role | Fit | Posted | Salary | Link |
|---|---|---|---|---|---|---|
| 1 | Acme Corp | Staff Backend Engineer | 9.2/10 | 3 days ago | $180–220k | [Apply →](url) |
| 2 | Widgets Inc | Senior Platform Engineer | 8.1/10 | 1 week ago | Not disclosed | [Apply →](url) |

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

## Key rules

- **The script owns the tracker and profile files.** Never hand-edit `Tracker.md`,
  `tracker.json`, or `profile.json` directly — always go through `job_tool.py`, so state can't
  silently drift or lose rows across sessions.
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
