---
name: expense-analyzer
description: Manually invoked expense analysis skill. Use when the user says "analyze my expenses", "expense report", "what did I spend on", "monthly spending", "show me my expenses", or references a transaction CSV file for analysis. Reads Monzo (joint account, auto-synced via the wealth dashboard, no download) and Wise/Revolut CSV exports, and produces a detailed markdown report with category totals, top transactions, and flagged unusual or large spends.
---

# Expense Analyzer

Generate a markdown expense report from Monzo (via the wealth dashboard DB) or a Wise CSV transaction export.

## Steps

1. **Identify the source**:
   - **November 2026 onwards → Monzo (default).** Use the literal source `monzo`. It reads the joint Monzo account from the wealth dashboard's DB (`~/GitHub/wealth-dashboard/data/wealth.db`, read-only; override with `WEALTH_DB`), which syncs daily at 07:00. No download needed. Only the joint account is used; the personal one is unused.
   - **Earlier months → Wise CSV.** Monthly CSVs live in `~/Documents/2 Money/Accounts/Wise/Monthly Exports/`; the full export is `~/Documents/2 Money/Accounts/Wise/Wise_Transaction_History.csv`. If unclear, ask.
   - **Wise export type:** the "statement" CSV (signed amounts, no Direction or Category columns) won't parse, and the script finds nothing. Ask for the "transaction history" export instead of converting it.
   - **Reimbursed work trips:** ask whether any trips (clusters of foreign-currency payments) were reimbursed by an employer. Exclude those items, and don't count the reimbursement as income in the month it arrives.
   - October 2026 is mixed: Wise plus Monzo joint from 5 Oct. Run both and combine if asked.
   - Before a Monzo report, check freshness: `grep monzo ~/GitHub/wealth-dashboard/data/sync.log | tail -1`. If it isn't `ok` from today, tell the user (usually: Reconnect on the dashboard's Accounts page, then approve in the Monzo app).

2. **Infer the month filter** — in order of priority:
   - If the user names a month explicitly (e.g. "March", "last month"), use that.
   - Otherwise, if the filename contains a month name (e.g. `april_transactions.csv`, `march-2026.csv`), infer from it.
   - If no month can be inferred, omit `--month` to analyze the full file.
   - Map to `--month YYYY-MM` using the current year (e.g. "april" → `--month 2026-04`).

3. **Previous month for comparison** — if the previous month is also Monzo, pass `--compare monzo`. Otherwise **check for a previous month's CSV** — look in the same directory for a file named after the prior month (e.g. if current is `april_transactions.csv`, look for `march_transactions.csv`). If found, pass it with `--compare <path>` for month-over-month comparison.

4. **Run the script** (stdlib only, no venv needed):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/analyze.py" <file_path|monzo> [--month YYYY-MM] [--compare <prev_csv_path|monzo>]
   ```

5. **Save the report**:
   - If a month filter was used: `~/Documents/2 Money/Budget & Reports/expense-report-YYYY-MM.md` (e.g. `expense-report-2026-04.md`)
   - Otherwise: `~/Documents/2 Money/Budget & Reports/expense-report-YYYY-MM-DD.md` (today's date as fallback)

6. **Reply** with a short summary: total spend, top category, and one notable flagged item (if any). Just 2–3 sentences — the detail is in the file.

## What the script handles

Monzo (`monzo` source):
- Applies the dashboard's merchant re-categorisation rules (e.g. Trading 212 → investment)
- Skips pot moves, transfers between own accounts, incoming money, and non-spending categories (investment, general, income, savings)
- Cancels a refund against the charge it reverses (same merchant, exact amount)
- Maps Monzo categories to the Wise-era names (eating_out → Eating out, holidays → Trips, transfers → Personal transfers…) so months compare cleanly
- Avg/month history combines the Wise CSVs and Monzo

Wise CSV:

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
