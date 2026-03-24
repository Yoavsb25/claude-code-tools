---
name: tfl-refund
description: Generate a structured, ready-to-send email to TfL disputing overcharged Oyster fares. Reads the latest oyster-audit-report-*.md (or a named report). Use when the user invokes /tfl-refund or wants to claim back Oyster overcharges.
disable-model-invocation: true
---

# TfL Refund Email Generator

Produces a copy-paste email to TfL based on your most recent Oyster audit report.

## Step 1: Find the audit report

If the user provided a filename argument (e.g., `/tfl-refund oyster-audit-report-2026-03-19.md`), look for it in `oyster-history/reports/`.

Otherwise, find the most recently dated report:

```bash
ls <your-project-root>/oyster-history/reports/oyster-audit-report-*.md 2>/dev/null | sort -r | head -1
```

**If no report found:** stop and say "No audit report found. Run `/oyster-audit` first to generate one."

**If the specified file doesn't exist:** list available reports (`ls oyster-history/reports/`) and ask which to use.

## Step 2: Parse the claimable overcharges

Look for the `## Claimable Overcharges` section at the end of the report.

If that section says "Nothing to claim." — stop and say "No overcharges found in this report — nothing to claim."

If the section contains a table, extract:
- Each row: date, journey, charged, expected, difference
- The `**Total claimable:**` line — use this as the refund total
- The `**Railcard:**` line — use this as the railcard type in the email
- The `**Cards:**` line — use these as the card identifiers

If the `## Claimable Overcharges` section is not present (older report format), fall back to reading the "Section 1 — Fare Discrepancies" and "Section 4 — Potential Refunds" sections. Extract only items explicitly recommended for TfL contact or refund. If uncertain, list the items you found and ask the user to confirm which to include.

## Step 3: Generate the email

Output the email inside a fenced markdown code block (``` ... ```) so the user can copy it cleanly. The email content:

```
TO: tfl-contactus@tfl.gov.uk

SUBJECT: Oyster railcard discount not applied — refund request [cards ...XXXX, ...XXXX] — £X.XX

---

Dear TfL Customer Services,

I am writing to request a refund for Oyster journeys where my <railcard type from report> railcard discount was not applied.

My railcard was valid throughout the period in question and is registered to my Oyster cards (ending ...XXXX and ...XXXX).

The following journeys were charged at the full adult fare instead of the discounted rate:

| Date | Journey | Charged | Should be | Difference |
|------|---------|---------|-----------|------------|
[one row per overcharged journey]

Total overcharge: £X.XX

I would be grateful if you could investigate and arrange a refund to my Oyster account.

Thank you,
[Your name]

Oyster cards: ending ...XXXX and ...XXXX
```

**Before sending, replace:** `[Your name]` with your actual name. All other fields in `[brackets]` and `<angle brackets>` have been filled in by Claude from the report.

After outputting the email, add a note:
"You can submit this at tfl.gov.uk/contact → Oyster and contactless → Dispute a charge, or email it directly. TfL's refund window is 8 weeks from each journey date."
