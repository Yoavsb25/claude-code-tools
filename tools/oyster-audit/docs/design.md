# Oyster Audit — Design Spec

**Date:** 2026-03-24
**Status:** Live

---

## Overview

A Claude skill (`/oyster-audit`) that runs a Python audit script against TfL Oyster CSV exports and a Wise bank statement, then writes a dated markdown report summarising fare discrepancies, incomplete journeys, and claimable overcharges.

---

## Goals

- Accept Oyster CSV exports from TfL and a Wise transaction CSV
- Detect fares charged without railcard discount applied
- Detect incomplete journeys (tap-in only, max fare charged)
- Match Oyster top-ups to card statement entries
- Write a structured, dated markdown report to `oyster-history/reports/`
- Produce a `## Claimable Overcharges` table for downstream use by `/tfl-refund`

## Non-Goals

- Filing refund claims (handled by `tfl-refund` skill)
- Real-time fare lookup (uses hardcoded TfL fare tables in audit script)
- Contactless payment card auditing

---

## Architecture

```
User invokes /oyster-audit
        ↓
[Skill: oyster-audit]
  ├── Find latest Oyster CSV(s) in oyster-history/
  ├── Find latest Wise CSV in finence/
  ├── Verify audit.py exists at expected plugin path
  └── Run audit.py with --oyster, --statement, --railcard flags
        ↓
[Python: audit.py] (lives in tube-fare-auditor plugin)
  ├── Parse Oyster journey history
  ├── Check each fare against TfL fare tables + railcard rules
  ├── Match top-ups to Wise statement entries
  └── Write audit_results.json to /tmp/tube_audit_output/
        ↓
[Skill resumes]
  ├── Read audit_results.json
  └── Write oyster-audit-report-YYYY-MM-DD.md → oyster-history/reports/
```

---

## Components

### `audit.py` (tube-fare-auditor plugin)
- Located at `~/.claude/skills/tube-fare-auditor/scripts/audit.py`
- CLI args: `--oyster <csv>` (repeatable), `--statement <csv>`, `--railcard <type>`, `--output <dir>`
- Writes `audit_results.json` to the output dir
- Default railcard: `26-30`

### `oyster-audit` skill
- Lives at `.claude/skills/oyster-audit/SKILL.md`
- Orchestrates: find files → verify script → run → write report
- Supports `--railcard <type>` arg override
- Supports "audit all" to include all CSVs from `oyster-history/`

---

## Output Format

Report saved to `oyster-history/reports/oyster-audit-report-YYYY-MM-DD.md`.

Sections:
1. Summary
2. Fare Discrepancies
3. Incomplete Journeys
4. Statement vs Top-Ups
5. Potential Refunds
6. Recommendations
7. Claimable Overcharges (structured table — consumed by `tfl-refund`)

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| No Oyster CSV found | Stop; prompt user to export from oyster.tfl.gov.uk |
| No Wise CSV found | Continue without `--statement`; note to user |
| `audit.py` not found at expected path | Stop; tell user to check tube-fare-auditor plugin installation |
| `audit_results.json` missing after run | Show directory listing; stop |
| Report filename collision (same date run twice) | Append `-2`, `-3` suffix |

---

## Key Files

| Path | Purpose |
|---|---|
| `oyster-history/*.csv` | Oyster card exports from TfL |
| `finence/transaction-history*.csv` | Wise bank statement export |
| `oyster-history/reports/oyster-audit-report-YYYY-MM-DD.md` | Audit report output |
| `~/.claude/skills/tube-fare-auditor/scripts/audit.py` | Core audit logic (plugin) |
