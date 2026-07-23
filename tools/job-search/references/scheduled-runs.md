# Scheduled daily runs

Yoav runs this skill every morning via a **local scheduled job**, not a hosted cloud agent —
hosted cloud routines (the `schedule` skill) run in Anthropic's cloud with no access to local
files, so they can't reach `~/Desktop/Job-Search/`, the local `job_tool.py`/`export_xlsx.py`
scripts, or the local `.venv`. Instead:

- `~/Library/LaunchAgents/com.yoavsborovsky.jobsearch.daily.plist` — a `launchd` agent that fires
  `scripts/run_daily.sh` daily at 08:00.
- `scripts/run_daily.sh` invokes the local `claude` CLI directly (`claude -p "<prompt>"
  --dangerously-skip-permissions --model claude-sonnet-5 --add-dir ~/Desktop/Job-Search --add-dir
  ~/.claude/skills/job-search`), logging to `~/Desktop/Job-Search/logs/daily-run-<date>.log`.

**Known failure mode:** this setup authenticates via the CLI's own local OAuth login session.
`launchd` runs it non-interactively, so if that session expires, there's no browser/TTY available
to refresh it — the run fails with `Failed to authenticate: OAuth session expired and could not be
refreshed` and stays broken until Yoav manually runs `claude login` again interactively. There is
currently no automatic recovery from this — if the daily logs go quiet or start showing auth
errors, that's the first thing to check.

## What the scheduled run should do

The scheduled prompt should run the full Stage 0–7 pipeline exactly as an interactive request
would (load profile, search, dedupe/score, present the two-table shortlist, connections
enrichment, export to Excel) — it should NOT skip stages just because no human is watching in real
time. Since there's no one to answer Stage 4's "want me to track these?" question synchronously,
the scheduled run should default to **Stage 6 Persist as `Shortlisted`** for everything above the
score threshold (equivalent to the user having said "add them all") rather than blocking on an
answer that will never come, and should skip Stage 5's resume-tailor hand-off entirely (that step
requires an explicit human decision on which role to pursue). Use whatever wrap-up/notification
mechanism the scheduled run has to leave a clear one-message summary — new roles found, the Excel
file's path, and any tracker rows that came back stale — so Yoav can catch up in one read without
re-running anything.
