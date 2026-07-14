#!/bin/bash
# Runs the job-search skill's full daily pipeline unattended via the Claude Code CLI.
# Invoked by ~/Library/LaunchAgents/com.yoavsborovsky.jobsearch.daily.plist every morning.
set -uo pipefail

CLAUDE_BIN="/Users/yoavsborovsky/.local/bin/claude"
LOG_DIR="/Users/yoavsborovsky/Desktop/Job-Search/logs"
LOG_FILE="$LOG_DIR/daily-run-$(date +%F).log"
mkdir -p "$LOG_DIR"

PROMPT='Run the job-search skill'"'"'s full daily pipeline (Stages 0 through 7) exactly as described in ~/.claude/skills/job-search/SKILL.md'"'"'s "Scheduled daily runs" section: load the profile and tracker, search for matching openings, dedupe and score them, build the shortlist split into Public and Private/non-public company tables with a Skills Fit column, run Stage 4.5 connections enrichment against ~/Desktop/Job-Search/connections.json, persist everything scoring above threshold to the tracker as Shortlisted status (do not wait for approval - this is an unattended scheduled run), and export the results to an Excel workbook via ~/.claude/skills/job-search/scripts/export_xlsx.py using the venv at ~/.claude/skills/job-search/.venv. This is a fully unattended run: do not ask clarifying questions, do not enter plan mode, and do not wait for user confirmation at any stage - make reasonable default decisions and proceed. Stay scoped to job-search actions only: read/write files under ~/Desktop/Job-Search and ~/.claude/skills/job-search, run job_tool.py/export_xlsx.py, and use WebSearch/WebFetch for job listings. Do not run git commands, do not send messages or emails, do not modify any other files or directories. At the end, print a concise plain-text summary: number of new roles found (split public/private), the Excel file'"'"'s full path, and any tracker rows flagged as stale.'

{
  echo "=== job-search daily run: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  "$CLAUDE_BIN" -p "$PROMPT" \
    --dangerously-skip-permissions \
    --model claude-sonnet-5 \
    --add-dir /Users/yoavsborovsky/Desktop/Job-Search \
    --add-dir /Users/yoavsborovsky/.claude/skills/job-search
  echo "=== exit code: $? ==="
} >> "$LOG_FILE" 2>&1
