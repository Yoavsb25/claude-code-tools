# job-search

Runs the end-to-end job hunt: finds current openings matching a target role/location, ranks them
by fit against Yoav's profile, tracks every application in a local markdown tracker, and hands off
to `resume-tailor` (and `github-project-picker`) for any role worth pursuing.

## How it works

1. **Load the tracker** — reads `~/Desktop/Job-Search-Tracker.md` so it never re-surfaces a role
   already tracked, applied to, or rejected.
2. **Gather criteria** — target role(s), location/remote, seniority, must-haves, deal-breakers.
3. **Search** — runs varied `WebSearch` queries across LinkedIn, Indeed, and ATS platforms
   (Greenhouse, Lever, Ashby), then `WebFetch`es promising postings for full JD text, posted date,
   and salary.
4. **Dedupe and score** — merges duplicate postings, drops anything already tracked or hitting a
   deal-breaker, and ranks the rest on role fit, requirements fit, and constraint fit.
5. **Present a shortlist** and, for roles the user decides to pursue, kicks off `resume-tailor`
   (and optionally `github-project-picker`) using the JD already fetched.
6. **Update the tracker** — adds new rows, updates status/resume path, and flags stale
   applications or shortlisted roles that need a decision.

## Usage

Copy `SKILL.md` into `~/.claude/skills/job-search.md` (or install via the registry), then say:

> "Find me some jobs — Staff Backend Engineer, remote"
> "What's out there for a senior platform role this week?"
> "I applied to the Acme Corp role, update the tracker"
> "Move the Widgets Inc application to interviewing"

## Output

- A ranked shortlist table printed in the conversation.
- A running tracker at `~/Desktop/Job-Search-Tracker.md` (company, role, status, fit score, key
  dates, resume file, JD link, notes).
- Tailored resumes via `resume-tailor` for any role the user chooses to pursue.

## Requirements

No external tools or API keys required — search relies on `WebSearch`/`WebFetch`. Works best
alongside `resume-tailor` and `github-project-picker` for the hand-off step.

> **Note:** The SKILL.md references Yoav's local work documentation and resume-tailor's file
> paths. Adapt the profile path in Step 3 and the tracker location to your own setup before use.
