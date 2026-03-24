---
name: trip-expense-report
description: Produce a markdown spending summary for a specific trip or date range from the Wise transaction CSV. Use when the user invokes /trip-expense-report or asks to summarise spending for a trip or date range.
disable-model-invocation: true
---

# Trip Expense Report

Produces a spending breakdown for a trip or date range from your Wise transaction history.

## Step 1: Gather inputs

Ask the user for (if not already provided):
1. **Trip name / label** — e.g., "Milan", "London Feb", "Ski weekend"
2. **Start date** — inclusive, format YYYY-MM-DD or DD Mon YYYY
3. **End date** — inclusive

If the user has specified a particular CSV file to use, use that. Otherwise find the latest:

```bash
ls -t <your-project-root>/finence/transaction-history*.csv 2>/dev/null | head -1
```

**If no CSV found:** stop and say "No transaction history CSV found in finence/. Please export your Wise history."

## Step 2: Read and filter the CSV

Read the CSV. The relevant columns are:
- `Created on` — transaction datetime (filter by date range)
- `Direction` — OUT = spending, IN = income
- `Source amount (after fees)` — amount in source currency
- `Source currency` — currency of the transaction
- `Target name` — merchant / recipient name
- `Target amount (after fees)` — amount received (for FX transactions)
- `Target currency` — currency received
- `Source fee amount` — FX fee paid
- `Source fee currency` — currency of the fee
- `Category` — Wise category label

Filter to rows where `Created on` falls within the start and end dates (inclusive). The `Created on` column contains a full datetime (e.g., `2026-03-14 09:23:11`). Compare only the date portion (first 10 characters, `YYYY-MM-DD`) against the start and end dates.

Exclude NEUTRAL direction rows from spending totals (these are internal currency conversions).

**If no transactions found:** tell the user and suggest widening the date range.

## Step 3: Produce the report

Calculate:
- **Total spent (GBP):** sum of `Source amount (after fees)` for all OUT transactions where `Source currency` is GBP, plus the GBP-equivalent of non-GBP OUT transactions (calculated as: Source amount ÷ Exchange rate, or derived from Target amount if Target currency is GBP). Include all OUT transactions in the total.
- **Total IN (GBP):** sum of Source amount where Direction=IN and Source currency=GBP
- **By category:** group OUT transactions by Category, sum amounts in GBP (or GBP equivalent), sort descending
- **FX costs:** sum of all `Source fee amount` where fee > 0, grouped by fee currency. FX fees are charged in the source currency. For a GBP account, all fees will typically be in GBP. Sum `Source fee amount` where it is > 0. In the "Currencies used" line, list the distinct `Target currency` values from non-GBP OUT transactions in the period.
- **Top 5 transactions:** the 5 largest single OUT transactions by GBP amount

Format the report as:

```markdown
# Trip Expense Report: <label>
**Period:** <start date> – <end date>
**Source:** <CSV filename>
**Generated:** <today's date>

---

## Summary
| | |
|---|---|
| Total spent (GBP) | £X.XX |
| Total received (GBP) | £X.XX |
| FX fees paid | £X.XX |
| Transactions | X |

---

## Spending by Category
| Category | Amount |
|----------|--------|
| Transport | £X.XX |
| Eating out | £X.XX |
(sorted descending, GBP or GBP-equivalent)

---

## Day-by-Day
List transactions in chronological order within each day (by the time component of `Created on`).
### DD Mon YYYY
- Merchant — £X.XX (or X.XX EUR if non-GBP)
(list each OUT transaction per day)

---

## FX Costs
Total fees on foreign currency transactions: £X.XX
Currencies used: EUR, USD, ...
(If no FX fees, write "No foreign currency fees in this period.")

---

## Top 5 Transactions
| Date | Merchant | Amount |
|------|----------|--------|
(5 largest OUT transactions by GBP amount)
```

## Step 4: Save and display

Determine filename: `trip-report-<label-lowercase-hyphenated>-YYYY-MM-DD.md` (using today's date). To form the label slug: lowercase the label, replace spaces with hyphens, remove any characters that are not alphanumeric or hyphens.

If that filename already exists in the project root, run:
```bash
ls <your-project-root>/trip-report-*.md 2>/dev/null
```
Inspect the results and choose the lowest suffix not already present — append `-2`, then `-3`, etc.

Save the report to: `<your-project-root>/<filename>`

Display the full report inline, then say: "Report saved to `<filename>`."
