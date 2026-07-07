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
3. **Search** — runs varied `WebSearch` queries across LinkedIn, Indeed, and ATS platforms
   (Greenhouse, Lever, Ashby) — including industry-specific angles — then `WebFetch`es promising
   postings for full JD text, posted date, and salary.
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
```

State lives in `~/Desktop/Job-Search/` by default (override with `JOB_SEARCH_DIR`):
`profile.json`, `tracker.json` (source of truth), and the generated `Tracker.md`. Moving a row's
status to `Applied`, `Phone Screen`, or `Interviewing` auto-computes `applied_date`/`followup_date`;
`tracker list --stale-only` flags shortlisted roles idle 10+ days and applied/interviewing roles
past their follow-up date with no status change since.

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

Python 3.9+ (stdlib only, no dependencies). Search relies on `WebSearch`/`WebFetch`. Works best
alongside `resume-tailor` and `github-project-picker` for the hand-off step.

> **Note:** The SKILL.md references Yoav's local work documentation for requirements-fit scoring.
> Adapt the profile path in Stage 3 to your own setup before use.
