# Expense Analyzer v2 — Design Spec

**Date:** 2026-04-29  
**Status:** Approved

## Overview

Upgrade the expense-analyzer skill from markdown output to an Excel workbook. Single CSV in, `.xlsx` out. Charts embedded in the sheets where they are relevant. No multi-month history or year-over-year comparisons in this version.

## Goals

- Replace the markdown report with a `.xlsx` workbook
- Embed charts in relevant sheets (not a standalone Trends sheet)
- Keep all existing analysis logic unchanged

## Non-Goals

- Multi-month trends or history comparison
- Year-over-year comparisons
- Writing into the existing `Money_Flow_2026_Pro.xlsx`

---

## Architecture

Single entry point: `analyze.py`. Same CLI as v1 minus `--compare`:

```
analyze.py <csv_path> [--month YYYY-MM]
```

Swaps `print()` markdown output for an openpyxl workbook saved to disk.

**Dependency:** `openpyxl` — pip-installed at skill setup time, no venv needed.

---

## Excel Workbook Structure

Five sheets, in this order:

### 1. Summary
- Total spend, transaction count
- Top category by spend
- Count of flagged transactions

### 2. By Category
- Table: Category | Total (£) | # Transactions | Avg (£)
- Sorted by total descending
- **Bar chart** embedded below the table: X = categories, Y = £ total. One bar per category.

### 3. Top Transactions
- Top 10 transactions by amount
- Columns: Date | Merchant | Category | Amount (£) | Original Amount + Currency (if non-GBP)

### 4. Flagged
- Unusual/large transactions with reasons
- Columns: Date | Merchant | Category | Amount (£) | Reason
- Note if none flagged

### 5. Transactions
- Full line-item breakdown, sorted by category then amount descending
- Columns: Category | Date | Merchant | Amount (£) | Original Amount + Currency (if non-GBP)

---

## Flagging Logic

Unchanged from v1:
- Large spend: amount > £100
- Outlier: amount ≥ £50 AND > 2× category average (requires ≥ 3 transactions in category)

---

## SKILL.md Changes

1. Add a step to install openpyxl: `pip install openpyxl` (one-time, no venv).
2. Remove `--compare` from invocation instructions.
3. Change output path from `.md` to `.xlsx`: `finence/reports/expense-report-YYYY-MM.xlsx`.
4. Reply step unchanged: 2–3 sentences (total spend, top category, flagged count).

---

## Output

File saved to: `finence/reports/expense-report-YYYY-MM.xlsx`

Script prints the saved path to stdout on success. Errors go to stderr with non-zero exit code.
