# tube-fare-auditor — Advanced TfL Oyster Auditor

Audits your TfL Oyster card travel history against correct fares, verifies railcard discounts are applied, detects maximum fare charges from incomplete journeys, matches top-ups to your bank statement, and produces a plain-English report of suspicious charges and potential refunds.

## What it checks

- Fare discrepancies (charged vs. correct fare for each journey)
- Railcard discount not applied when it should have been
- Incomplete journeys (tap-in without tap-out) that triggered max fare
- Oyster top-ups matched against bank/card statement entries
- Peak vs. off-peak misclassification

## Requirements

- Python ≥ 3.9
- Oyster history CSV exported from [oyster.tfl.gov.uk](https://oyster.tfl.gov.uk)
- Optionally: bank statement CSV for top-up reconciliation

## Usage

Export your Oyster history CSV, then:

```
/tube-fare-auditor
audit my Oyster card
check my TfL charges
```

The skill produces a structured report with claimable amounts and a refund link.

## Related

- `oyster-audit` — simpler fare check (subset of this tool's functionality)
- `tfl-refund` — submit a refund request directly
