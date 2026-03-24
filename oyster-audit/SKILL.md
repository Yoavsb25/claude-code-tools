---
name: oyster-audit
description: Run the TfL Oyster fare audit against the latest Oyster and Wise CSVs in this project, then save a timestamped markdown report. Use when the user invokes /oyster-audit or asks to audit their Oyster card charges.
disable-model-invocation: true
---

# Oyster Audit

Runs the TfL fare audit against your current Oyster and Wise CSV files and saves a report.

## Step 1: Find input files

Run these two commands to locate the latest files:

```bash
ls -t <your-project-root>/oyster-history/*.csv 2>/dev/null | head -1
```

```bash
ls -t <your-project-root>/finence/transaction-history*.csv 2>/dev/null | head -1
```

**If no Oyster CSV found:** stop and say "No Oyster CSV files found in oyster-history/. Please export your history from oyster.tfl.gov.uk."

**If no Wise CSV found:** continue without `--statement` and note this to the user.

If the user passed `--railcard <type>` as an argument, use that. Otherwise default to `26-30`.

If the user said "audit all" or "use all cards", include all CSVs from `oyster-history/` with one `--oyster` flag each.

Example with two cards:
```bash
python3 ~/.claude/skills/tube-fare-auditor/scripts/audit.py \
  --oyster <your-project-root>/oyster-history/card1.csv \
  --oyster <your-project-root>/oyster-history/card2.csv \
  --statement <latest-wise-csv> \
  --railcard <railcard-type> \
  --output /tmp/tube_audit_output/
```

## Step 2: Verify the audit script exists

```bash
ls ~/.claude/skills/tube-fare-auditor/scripts/audit.py 2>/dev/null
```

**If not found:** stop and say "audit.py not found at `~/.claude/skills/tube-fare-auditor/scripts/audit.py`. Check that the tube-fare-auditor plugin is installed."

## Step 3: Run the audit script

```bash
python3 ~/.claude/skills/tube-fare-auditor/scripts/audit.py \
  --oyster <latest-oyster-csv> \
  --statement <latest-wise-csv> \
  --railcard <railcard-type> \
  --output /tmp/tube_audit_output/
```

If no Wise CSV, omit `--statement`. If `audit.py` fails, show the error output directly and stop.

After the script completes, verify the output file exists:

```bash
ls /tmp/tube_audit_output/
```

If `audit_results.json` is not present, show the actual directory listing to the user and stop. Do not proceed to write the report if the JSON file is missing.

## Step 4: Determine the report filename

Use today's date: `oyster-audit-report-YYYY-MM-DD.md`.

Check if that file already exists in `oyster-history/reports/`:

```bash
ls <your-project-root>/oyster-history/reports/oyster-audit-report-*.md 2>/dev/null
```

If today's name is taken, append `-2`, `-3`, etc. until you find one that does not exist. Run the `ls` command above, inspect which dated filenames exist, then choose the lowest suffix not already present — try `-2`, then `-3`, etc.

## Step 5: Write the report

Read `/tmp/tube_audit_output/audit_results.json`.

Write a complete markdown report to `oyster-history/reports/<chosen-filename>` following this structure:

- **Summary** — total journeys, total charged, issues found, potential overcharge
- **Section 1 — Fare Discrepancies** — each flagged journey with date, route, charged, expected, explanation
- **Section 2 — Incomplete Journeys** — any journeys with no tap-out
- **Section 3 — Statement vs Top-Ups** — matching table of Oyster top-ups to card payments
- **Section 4 — Potential Refunds** — what can be claimed and how
- **Section 5 — Recommendations** — practical tips based on findings

At the end of the report, always add a "## Claimable Overcharges" section containing a structured table of only the items that can actually be claimed back (i.e., genuine overcharges — not items flagged and explained away). If there is nothing to claim, write "Nothing to claim." in this section instead of a table.

The table must use exactly this format:

| Date | Journey | Charged | Expected | Difference |
|------|---------|---------|----------|------------|
| DD Mon YYYY | Station A → Station B | £X.XX | £X.XX | £X.XX |

Below the table add one line: `**Total claimable: £X.XX**`
Also add: `**Railcard:** <railcard type>` and `**Cards:** ending ...XXXX, ending ...XXXX`

## Step 6: Show inline summary

After writing the file, display:

```
Audit complete. Report saved to `oyster-history/reports/<filename>`.

Summary:
- Journeys analysed: X
- Total charged: £X.XX
- Potential overcharge: £X.XX (show "None found" if no overcharge)
- Action items: [bullet list of the 1-3 most important things to do]

Run `/tfl-refund` to generate a claim email if overcharges were found.
```
