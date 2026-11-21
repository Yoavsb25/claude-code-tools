# Folder and extras skill bundles: short design (approved 2026-11-21)

## Why
Many skills here were built for personal use but get used rarely (a trip once a year) or are mainly
useful to others. They should stay available and shared, without loading into every session.

## Goals / non-goals
- Goal: no personal skill loads by default; each one is on where it's used, or one command away.
- Goal: the repo stays the public home for every skill that is still relevant.
- Non-goal: new scheduled automations (no regular rhythm today; revisit with `/infra-audit` data).
- Anti-goal: having to remember where a rare skill lives or how it was installed.

## Approaches
- **A. Switchable bundles (chosen).** Bundles installed per folder, or installed but off and switched on when needed
  (`claude plugin enable extras@yoav-tools`, or `/plugin` inside a session), then a restart.
- B. An always-loaded "library" skill that lists stored skills and opens them on demand. No restart, but an extra moving part.
- C. Keep everything loaded. Zero friction, but about 2k tokens per session and accidental triggers.

## Design
`yoav-tools` marketplace (this repo) replaces the `life` and `build` bundles with:

| Bundle | Skills | Scope |
|---|---|---|
| home | ocado-shopper, ocado-deals | local, `~/Documents/3 Homes/London` |
| money | expense-analyzer, trip-expense-report | local, `~/Documents/2 Money` |
| extras | flight-finder, stay-finder, amazon-shopper, tube-fare-auditor, tfl-refund, folder-organizer, software-architect, product-manager, ui-ux-expert, security-architect, testing-strategist, tech-stack-selector | user, installed but disabled |
| career | unchanged | local, job-search |

- Deleted from the repo and registry (replaced by AI agents): add-todo, run-todos, process-emails.
- `yoav-private` (design, mobile, research) unchanged.
- One line in the global `~/.claude/CLAUDE.md` names the extras bundle and its skills, so Claude can offer to
  switch it on when a request matches.
- The folder bundles apply only when Claude starts in that exact folder (neither is a git repo).

## Left to the builder
- Regenerate the registry (`npm run generate-registry`, `npm run validate`).
- Verify with `claude plugin list` from `~`, both folders, and job-search.
