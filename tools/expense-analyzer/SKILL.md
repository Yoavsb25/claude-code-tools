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
   - Before a Monzo report, make the data fresh: run `cd ~/GitHub/wealth-dashboard && .venv/bin/python -m wealth.sync --if-stale` (does nothing if today's sync already ran; launchd runs it at 07:00 and at login). Then check `sqlite3 -readonly ~/GitHub/wealth-dashboard/data/wealth.db "SELECT status, message, started_at FROM sync_runs WHERE account_id='monzo' ORDER BY id DESC LIMIT 1"`. If it isn't `ok`, tell the user why (`needs_reauth`: Reconnect on the dashboard's Accounts page, then approve in the Monzo app) and that the report stops at the last good sync.

2. **Infer the month filter** — in order of priority:
   - If the user names a month explicitly (e.g. "March", "last month"), use that.
   - Otherwise, if the filename contains a month name (e.g. `april_transactions.csv`, `march-2026.csv`), infer from it.
   - If no month can be inferred, omit `--month` to analyze the full file.
   - Map to `--month YYYY-MM` using the current year (e.g. "april" → `--month 2026-04`).

3. **Previous month for comparison** — with `--month`, pass `--compare auto`. It uses last month's saved report (`expense-report-YYYY-MM.md` in Budget & Reports) when it exists, because that already combines every source and any manual exclusions; otherwise it falls back to the same source (Monzo). Never use `--compare monzo` when the previous month mixed sources (e.g. October 2026): it only sees the Monzo slice. Without a saved report for a Wise month, look for the prior month's CSV in the same directory and pass `--compare <path>`.

4. **Run the script** (stdlib only, no venv needed):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/analyze.py" <file_path|monzo> [--month YYYY-MM] [--compare auto|<prev_report.md>|<prev_csv_path>|monzo]
   ```

5. **Save the report**:
   - If a month filter was used: `~/Documents/2 Money/Budget & Reports/expense-report-YYYY-MM.md` (e.g. `expense-report-2026-04.md`)
   - Otherwise: `~/Documents/2 Money/Budget & Reports/expense-report-YYYY-MM-DD.md` (today's date as fallback)

6. **Reply** with a short summary: total spend, top category, and one notable flagged item (if any). Just 2–3 sentences — the detail is in the file. Also mention, if present: anything under **Left Out** that might be real spending (ask; if yes, re-categorise it on the dashboard's Spending page or with `wealth.db.set_merchant_rule`, then re-run), and any **Possibly Missing Spend** category (suggest checking Wise).

## What the script handles

Monzo (`monzo` source):
- Applies the dashboard's merchant re-categorisation rules (e.g. Trading 212 → investment)
- Skips pot moves, transfers between own accounts, incoming money, and non-spending categories (investment, income, savings, not_spending), listing each skipped non-zero payment under **Left Out**
- Counts Monzo's "general" as **Uncategorised** (it's real spend Monzo couldn't classify, unlike Wise's "General")
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

1. Summary (total spend; vs-previous-month delta if `--compare` was used; for Monzo, "Data through" the last successful sync while the month is in progress)
2. By Category table (total / optional delta vs prev month / count / avg)
3. Top 10 transactions
4. Possibly Missing Spend (a usual category, avg ≥ £100/month and not Trips, below 60% of its pro-rated average)
5. Flagged unusual expenses
6. Left Out (Monzo: payments not counted, with the reason)
7. Full per-category breakdown with individual line items
