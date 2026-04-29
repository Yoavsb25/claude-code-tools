---
name: expense-analyzer
description: Manually invoked expense analysis skill. Use when the user says "analyze my expenses", "expense report", "what did I spend on", "monthly spending", "show me my expenses", or references a transaction CSV file for analysis. Processes Wise/Revolut CSV exports and produces a detailed markdown report with category totals, top transactions, and flagged unusual or large spends.
---

# Expense Analyzer

Generate a markdown expense report from a Wise CSV transaction export.

## Steps

1. **Identify the file** — the user will reference a CSV path. Default is `finence/transaction-history.csv`. If unclear, ask.

2. **Infer the month filter** — in order of priority:
   - If the user names a month explicitly (e.g. "March", "last month"), use that.
   - Otherwise, if the filename contains a month name (e.g. `april_transactions.csv`, `march-2026.csv`), infer from it.
   - If no month can be inferred, omit `--month` to analyze the full file.
   - Map to `--month YYYY-MM` using the current year (e.g. "april" → `--month 2026-04`).

3. **Check for a previous month's CSV** — look in the same directory for a file named after the prior month (e.g. if current is `april_transactions.csv`, look for `march_transactions.csv`). If found, pass it with `--compare <path>` for month-over-month comparison.

4. **Run the script** (stdlib only, no venv needed):
   ```bash
   python3 .claude/skills/expense-analyzer/scripts/analyze.py <file_path> [--month YYYY-MM] [--compare <prev_csv_path>]
   ```

5. **Save the report**:
   - If a month filter was used: `finence/reports/expense-report-YYYY-MM.md` (e.g. `expense-report-2026-04.md`)
   - Otherwise: `finence/reports/expense-report-YYYY-MM-DD.md` (today's date as fallback)

6. **Reply** with a short summary: total spend, top category, and one notable flagged item (if any). Just 2–3 sentences — the detail is in the file.

## What the script handles

- Filters to `Direction=OUT` only (skips incoming transfers, rewards, currency conversions)
- Deduplicates multi-currency rows for the same transaction (keeps GBP row when both EUR and GBP exist)
- Converts non-GBP amounts to GBP using the exchange rate in the export
- Skips `Money added`, `Rewards`, `General` categories (not real expenses)
- Skips transactions under £0.01 (foreign currency rounding artifacts and zero-cost charges)
- Flags large transactions (>£100) and anything ≥£50 AND >2× its category average

## Report sections

1. Summary (total spend; includes vs-previous-month delta if `--compare` was used)
2. By Category table (total / optional delta vs prev month / count / avg)
3. Top 10 transactions
4. Flagged unusual expenses
5. Full per-category breakdown with individual line items
