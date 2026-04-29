# expense-analyzer — Wise/Revolut Expense Analyzer

Processes Wise or Revolut CSV transaction exports and produces a detailed markdown expense report with category totals, top transactions, month-over-month comparison, and flagged unusual spends.

## What it does

- Filters to outgoing transactions only (skips incoming transfers, rewards, conversions)
- Deduplicates multi-currency rows for the same transaction
- Converts non-GBP amounts using the exchange rate in the export
- Skips internal categories (`Money added`, `Rewards`, `General`) and sub-penny amounts
- Flags large transactions (>£100) and anything ≥£50 AND >2× its category average
- Optional month-over-month comparison via `--compare`

## Report sections

1. Summary (total spend; delta vs previous month if `--compare` used)
2. By Category table (total / optional delta / count / avg)
3. Top 10 transactions
4. Flagged unusual expenses
5. Full per-category breakdown with individual line items

## Installation

Copy both files into your project's `.claude/skills/expense-analyzer/`:

```
.claude/skills/expense-analyzer/SKILL.md
.claude/skills/expense-analyzer/scripts/analyze.py
```

## Usage (via Claude skill)

Drop a Wise CSV export into your project (e.g. `finence/april_transactions.csv`) then say:

> "Analyze my expenses" or "expense report for April"

Claude will run the script and save a report to `finence/reports/expense-report-YYYY-MM.md`.

## Direct usage

```bash
python3 .claude/skills/expense-analyzer/scripts/analyze.py <csv_path> [--month YYYY-MM] [--compare <prev_csv_path>]
```

## Dependencies

Python stdlib only — no venv or pip install needed.
