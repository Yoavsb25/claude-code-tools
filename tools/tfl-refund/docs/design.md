# TfL Refund Email Generator — Design Spec

**Date:** 2026-03-24
**Status:** Live

---

## Overview

A Claude skill (`/tfl-refund`) that reads a completed Oyster audit report and generates a ready-to-send dispute email for TfL Customer Services. It extracts only the genuinely claimable items from the report's `## Claimable Overcharges` section and formats them into a professional, copy-paste email.

---

## Goals

- Read the most recent (or named) Oyster audit report from `oyster-history/reports/`
- Extract claimable overcharges from the structured `## Claimable Overcharges` section
- Generate a complete, copy-paste email with all journey details filled in
- State the TfL submission method and 8-week claim window

## Non-Goals

- Submitting the claim automatically (user sends manually)
- Reading raw Oyster CSVs directly (always reads from audit report)
- Tracking whether a claim was sent or refunded

---

## Architecture

```
User invokes /tfl-refund [optional: report filename]
        ↓
[Skill: tfl-refund]
  ├── Find report in oyster-history/reports/ (latest or named)
  ├── Parse ## Claimable Overcharges section
  └── Generate dispute email
        ↓
Output: fenced code block with ready-to-send email
```

---

## Report Location

Reports live in `oyster-history/reports/oyster-audit-report-YYYY-MM-DD.md`.

The skill finds the most recent by sorting on filename (date-prefixed names sort correctly lexicographically).

---

## Email Structure

- **To:** tfl-contactus@tfl.gov.uk
- **Subject:** `Oyster railcard discount not applied — refund request [cards ...XXXX, ...XXXX] — £X.XX`
- **Body:** Formal dispute letter with journey table, total, and card details extracted from the report
- **Placeholder:** `[Your name]` — only field the user must fill manually

Card identifiers, railcard type, journey table, and total are all auto-populated from the report's `## Claimable Overcharges` section.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| No report found in `oyster-history/reports/` | Stop; tell user to run `/oyster-audit` first |
| Named report doesn't exist | List available reports; ask user to confirm |
| `## Claimable Overcharges` says "Nothing to claim." | Stop; inform user there is nothing to claim |
| Section missing (old report format) | Fall back to Sections 1 + 4; confirm items with user before generating email |

---

## Key Files

| Path | Purpose |
|---|---|
| `oyster-history/reports/oyster-audit-report-YYYY-MM-DD.md` | Source of claimable overcharges |
