# amazon-shopper — Amazon UK Basket Automation (macOS)

Searches Amazon UK for an item, picks the best match (rating ≥3.5, ≥20 reviews, Prime-preferred), shows it for confirmation, then adds it to your basket. Never completes checkout — basket only.

## Requirements
- Playwright MCP tool available in Claude Code
- Logged in to Amazon UK in the browser session

## Usage (via Claude skill)

Copy `SKILL.md` into your project's `.claude/skills/amazon-shopper/` and say "buy [item]" or invoke it from `run-todos` for qualifying buy tasks.

## Key rules
- **Basket only** — never attempts checkout or payment
- Stops and asks if key specs are missing (size, colour, budget, model)
- Skips sponsored results; prefers Prime-eligible, well-reviewed items
- One item per invocation
