# Grocery Price Comparator — Design Spec

**Date:** 2026-03-23
**Status:** In Review

---

## Overview

A Python-based tool invoked as a Claude skill (`/compare-basket`) that accepts a pasted shopping list, scrapes live prices from Tesco, Ocado, and Waitrose using Playwright, uses a single Claude API call to semantically match items to the correct SKUs, and outputs a comparison table highlighting the cheapest basket.

---

## Goals

- Accept a free-form structured shopping list (bullet points, plain text with quantities)
- Fetch live prices from Tesco, Ocado, and Waitrose via Playwright scraping
- Match each list item to the most equivalent product per retailer using Claude
- Output a side-by-side price comparison table with cheapest basket highlighted
- Ask clarifying questions only when genuinely ambiguous; auto-pick otherwise
- Minimize token usage: strip all data to essential fields before sending to Claude, batch all matching into a single API call, and keep prompts concise

---

## Non-Goals

- Price tracking over time
- Retailers beyond Tesco, Ocado, Waitrose
- A web UI

---

## Data Source

**Primary: DIY Playwright scraping** using the Python `playwright` library.

The Python script navigates each retailer's search page, extracts structured price data using CSS selectors, and returns clean JSON. Claude never sees raw HTML — only the stripped candidates JSON.

**Fallback: Apify pre-built actors** for any retailer that aggressively blocks Playwright (Ocado in particular has bot detection). Apify actors for Tesco, Ocado, and Waitrose are available on the Apify marketplace. The fallback is a manual code swap — if a retailer's scraper returns empty results or raises an HTTP error (403, redirect to CAPTCHA), the script fails that retailer with a message prompting the user to enable the Apify actor for that retailer. Switching is a one-line config change in `scraper.py`; the rest of the architecture is unchanged.

### Retailer search URLs
| Retailer | Search URL pattern |
|---|---|
| Tesco | `https://www.tesco.com/groceries/en-GB/search?query={item}` |
| Ocado | `https://www.ocado.com/search?entry={item}` |
| Waitrose | `https://www.waitrose.com/ecom/shop/search?searchTerm={item}` |

CSS selectors for price extraction to be confirmed during development using browser DevTools.

---

## Architecture

```
User pastes list
      ↓
[Skill: /compare-basket]
      ↓
[Python script: basket_compare.py]
  ├── Parse list items + quantities
  ├── Scrape each retailer per item via Playwright (parallel, max 5 concurrent)
  ├── Strip results to: name, price, unit_price, retailer, url
  └── Build candidates JSON
      ↓
[Single Claude API call — claude-sonnet-4-6]
  ├── Input: items + candidates JSON
  ├── Task: pick best match per item per retailer
  ├── Flag low-confidence matches for clarification
  └── Return structured JSON matches
      ↓
[Python script]
  └── Apply quantity multipliers → render comparison table → highlight cheapest basket
```

---

## Components

### `basket_compare.py` — Entry point
- Reads shopping list from stdin or a `--file` argument
- Parses items and quantities (e.g. `2x milk 2L` → item: `milk 2L`, qty: 2)
- Orchestrates: scrape → match → clarify (if needed) → render
- Clarification loop: questions are grouped per item (not per item-retailer pair). One question is shown per ambiguous item; the user's answer applies to that item across all retailers. Example prompt: `[1] For "butter": did you mean own-label unsalted or a specific brand like Anchor?`. User types `own-label` and presses Enter. The script collects all answers, then re-calls the matcher with each ambiguous item's candidates plus `"user_clarification": "<answer>"` appended. Max one clarification round total.

### `scraper.py` — Playwright scraping layer
- `async scrape(item: str, retailer: str) -> list[Product]`
- Launches headless Chromium, navigates to retailer search URL, extracts top 5 results per retailer per item
- Strips each result to `{name, price: float, unit_price: str, retailer: str, url: str}`
  - `price` is a float (e.g. `1.40`)
  - `unit_price` is a formatted display string (e.g. `"62p/litre"`) — not used for arithmetic
- All scrape calls run concurrently via `asyncio`, max 5 concurrent browser pages
- Per-retailer scraper functions can be swapped for Apify HTTP calls without changing the interface

### `matcher.py` — Claude matching layer
- Builds a single structured prompt from all items + candidates (see prompt template in Data Flow)
- Calls Claude API (claude-sonnet-4-6) with JSON output mode
- Returns a JSON array of `{item, retailer, matched_product, price, unit_price, url, confidence, clarification_question?}` per match
- Confidence is self-assessed by Claude on a 0–1 scale; matches below 0.8 include a `clarification_question` string
- If no candidate is a reasonable match for a given item at a given retailer, Claude returns `{"price": null, "url": null, "matched_product": null, "confidence": 0}` for that item-retailer pair — this is treated as N/A in the table
- If Claude returns malformed or incomplete JSON: retry the call once with the same prompt; if it fails again, abort with a clear error message
- For the clarification re-call: only the low-confidence items and their candidates are sent, with user answers appended as `"user_clarification": "..."` per item; high-confidence matches from the first call are reused as-is
- `matched_product` is a string — the product name as returned in the candidates (same as `name`). It is included in the return schema so the renderer can display which product was matched.

### `renderer.py` — Output formatting
- Applies quantity multipliers to prices before rendering (quantity comes from parser, not Claude)
- Renders markdown comparison table to terminal
- Highlights cheapest option per item (✓) and cheapest total basket (🏆)
- Retailer excluded from cheapest recommendation if 2 or more items are N/A
- Optionally saves output as a `.md` report via `--save` flag; filename defaults to `basket-comparison-YYYY-MM-DD.md` in the current working directory

### `compare-basket` skill
- Lives at `.claude/skills/compare-basket.md`
- Instructs Claude to accept a pasted list from the user, write it to a temp file, and run `python grocery/basket_compare.py --file <tempfile>` from the repo root (i.e., `<your-project-root>`)
- Assumes a virtualenv at `grocery/.venv` is activated before running
- Defines expected input format and output behaviour for the user

---

## Data Flow

### Input (pasted by user)
```
2x semi-skimmed milk 2L
free-range eggs 12
sourdough bread 400g
unsalted butter 250g
```

### Parsed representation (internal)
```json
[
  {"item": "semi-skimmed milk 2L", "qty": 2},
  {"item": "free-range eggs 12", "qty": 1},
  {"item": "sourdough bread 400g", "qty": 1},
  {"item": "unsalted butter 250g", "qty": 1}
]
```

### Scraper output (stripped before Claude sees it)

Each candidate includes `retailer` as an explicit field so Claude does not need to infer it from structure.

```json
{
  "semi-skimmed milk 2L": [
    {"retailer": "tesco",    "name": "Tesco Semi Skimmed Milk 2.27L",   "price": 1.40, "unit_price": "62p/litre", "url": "https://..."},
    {"retailer": "ocado",    "name": "Ocado Own Semi Skimmed Milk 2L",  "price": 1.89, "unit_price": "95p/litre", "url": "https://..."},
    {"retailer": "waitrose", "name": "Waitrose Semi Skimmed Milk 2L",   "price": 1.65, "unit_price": "83p/litre", "url": "https://..."}
  ]
}
```

Up to 5 candidates per retailer per item (max 15 candidates per item total).

### Claude matching prompt (single call)
```
You are matching shopping list items to supermarket products.
For each item, pick the best match per retailer using these rules:
- Prefer own-label over branded unless a brand is specified
- Match size/quantity as closely as possible to what was requested
- Prefer standard over organic unless organic is specified
- When own-label IS organic (common at Waitrose), prefer the non-organic own-label alternative if available; otherwise accept the organic own-label
- Rate your confidence 0–1: how well does the matched product match what was requested?
  - 1.0 = exact match (same type, size, own-label)
  - 0.8 = close match (slightly different size or only branded available)
  - below 0.8 = ambiguous (wrong category, no good match, or brand ambiguity)
- For matches below 0.8, include a clarification_question field

Return JSON array: [{item, retailer, matched_product, price, unit_price, url, confidence, clarification_question?}]

Shopping list: [...]
Candidates: [stripped JSON]
```

### Output table
```
Item                    | Tesco   | Ocado   | Waitrose | Cheapest
Semi-skimmed milk 2L ×2 | £2.80   | £3.78   | £3.30    | Tesco ✓
Free-range eggs ×12     | £2.75   | £2.99   | £3.10    | Tesco ✓
Sourdough bread 400g    | £1.20   | £1.50   | N/A      | Tesco ✓
Unsalted butter 250g    | £1.85   | £1.95   | £1.90    | Tesco ✓
─────────────────────────────────────────────────────────────────
TOTAL                   | £8.60   | £10.22  | £8.30*   | 🏆 Tesco
* Waitrose missing 1 item
```

---

## Matching Rules

Claude uses these tie-breaking rules when auto-picking:
1. Prefer own-label over branded (unless brand is specified)
2. Match size/quantity as closely as possible
3. Prefer standard over organic (unless organic is specified)
4. If own-label is only available as organic (common at Waitrose): accept it; do not prefer a branded non-organic over an own-label organic

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Scraper returns zero results for an item | Show `N/A` in that column (scraper-level miss) |
| Claude returns null price for an item-retailer pair | Show `N/A` in that column (matcher-level miss) |
| 2+ items show N/A at a retailer (either source) | Exclude retailer from cheapest basket recommendation with a `*` note |
| Scraper blocked by anti-bot (HTTP 403 or CAPTCHA redirect) | Fail that retailer entirely with clear message; suggest switching to Apify for that retailer |
| Ambiguous items | Claude batches all low-confidence questions into one clarification round; user answers all at once; matcher re-called once with answers; max 1 round total |
| Ambiguous quantity | Assume qty=1, note assumption in output |
| Claude API unavailable | Fail fast with clear message |

---

## Token Efficiency

- All scraped results stripped to 5 fields (name, price, unit_price, retailer, url); capped at 5 candidates per retailer per item (max 15 per item)
- All items matched in a single Claude API call
- Quantity multipliers applied by Python after matching — Claude never needs to know quantities
- Scraped results cached in-memory for the duration of a single script invocation (re-runs of same item within one session are free)

---

## Key Dependencies

```
# requirements.txt
playwright          # browser automation
anthropic           # Claude API
asyncio             # stdlib — concurrent scraping
```

---

## File Structure

```
London/
  grocery/
    basket_compare.py
    scraper.py
    matcher.py
    renderer.py
    requirements.txt
  .claude/
    skills/
      compare-basket.md
```
