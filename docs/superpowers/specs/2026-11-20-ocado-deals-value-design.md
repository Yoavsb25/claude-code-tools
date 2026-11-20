# ocado-deals 2.0 — offers judged against what we actually buy

## Intent

Ocado runs many offers, but the household isn't benefiting: too many brands and pack sizes to compare, so we default to what we know, and "was £10, now £9.90" tells us nothing when the regular brand is £5. The skill should cut the weekly grocery bill by surfacing only offers that save real money, judged against what we normally buy, and hiding everything else.

## Goals

- Compare every offer by **unit price** (per kg / L / each), never by the product's own was-price.
- Baseline = **what we usually buy**, learned from Ocado order history (product, unit price, how often, how many).
- Report three kinds of findings, short and ranked by £/year saved:
  1. **Swaps** — a cheaper equivalent of something we already buy.
  2. **Stock-ups** — a big offer on something we buy regularly; buy several now.
  3. **New finds** — something we don't usually buy that is unusually cheap this week.
- Groceries only (food & drink).

## Non-goals

- Adding to the trolley (stays with `ocado-shopper`).
- Comparing other supermarkets (that's `grocery`).
- Brand loyalty rules — Ocado own-brand and big national brands are all acceptable.

## Anti-goals (failure even if it "works")

- A long catalogue of offers — that recreates the original confusion.
- Recommending switches for pennies (e.g. saving £0.10).
- Ranking by % off alone (20% of £0.50 doesn't matter).

## Decision rules (user-tunable defaults, stated at top of SKILL.md)

**Equivalence.** Two products are "the same thing" when they are the same product type and spec (semi-skimmed ≠ whole milk, free-range ≠ caged eggs, mince fat % within a few points). Brand and pack size may differ. Claude judges this.

**Acceptable brands.** Ocado own-brand, M&S (on Ocado), and major national brands. Unknown brands with few/no reviews (<10) are skipped.

**Swap** — shown when both hold:
- ≥10% cheaper per unit than our usual product, and
- saves ≥ £1/week **or** ≥ £20/year at our usual quantity.

**Stock-up** — shown when:
- we bought the item in ≥2 of the history's orders (regular purchase),
- the offer is ≥25% cheaper per unit than our usual price,
- it keeps (cupboard, frozen, freezable, long-dated chilled).
- Suggested quantity: enough for ~4–8 weeks of our usage, capped by shelf life; show extra spend this week and total saving.

**New find** — shown when:
- not in our history,
- ≥30% cheaper per unit than the everyday own-brand price for that product type on Ocado,
- max 5 per run, groceries only.

**Excluded categories.** Household/cleaning, toiletries/personal care, baby non-food, pet, clothing, homeware, anything non-grocery.

## Approaches considered

- **A. Rebuild `ocado-deals` around these rules** (chosen). Keep its offer-page scanning; replace the scoring; add an order-history baseline file and the three-section report. Least new machinery; fixes the actual flaw.
- **B. Merge into `ocado-shopper`.** Convenient for swaps, but new finds don't fit a list-driven flow, and it ties everything to Playwright (currently broken).
- **C. Python tool with scoring code.** Most precise and tunable, but much more to build and maintain. Fallback if A's maths proves unreliable.

## How it works

1. **Load baseline.** Read `~/.claude/ocado-deals/usual.json`. If missing or older than 30 days, refresh it:
   - Open `https://www.ocado.com/orders` in Chrome via Claude in Chrome (needs the user's logged-in session; a redirect to `sso.ocado.com` means logged out → ask them to log in; never type credentials).
   - Collect `/orders/<id>/details` links for the last ~3 months (incl. an upcoming order).
   - Detail pages are client-rendered: `fetch()` returns an empty shell, so **navigate** to each and read `main.innerText` once it contains `Price:`. Each line item is: `Nх Product name` (the `х` is Cyrillic — match `[хx]`), optional `Promotion:` + promo name, a pack line like `400g (£13.13 per kilo)` / `6 per pack (17.0p per item)`, `£X per item`, `Price:` + line total.
   - Tool output truncates around 1,000 chars: store each parsed order in `sessionStorage`, aggregate in-page, read back in small slices, then clear the keys.
   - Keep regulars (bought in ≥2 orders), groceries only. Record `baseline_weekly_spend` = total spend ÷ weeks covered.
   - Write the file. Format (field set verified against a real account 2026-11-20; values illustrative):
     ```json
     { "updated": "2026-11-20", "weeks_covered": 10, "orders": 10,
       "baseline_weekly_spend": 60.00,
       "items": [{ "name": "Lurpak Slightly Salted Butter 500g", "type": "butter, salted",
                   "pack": "500g", "unit_price": 9.00, "unit": "kg|l|each",
                   "orders": 6, "units": 7, "spend_13wk": 31.50, "units_per_week": 0.54 }],
       "savings_log": [] }
     ```
2. **Scan offers.** Same discovery as today (offers index, category pages, multi-buy bundle pages, Big Brand Offers), food & drink only. Public pages — plain fetch is fine.
3. **Score** each offer against the rules above. For multi-buys, unit price = bundle total ÷ N.
4. **For swaps on usual items with no offer hit**, a targeted Ocado search for the item's type is allowed to find a cheaper everyday equivalent (not just offers) — a swap is a swap whether or not it's "on offer".
5. **Report**, ranked by £/year saved within each section:

```
## Ocado savings — 20 Nov 2026     (≈ £X/year if you take all of these)
Baseline £60.00/week · £Y/year locked in from N accepted suggestions since <date>

### Swaps
| You buy | Switch to | Unit price | Saves |
| Lurpak Butter 500g (2/month) | Ocado Butter 500g | £5.60/kg vs £9.00/kg | £41/yr |

### Stock up this week
| Item | Offer | Buy | Extra now | Saves |
| Napolina Olive Oil 1L | Half price, £4.50 | 3 | +£9.00 | £13.50 |

### New this week
| Item | Price | vs usual for this type |
| Ocado Beef Burgers 1kg | £1.00/kg | 85% below typical £6.50/kg |
```

Empty sections say "nothing worth it this week". End with: "Say which to add — `ocado-shopper` can put them in the trolley."

6. **Savings log.** When the user says which suggestions they took, append `{date, item, kind: swap|stock-up|new, saving_per_year}` to `savings_log`. Every report's header shows: baseline weekly spend, and "£X/year locked in from N accepted suggestions since <first date>".

## Benchmark

The new skill is checked against the old one on the same eval set (`tools/ocado-deals/evals/evals.json`). 1.0.0 must fail the value-judgement evals (e.g. £10→£9.90 ranked as a deal); 2.0.0 must pass all of them. Evals use generic products only — the repo is public; real history stays in `~/.claude/ocado-deals/usual.json`.

## Constraints

- Ocado's order-history page requires login → Claude in Chrome; offer pages don't.
- Ocado URLs/IDs change; discover them from `/offers` each run (as today).
- Unit prices must be computed consistently (per kg / L / each); when Ocado doesn't show one, derive it from pack size.

## Deliverables

- `tools/ocado-deals/SKILL.md` rewritten; manifest bumped to 2.0.0 with updated description, `cli_tools`/requirements noting Claude in Chrome.
- `npm run generate-registry` and `npm run validate` pass.

## Left to the builder

- Order-history extraction details beyond what step 1 pins down.
- Product-type labelling for equivalence and category reference prices.
- Fine-tuning of the stock-up quantity wording.

## Calls I made (check these)

- Swap thresholds: ≥10% per unit AND (≥£1/week or ≥£20/year).
- Stock-up: bought in ≥2 orders, ≥25% off usual unit price, keeps; 4–8 weeks' supply.
- History window 3 months, refreshed after 30 days, stored at `~/.claude/ocado-deals/usual.json`.
- Pet food excluded as non-grocery.
- Swaps may come from everyday prices, not only offers.

## Addendum — 2.1.0 (2026-11-20)

The user wants to discover new products on sale, not only their usual items. In live runs the 2.0 rule (≥30% below own-brand) surfaced nothing, because branded offers rarely beat own-brand prices.

- **New find (replaces the ≥30% rule):** on offer and within 10% of, or below, the everyday own-brand unit price for its type; or, with no own-brand equivalent, ≥40% off its own price. Max 8.
- **Checked, not worth it:** up to 5 one-line notes on offers ≥25% off their own price that failed every rule, with unit price against the usual or own-brand price (e.g. prawns 3 for £12 → £20/kg vs usual £13.75/kg).
- **Brand filter:** products already bought always pass, and an unreadable review count never causes a skip.
