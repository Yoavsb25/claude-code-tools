---
name: compare-basket
description: Compare live grocery prices across Tesco, Ocado, and Waitrose for a shopping list, and highlight the cheapest basket. Use this skill whenever the user wants to compare supermarket prices, find the cheapest place to shop, check grocery costs, or invokes /compare-basket. Also trigger for phrases like "where should I shop", "is Tesco cheaper than Waitrose", "compare prices for my shopping list", or "which supermarket is cheapest for X".
---

# Compare Basket

Scrapes live prices from Tesco, Ocado, and Waitrose, uses Claude to match each
item to the best product per retailer, and renders a side-by-side price table
with the cheapest basket highlighted.

## Setup (first time only)

If `grocery/.venv` doesn't exist:

```bash
cd <your-project-root>/grocery
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Steps

### 1. Get the shopping list

If the user hasn't pasted one, ask:
> Please paste your shopping list. Use `2x` before an item to set quantity (e.g. `2x semi-skimmed milk 2L`). One item per line.

### 2. Write the list to a temp file

Write the list exactly as the user provided it to `/tmp/basket-list.txt`.

### 3. Run the script

```bash
cd <your-project-root>
source grocery/.venv/bin/activate
python grocery/basket_compare.py --file /tmp/basket-list.txt
```

To also save a `.md` report, add `--save`:

```bash
python grocery/basket_compare.py --file /tmp/basket-list.txt --save
```

### 4. Show the output

Display the comparison table from the script output. If the user asks to save
the report and `--save` wasn't used, re-run with `--save`.

## Input format

```
2x semi-skimmed milk 2L
free-range eggs 12
sourdough bread 400g
unsalted butter 250g
```

- `2x item` or `2 x item` — quantity prefix (defaults to 1 if omitted)
- Bullet points (`-`, `•`) and numbered lists are fine — the parser strips them

## What to expect

- Scraping takes **30–60 seconds** for a typical basket — let the user know
- If a retailer shows `N/A` for an item, either the scraper found nothing or
  Claude judged there was no reasonable match
- If a retailer is blocked by bot detection, the script prints a message
  suggesting switching the Apify fallback on for that retailer
  (a one-line change in `grocery/scraper.py`)
- `ANTHROPIC_API_KEY` must be set in the environment

## Troubleshooting

| Symptom | Fix |
|---|---|
| All results N/A for one retailer | Bot detection — set `USE_APIFY["<retailer>"] = True` in `scraper.py` |
| `ModuleNotFoundError` | Run the setup steps above |
| `ANTHROPIC_API_KEY` error | Export the key: `export ANTHROPIC_API_KEY=sk-...` |
| CSS selectors returning empty | Open the retailer's search page in Chrome DevTools and update the selectors in `scraper.py` |
