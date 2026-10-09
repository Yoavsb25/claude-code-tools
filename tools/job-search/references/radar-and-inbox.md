# Job Radar, the Cockpit page and inbox sync

Read from SKILL.md when the user asks about the radar, the Cockpit page, the 07:00 job or employer emails.

## The 07:00 run

Since 2026-09-29 the daily run is the **Job Radar refresh**, not an unattended Claude session.

- `~/Library/LaunchAgents/com.example.jobradar.plist` runs
  `/opt/homebrew/bin/python3 scripts/radar.py daily` at 07:00 (launchd runs a missed slot on
  wake if the Mac was asleep). Log: `~/job-search-data/logs/radar.log`.
- `daily` = radar refresh, then inbox sync (`inbox.py`, read-only IMAP; ghosting only after a
  successful sync), then a git commit of `~/job-search-data`. A failing step is logged and the
  next one still runs.
- It is plain Python (stdlib + `job_tool.py` fetchers): no LLM, no `claude` CLI, so there is no
  OAuth session to expire. State lives in `~/job-search-data/`, outside `~/Desktop`, because
  macOS TCC blocks launchd jobs from reading the Desktop (this broke every run in Sept 2026).
- Output: `radar.json` (every London / UK-remote posting from the `companies.json` watchlist plus
  a LinkedIn sweep, enriched with years required, level, role family, salary) and
  `coverage.json` (per-company fetch result, LinkedIn stats, discovered companies).

Nothing ever applies or sends messages. The only automatic tracker writes come from inbox sync
(unambiguous email matches, undoable) and ghosting; the user browses the Radar and saves roles themselves.

## Job Radar (daily, browsable)

Every morning `scripts/radar.py refresh` (launchd, plain Python, no LLM) collects every London /
UK-remote posting from the `companies.json` watchlist plus a LinkedIn sweep into
`~/job-search-data/radar.json`, with years required (pulled from the JD text, with the evidence
sentence), level, role family and salary. `radar.py status` prints a summary; coverage per company
is in `coverage.json`. the user browses it with `radar.py serve` (local page at http://127.0.0.1:8765,
refreshes in the background if data is over 12h old).

The page is the **Job Cockpit** (`cockpit.py` builds its data; served at `/api/cockpit`):
- **Today** (default): weekly 3/2/1 tiles plus a public-proof log (`cockpit_state.json`), emails
  that need a reply ("✓ Handled"), emails to sort ("It's <company>" / another row / Ignore), follow-ups
  due, and the last 7 days of automatic status changes with Undo; "Sync inbox now" runs inbox sync.
- **Roles**: the radar. "☆ Save as…" Tier 1 (tailor + warm path) or Tier 2 (fast apply) adds a
  Shortlisted row with a guessed positioning; Hide choices live in `radar_state.json`.
- **Pipeline**: every tracker row with status / tier / channel / positioning editable in place
  ("confirm" accepts a guessed positioning); a row opens to its history, LinkedIn connections at the
  company, and a "Copy /resume-tailor command" button.
- **Insights**: funnel (applied → heard back → conversations → interviewing → offers), median time to
  a response, and conversation rate by channel, positioning and tier (groups under 5 marked "few").
Page edits are limited to status, tier, channel, positioning, notes and follow-up date.

When the user asks "what's new" or wants a shortlist, start from `radar.json` (filter: not closed,
`years_min` ≤ 3 or unknown, role_family not Non-tech) instead of re-fetching every source. Never
apply, send messages, or add tracker rows without them choosing the role.

---

## Inbox sync (daily, read-only)

`scripts/inbox.py` reads Gmail over IMAP and keeps the tracker in step with what employers sent.
It runs inside `radar.py daily` at 07:00; `inbox.py sync [--days N] [--dry-run]` runs it by hand.
The mailbox is opened read-only and fetched with `BODY.PEEK`: nothing is marked read, moved or
sent. Credentials: a Gmail app password in the macOS Keychain (service `job-search-imap`;
`inbox.py setup` prints the steps).

Only unambiguous matches (company named by the sender or subject, one row fits) change the
tracker: confirmation → `Applied`, rejection → `Rejected`, invite/reply → `Responded` plus an
action item. Everything else waits in the review queue. When the user asks "anything from employers?"
or "what do I need to reply to?", run `inbox.py actions` and `inbox.py review`; settle review
items with `inbox.py resolve <msg_id> --row ID` or `--ignore`, and mark replies handled with
`inbox.py done <msg_id>`. A status update the user tells you directly still goes through
`tracker upsert`.

`radar.py daily` commits the state dir after each run when it is a git repo, so
`git -C ~/job-search-data log -p tracker.json` shows every automatic change.

## Retired: the unattended Claude pipeline

`scripts/run_daily.sh` + `com.example.jobsearch.daily.plist` (both deleted; see git history) ran the full Stage 0–7
pipeline via `claude -p`. It was retired because it failed on OAuth expiry and TCC, and because a
30-row LLM shortlist hid the other ~4,000 fetched postings. Full LLM scoring is still available
interactively through this skill.
