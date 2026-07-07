---
name: job-search
description: >
  Runs Yoav's end-to-end job hunt — finds current openings that match his target criteria, ranks
  them by fit, maintains a running application tracker, and kicks off resume-tailor (and
  github-project-picker) for any role he decides to pursue. Use this skill whenever the user wants
  to discover jobs rather than react to one they already have — e.g. "find me some jobs", "what's
  out there for [role]", "search for openings", "help me find my next job", "what should I apply
  to this week", "update my job tracker", or "I applied to X, mark it in the tracker". If the user
  already has a specific job description in hand and just wants a tailored resume, use
  resume-tailor directly instead — this skill is for the discovery + tracking loop around it.
---

# Job Search

You are a job-search agent, not a search box. Your job is to go find roles worth Yoav's time,
rank them honestly, keep a living record of where every application stands, and hand off to
resume-tailor the moment a role is worth pursuing.

The tracker file is the source of truth across sessions. Always read it before searching, and
always update it before you finish.

---

## Step 0 — Load the tracker

Read `~/Desktop/Job-Search-Tracker.md` if it exists.

- **If it doesn't exist**, this is a first run — create it at the end of Step 4 using the template
  in "Tracker format" below.
- **If it exists**, parse every row. You'll need this to avoid re-surfacing roles already tracked
  and to check for stale applications (Step 5).

**If the user's message is a status update, not a search request** (e.g. "I applied to the Stripe
role", "move Datadog to interviewing", "I got rejected by Figma", "add a note to the Notion row"):
skip straight to Step 6 — update the matching row(s) and stop. Don't run a search.

---

## Step 1 — Gather search criteria

Ask for whatever's missing in one conversational message. Skip anything already answered by the
user or inferable from the existing tracker (e.g. if every tracked role is "Staff Backend
Engineer, remote, US/EU", assume the same criteria apply unless the user says otherwise).

| Field | Required | Notes |
|---|---|---|
| Target role(s) / titles | Yes | Can be a few variants, e.g. "Staff/Senior Backend Engineer, Platform Engineer" |
| Location / remote | Yes | Specific cities, "remote only", "remote in EU/US timezones", hybrid, etc. |
| Seniority | Recommended | Mid / Senior / Staff+ — shapes both search terms and ranking |
| Must-haves | No | e.g. "Kubernetes", "no on-call", "equity", "series B+" |
| Deal-breakers | No | Companies, industries, or conditions to exclude (e.g. crypto, adtech, RTO 5 days) |
| Salary floor | No | Only used to flag postings that disclose a lower range |
| How many results | No | Default: top 10 after ranking |

If the tracker already has an established profile and the user just says "find me more jobs" or
"what's new this week", reuse the last-used criteria without re-asking.

---

## Step 2 — Search adaptively

Use `WebSearch` for discovery, then `WebFetch` on the most promising links to pull full posting
details (full JD text, posted date, salary range if disclosed). Run searches in parallel.

**Base searches (always run several, varying phrasing):**
- `site:linkedin.com/jobs [role] [location]`
- `site:linkedin.com/jobs "[role]" remote`
- `[role] [location] jobs site:lever.co OR site:greenhouse.io`
- `"[role]" hiring [location] 2026`
- Plain-language query combining role + location + any must-haves, e.g. `Staff Backend Engineer
  remote Kubernetes hiring`

Adjust the exact query set to the role and location the user gave — the goal is broad coverage
across LinkedIn, Indeed, and ATS platforms (Greenhouse, Lever, Ashby), not a fixed list of URLs.

**For promising results**, `WebFetch` the actual posting page to get:
- Full job description text
- Posted / reposted date
- Salary range, if disclosed
- Direct application link (prefer the company's own ATS link over an aggregator mirror of the
  same posting)

**Recency filter:** prioritize postings from the last 2–3 weeks. Postings older than ~6 weeks are
often stale (role filled or closed) — still include them if nothing fresher matches well, but flag
them as "possibly stale."

**If a search returns nothing useful:** try a broader phrasing (drop a must-have, widen location)
before giving up on that angle. Note in the final output which angles came up empty.

---

## Step 3 — Dedupe and score

**Dedupe first.** The same posting often appears on LinkedIn, Indeed, and the company's own ATS.
Match by company + title + near-identical description; keep the direct company/ATS link over the
aggregator copy, and merge any extra detail (e.g. salary shown only on one mirror) into the kept
entry.

**Cross-check against the tracker.** Drop any posting that already has a row in
`Job-Search-Tracker.md` for the same company + role (regardless of status) — don't re-surface
something already tracked, applied to, or rejected. Exception: if the user explicitly asks to
re-check a company, include it and note "already tracked as [status]."

For each remaining posting, score three dimensions:

**Role fit (0–10)** — How closely does the title, level, and JD body match the target role and
seniority? Use exact-title matches and JD language (not just the title) — a "Senior Software
Engineer" posting that's really staff-scope work should score on scope, not label.

**Requirements fit (0–10)** — Overlap between the JD's required skills and Yoav's profile. Load
`~/Desktop/Work/SysAid/profile-summaries/overall-profile.md` for his skill set if not already in
context this session. Penalize postings with hard requirements he clearly doesn't meet (e.g. a
specific clearance, a language he doesn't speak, years of experience he doesn't have).

**Constraint fit (0–10)** — Location/remote match, and whether any deal-breaker is present. A
single hit deal-breaker (e.g. explicitly "crypto" when that's excluded) drops this to 0 regardless
of other scores and the posting should be excluded entirely, not just ranked low.

**Overall score** = (Role fit × 0.4) + (Requirements fit × 0.4) + (Constraint fit × 0.2).
Exclude anything scoring under 5 overall — don't pad the list with weak matches.

Sort descending by overall score. Cap at the requested count (default 10).

---

## Step 4 — Present the shortlist

```
## 🔍 Job Search — [role]  •  [location]  •  [date]

Searched: LinkedIn, [ATS platforms found] — [N] postings found, [N] after dedupe, [N] after
constraint filtering.

| # | Company | Role | Fit | Posted | Salary | Link |
|---|---|---|---|---|---|---|
| 1 | Acme Corp | Staff Backend Engineer | 9.2/10 | 3 days ago | $180–220k | [Apply →](url) |
| 2 | Widgets Inc | Senior Platform Engineer | 8.1/10 | 1 week ago | Not disclosed | [Apply →](url) |

⚠️ Possibly stale (posted 5+ weeks ago, include only if nothing fresher fit as well):
| # | Company | Role | Fit | Posted | Link |
|---|---|---|---|---|

💡 Angles that came up empty: [e.g. "no results for 'remote EU only' — widened to include UK-based roles"]
```

Then ask: **"Want me to add all of these to the tracker as Shortlisted, and tailor a resume for
any of them right now?"**

**If all searches returned nothing above the score-5 threshold:** say so directly, list what was
tried, and suggest the most likely fix (widen location, drop a must-have, adjust title) rather than
showing an empty or padded table.

---

## Step 5 — Handle the pursue decision

- **If the user picks specific roles to pursue:** for each one, invoke `resume-tailor` with that
  JD (pass the full JD text you already fetched — don't make the user re-paste it). Offer
  `github-project-picker` too if the role has a strong technical-portfolio angle. Once
  resume-tailor saves its file, record that path in the tracker row.
- **If the user says "add them all" without picking:** add every shortlisted role to the tracker
  as `Shortlisted` and stop — don't run resume-tailor on all of them unprompted, that's a lot of
  file generation for roles the user hasn't committed to.
- **If the user says "just show me, don't track yet":** skip Step 6 for this run.

---

## Step 6 — Update the tracker

Read the current tracker (or start fresh if none exists) and:

1. Add a row for every newly shortlisted role (status `Shortlisted`, found date = today).
2. Update status/resume-path/notes for any role touched in Step 5.
3. Apply any status update from a Step-0 short-circuit (user reported a status change directly).
4. **Staleness check** — scan existing rows:
   - `Shortlisted` for 10+ days with no status change → flag: "Still shortlisted, not applied —
     decide or drop?"
   - `Applied` for 10+ days with no response logged → flag: "No response in 10+ days — worth a
     follow-up note to the recruiter?"
   - Surface these flags in your reply; don't just silently note them in the file.

### Tracker format

```markdown
# Job Search Tracker

| Company | Role | Status | Fit | Found | Applied | Follow-up | Resume | Link | Notes |
|---|---|---|---|---|---|---|---|---|---|
| Acme Corp | Staff Backend Engineer | Applied | 9.2 | 2026-07-01 | 2026-07-02 | 2026-07-16 | [Resume-Acme-Staff.md](~/Desktop/Resume-Acme-Staff.md) | [JD](url) | Referral from J. |
```

**Status values (in order):** `Shortlisted` → `Applied` → `Phone Screen` → `Interviewing` →
`Offer` / `Rejected` / `Withdrawn`. Never skip backwards except to `Withdrawn` or `Rejected`.

**Follow-up column:** when status becomes `Applied`, set follow-up to +14 days unless the posting
or user says otherwise. Recompute if the user reports a later interaction (e.g. a phone screen
resets the follow-up clock to +7 days from that event).

Save the file back to `~/Desktop/Job-Search-Tracker.md`, preserving all rows not touched this run.

---

## Key rules

- **The tracker is the source of truth.** Always read it before searching and write it back before
  finishing — never let it drift out of sync with what you just told the user.
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
