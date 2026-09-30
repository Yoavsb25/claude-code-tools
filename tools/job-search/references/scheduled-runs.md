# Scheduled runs: Job Radar

Since 2026-09-29 the daily run is the **Job Radar refresh**, not an unattended Claude session.

- `~/Library/LaunchAgents/com.yoavsborovsky.jobradar.plist` runs
  `/opt/homebrew/bin/python3 scripts/radar.py refresh` at 07:00 (launchd runs a missed slot on
  wake if the Mac was asleep). Log: `~/job-search-data/logs/radar.log`.
- It is plain Python (stdlib + `job_tool.py` fetchers): no LLM, no `claude` CLI, so there is no
  OAuth session to expire. State lives in `~/job-search-data/`, outside `~/Desktop`, because
  macOS TCC blocks launchd jobs from reading the Desktop (this broke every run in Sept 2026).
- Output: `radar.json` (every London / UK-remote posting from the `companies.json` watchlist plus
  a LinkedIn sweep, enriched with years required, level, role family, salary) and
  `coverage.json` (per-company fetch result, LinkedIn stats, discovered companies).

The Radar never applies, messages, or writes to the tracker on its own; Yoav browses and saves.

## Retired: the unattended Claude pipeline

`scripts/run_daily.sh` + `com.yoavsborovsky.jobsearch.daily.plist` (plist backed up at
`~/job-search-data/retired-com.yoavsborovsky.jobsearch.daily.plist`) ran the full Stage 0–7
pipeline via `claude -p`. It was retired because it failed on OAuth expiry and TCC, and because a
30-row LLM shortlist hid the other ~4,000 fetched postings. Full LLM scoring is still available
interactively through this skill.
