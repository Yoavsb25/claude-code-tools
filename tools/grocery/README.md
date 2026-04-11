# grocery — Basket Price Comparator

Compare grocery prices across Tesco, Ocado, and Waitrose for any shopping list. Claude matches each item to the best product per retailer and shows you which basket is cheapest.

## How it works

Four-stage pipeline:
1. **scraper.py** — Playwright scrapes live prices from all three retailers
2. **matcher.py** — Claude API picks the best-matching product per item per retailer
3. **renderer.py** — Builds a markdown comparison table with cheapest items highlighted
4. **basket_compare.py** — Orchestrates the pipeline; handles quantity prefixes like `2x milk 2L`

## Setup

```bash
cd grocery
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Requires: `ANTHROPIC_API_KEY` environment variable.

## Usage

```bash
source grocery/.venv/bin/activate
python grocery/basket_compare.py --file /path/to/list.txt
```

Or use the Claude skill: copy `SKILL.md` into your project's `.claude/skills/compare-basket/` and say "compare my basket" in Claude Code.

## Input format

```
2x semi-skimmed milk 2L
free-range eggs 12
sourdough bread 400g
```

See `SKILL.md` for full Claude Code skill instructions.
