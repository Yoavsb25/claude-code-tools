# oyster-audit — TfL Fare Auditor

Audits your TfL Oyster card history against correct fares, detects overcharges, and generates a structured markdown report with claimable amounts.

## What it checks
- Fare discrepancies (charged vs. expected fare)
- Railcard discount not applied
- Incomplete journeys (tap-in without tap-out)
- Oyster top-ups matched to bank statement

## Dependencies

Requires the `tube-fare-auditor` plugin installed at `~/.claude/skills/tube-fare-auditor/`.

## Usage (via Claude skill)

1. Copy `SKILL.md` into your project's `.claude/skills/oyster-audit/`
2. Export your Oyster history CSV from [oyster.tfl.gov.uk](https://oyster.tfl.gov.uk) and place it in your project's `oyster-history/` folder
3. In Claude Code: `/oyster-audit`

See `docs/design.md` for architecture details.
