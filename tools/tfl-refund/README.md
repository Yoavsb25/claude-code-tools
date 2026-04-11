# tfl-refund — TfL Refund Email Generator

Reads your latest Oyster audit report and generates a ready-to-send email to TfL disputing overcharged fares.

## Usage (via Claude skill)

1. Run `/oyster-audit` first to generate an audit report
2. Copy `SKILL.md` into your project's `.claude/skills/tfl-refund/`
3. In Claude Code: `/tfl-refund`

Outputs a formatted email you can copy-paste or send directly to TfL.

See `docs/design.md` for more details.
