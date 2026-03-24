# trip-expense-report — Trip Spending Summary

Generates a markdown spending breakdown for any trip or date range from a Wise transaction CSV.

## What it produces
- Total spend by category
- Day-by-day transaction list
- FX fees paid
- Top 5 largest transactions

## Usage (via Claude skill)

1. Export your Wise transaction history as a CSV and place it in your project's `finence/` folder
2. Copy `SKILL.md` into your project's `.claude/skills/trip-expense-report/`
3. In Claude Code: `/trip-expense-report` — Claude will ask for trip name and date range
