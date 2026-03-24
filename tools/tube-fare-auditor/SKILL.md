---
name: tube-fare-auditor
description: Audits London TfL (Transport for London) Oyster card travel history against correct fares, checks that railcard discounts are applied correctly, matches Oyster top-ups to bank/card statements, detects incomplete journeys and maximum fare charges, and produces a plain-English report of suspicious charges and potential refunds. Use this skill whenever the user mentions checking their Oyster card history, TfL charges, tube fares, railcard discounts on TfL, Oyster top-ups on their bank statement, or wants to find out if they've been overcharged on the London Underground or TfL network. Also trigger for phrases like "check my travel history", "TfL refund", "oyster charges wrong", "was I charged correctly for the tube", "my railcard isn't working on Oyster", or "help me understand my Oyster charges".
---

# TfL Oyster Fare Auditor

Audits Oyster card travel history for fare errors, railcard discount issues, unmatched top-ups, and potential refunds.

## What you need from the user

Before running anything, make sure you have:

1. **Oyster journey history CSV(s)** — exported from oyster.tfl.gov.uk (may be multiple files if they have more than one Oyster card)
2. **Bank/card statement CSV** (optional but recommended) — to match Oyster top-up payments. Works with Wise, Monzo, or any generic bank CSV
3. **Railcard type** (if any) — ask if not mentioned. Supported types: `26-30`, `two-together`, `senior`, `disabled`, `annual-gold`, `network`, `hm-forces`, `freedom-pass`, `60plus`

If the user hasn't provided files yet, ask for them before proceeding. They can provide file paths on their filesystem.

## Step 1: Run the audit script

```bash
python ~/.claude/skills/tube-fare-auditor/scripts/audit.py \
  --oyster <path_to_oyster_csv> \
  [--oyster <path_to_second_oyster_csv>] \
  [--statement <path_to_card_statement_csv>] \
  [--railcard 26-30] \
  [--tfl-api-key <key>] \
  --output /tmp/tube_audit_output/
```

The script loads fare tables, station zones, and railcard rules from the `references/` directory — these are maintained separately from the script so you can update fares each March without touching the code.

**TfL API key (optional but recommended for exact fares):**
The script uses the live TfL Journey Planner API to verify exact fares. Without an API key, TfL rate-limits unauthenticated requests to ~50 per 30 minutes — enough for a first run to warm the local cache (results are cached for 35 days), but some journeys may fall back to zone-based estimates. Users can get a free API key at [api.tfl.gov.uk/registration](https://api.tfl.gov.uk/registration) — with a key, the rate limit is 500 calls/minute and all fares are verified live. Pass it via `--tfl-api-key` or the `TFL_API_KEY` environment variable. If the user has a key, use it. Otherwise, reassure them the zone-based fallback is accurate for standard zone-to-zone journeys.

## Step 2: Reason over the results

Read `audit_results.json` from the output directory. The script does the number-crunching; your job is to make sense of it for the user.

**Consult the reference files as needed:**
- `references/tfl-fares.md` — fare table overview and peak hour rules
- `references/refund-policy.md` — what TfL will and won't refund
- `references/railcard-types.json` — full railcard rules (especially peak/off-peak restrictions — different railcards have different rules)
- `references/fare-config.json` — the actual fare numbers by year
- `references/station-zones.json` — station zone lookup

If any stations appeared as "unknown" in the script output, look them up at tfl.gov.uk/maps and add them to `station-zones.json` before re-running.

## Step 3: Write the final report

Write a clear, plain-English report. Assume the user may not be familiar with TfL jargon. Structure it like this:

```
# TfL Oyster Audit Report
Period: [date range]
Cards audited: [number and card IDs/filenames]
Railcard: [type, or "None"]

---

## Summary
- Total journeys analysed: X
- Total charged to Oyster card(s): £X.XX
- Issues found: X
- Potential overcharge: ~£X.XX
- Potential refunds: ~£X.XX (see Section 4)

---

## Section 1 — Fare Discrepancies
For each flagged journey: date, route, what was charged, what should have been charged, why it's flagged.

Be specific. Don't just say "error" — explain it like:
"On 18 March, you were charged £3.10 for Monument → Kings Cross. Both stations are Zone 1.
Your 26-30 railcard should bring this down to £2.05. It looks like the railcard discount wasn't applied."

If a railcard's rules mean it legitimately doesn't apply at peak (e.g. Two Together), say so clearly
rather than flagging it as an error.

---

## Section 2 — Incomplete Journeys
List any "Entered [station]" records with no corresponding exit.
These result in a maximum fare charge and are almost always refundable within 8 weeks.

---

## Section 3 — Card Statement vs Oyster Top-Ups
Show a matching table. Flag any top-ups with no matching card payment, or
card charges to TfL with no matching Oyster top-up.

Note: top-up merchant names vary — "TfL - Transport for London", "Heathrow Express"
(when topped up at Heathrow), station names, etc. The script handles this automatically.

---

## Section 4 — Potential Refunds
Summarise what can be claimed and how:
- Incomplete journey refunds: claim at tfl.gov.uk/contact or at any station
- Railcard discount not applied: contact TfL with specific journey dates
- Wrong fare: contact TfL

Include any TfL "Unpaid fares" charges found on the card statement — these are penalty
charges for past incomplete journeys and are worth noting even if now outside refund window.

---

## Section 5 — Recommendations
Practical tips tailored to what you found. Examples:
- How to check/link a railcard on Oyster (oyster.tfl.gov.uk)
- Always tap out to avoid maximum fares
- What to say when contacting TfL
```

## Accuracy notes

- Fare tables are in `references/fare-config.json`, versioned by date. TfL typically raises fares in early March. If auditing journeys near a March boundary, double-check which period applies.
- Some National Rail journeys within London are paid via Oyster but at National Rail fares — legitimately higher than tube fares. Look for "[National Rail]" in the journey description.
- Flag confidently only when the discrepancy is > 10p after accounting for rounding. Smaller differences are likely rounding artefacts.
- If a station zone is unknown, say so rather than guessing.
