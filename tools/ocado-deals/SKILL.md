---
name: ocado-deals
description: Finds Ocado offers that actually save money. Compares unit prices against what the household usually buys (learned from Ocado order history) and reports only worthwhile swaps, stock-ups and standout new deals, while tracking savings over time. Use whenever the user mentions Ocado offers, asks what's worth buying or stocking up on this week, wants cheaper swaps, asks "is this deal worth it", wants to cut their grocery bill, or says they took a suggested swap — even if they don't say "deals".
---

# Ocado Deals — offers judged against what you actually buy

An offer only matters if it beats what you'd otherwise buy. This skill never ranks by "was £X" or by % off alone. It compares **unit prices** (per kg / L / each) against your usual products and shows only savings worth acting on.

## Your rules (edit these numbers any time)

| Rule | Default |
|---|---|
| Acceptable brands | Ocado own-brand, M&S, major national brands. Skip unknown brands with <10 reviews |
| **Swap** — cheaper equivalent of something you buy | ≥10% cheaper per unit at its **everyday** price **and** saves ≥ £20/year at your usual quantity |
| **Stock-up** — big offer on something you buy regularly | bought in ≥2 orders, ≥25% cheaper per unit than usual, keeps (cupboard / frozen / freezable / long-dated). Suggest 4–8 weeks' supply, capped by shelf life |
| **New find** — something you don't usually buy | ≥30% cheaper per unit than the everyday own-brand price for that product type. Max 5 |
| Groceries only | Exclude household/cleaning, toiletries/personal care, baby non-food, pet, clothing, homeware |
| History | Last ~3 months of orders, refreshed when older than 30 days |

**Equivalence:** two products are "the same thing" when they are the same product type and spec (semi-skimmed ≠ whole milk, free-range ≠ caged eggs, Greek *strained* ≠ Greek *style* yoghurt, mince fat % within a few points). Brand and pack size may differ. When equivalence is debatable, show the swap and name the difference in a few words. The user decides.

**Never** add anything to the trolley. That's `ocado-shopper`.

---

## Step 1 — Load the baseline

Read `~/.claude/ocado-deals/usual.json`:

```json
{ "updated": "YYYY-MM-DD", "weeks_covered": 10, "orders": 10,
  "baseline_weekly_spend": 60.00,
  "items": [{ "name": "Lurpak Slightly Salted Butter 500g", "type": "butter, salted",
              "pack": "500g", "unit_price": 9.00, "unit": "kg|l|each",
              "orders": 6, "units": 7, "spend_13wk": 31.50, "units_per_week": 0.54 }],
  "savings_log": [{ "date": "YYYY-MM-DD", "item": "...", "kind": "swap|stock-up|new", "saving_per_year": 41.0, "one_off": 0 }] }
```

**Always first** (both steps need an Ocado tab): load Chrome tools in **one** ToolSearch: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__tabs_close_mcp`. If Chrome isn't connected, tell the user to run `/chrome` and stop.

If the file exists and `updated` is within 30 days, use it and go to Step 2. Otherwise refresh it:

1. Open `https://www.ocado.com/orders` in a new tab. A redirect to `sso.ocado.com` means logged out: **ask the user to log in and stop.** Never type credentials. On a cookie banner, choose "Decline Advertising Cookies".
2. Collect order links for the last ~3 months (include an upcoming order):
   ```js
   [...document.querySelectorAll('a[href*="/orders/"][href$="/details"]')].map(a => a.href + ' | ' + a.innerText.replace(/\s+/g,' ').slice(0,40))
   ```
3. Detail pages are client-rendered (`fetch()` returns an empty shell). For **each** order, `navigate` to `/orders/<id>/details` and then run this parser. It waits for render, parses line items (note: the `х` in `2х` is Cyrillic) and stores the result in `sessionStorage`, because tool output truncates at around 1,000 chars:
   ```js
   for (let k=0; k<20 && !(document.querySelector('main')?.innerText||'').includes('Price:'); k++) await new Promise(r=>setTimeout(r,500));
   const L = document.querySelector('main').innerText.split('\n').map(x=>x.trim()).filter(Boolean); const out=[];
   for (let i=0;i<L.length;i++){ const m=L[i].match(/^(\d+)[хx]\s+(.+)$/); if(!m) continue; let promo='',pack='',total='';
     for (let j=i+1;j<Math.min(i+9,L.length);j++){ if(/^(\d+)[хx]\s/.test(L[j])) break;
       if(L[j]==='Promotion:') promo=L[j+1];
       else if(/per (kilo|litre|item|100)/.test(L[j]) && !pack && !/^£[\d.]+ per item$/.test(L[j])) pack=L[j];
       else if(L[j]==='Price:') total=L[j+1]; }
     out.push([m[1],m[2],pack,total,promo].join('|')); }
   const id=location.pathname.split('/')[2]; sessionStorage.setItem('ord_'+id, out.join('\n')); id+' '+out.length
   ```
4. Aggregate in-page by product name (orders, units, spend, latest pack line) into `sessionStorage['rows']`, sorted by spend. Read it back **10 rows per call**. For the tail, read only products bought in ≥2 orders.
5. Clear the `ord_*` and `rows` keys and close the tab.
6. Write the file (`mkdir -p ~/.claude/ocado-deals`). Keep groceries only, and only **regulars** (≥2 orders) — **unless the history has fewer than 2 orders, in which case keep every grocery line** (otherwise the baseline would be empty). Give each a `type` label for equivalence. Parse `unit_price`/`unit` from the pack line (`£13.13 per kilo` → 13.13/kg, `17.0p per item` → 0.17/each). Set `units_per_week = units / weeks_covered` and `baseline_weekly_spend = total spend / weeks_covered`. **Preserve the existing `savings_log`.**

If the history has fewer than 2 orders, carry on but say "history is thin (N order)" in the report. The Stock-up section then reads "none possible yet — an item needs to appear in at least 2 orders". Swaps and New this week still run against the single order's items.

---

## Step 2 — Scan offers

Work in an Ocado tab (`https://www.ocado.com/offers`, which redirects to `/promotions`). Offer pages and `/search?q=` results are **server-rendered**, so `fetch(path)` + `DOMParser` inside the tab returns about 100 product cards per page with no navigation. Strip query strings before printing hrefs, because tool output containing them gets blocked. Card fields:

```js
const seen=new Set();
[...doc.querySelectorAll('[data-test="fop-product-link"]')].map(a=>a.closest('li')||a.parentElement.parentElement.parentElement)
  .filter(c=>!seen.has(c)&&seen.add(c))
  .map(c=>{const g=k=>c.querySelector(`[data-test="${k}"]`)?.textContent.trim()||''; const tx=c.textContent.replace(/\s+/g,' ');
    return {title:g('fop-title')||g('fop-product-link'), size:g('fop-size'), price:g('fop-price'), perUnit:g('fop-price-per-unit'),
            was:(tx.match(/was £([\d.]+)/)||[])[1], offer:(tx.match(/Now £[\d.]+,? was £[\d.]+|Half [Pp]rice|Buy any [^£]*£[\d.]+|\d+ for £[\d.]+/)||[''])[0],
            reviews:+((tx.match(/from (\d+) reviews/)||[0,0])[1])};})
```

Normalise `perUnit` (`£6.21 per kilo`, `30.8p per item`, `per 100g` ×10) to a number plus `kg|l|each`. Keep results in `sessionStorage`, filter and score in-page, and read back only the candidate lines. Clear the keys and close the tab when done.

Collect the section links from the offers page:

| Section | Path pattern |
|---|---|
| Fresh & Chilled | `/promotions/fresh-chilled-food/…` |
| Food Cupboard | `/promotions/food-cupboard/…` |
| Bakery | `/promotions/bakery/…` |
| Frozen | `/promotions/frozen…` (if present) |
| Multi-buy bundles | any link containing "for £" (e.g. "3 for £12") |
| Big Brand Offers (fixed) | `https://www.ocado.com/categories/events-inspiration/big-brand-offers/fecb2247-6f0e-4e89-85d4-63b310a6db07` |

Fetch all in parallel (and `&page=2` where paginated). For every **grocery** offer record: name, pack size, offer price, unit price + unit, offer type (single / "N for £X"), and whether it keeps.

- Multi-buy unit price = (bundle total ÷ N) ÷ pack size.
- If Ocado shows no unit price, derive it from the pack size in the name.
- If neither works, **drop the offer**. Never compare per-each with per-kg.

A section **failed** if its fetch is not OK **or it parses 0 product cards** (selectors may have changed). If no section links are found on the offers page, every section failed. List failed sections in the report. If all sections failed, say "Offer scan failed — Ocado's page layout may have changed" and don't print "nothing worth it this week" for Stock-up or New this week. Swaps from everyday searches may still be shown if search worked.

---

## Step 3 — Score

For each **usual item** (baseline), look at offers and everyday prices for the same `type`. Each product lands in **at most one** section:

- **Swap** — judged on **everyday prices only** (the alternative's normal price, not a temporary offer), so the yearly saving lasts.
  - Rule: alternative is a different product, ≥10% cheaper per unit at its everyday price, and saves ≥ £20/year.
  - `£/year = (usual price per pack − alternative's everyday price for the same amount) × units_per_week × 52`. `units_per_week` counts **packs**, so never multiply a per-kg difference by it.
  - If the alternative is also on offer this week, add "(also on offer this week)".
- **Stock-up** — the usual product **or** a same-spec equivalent is on offer ≥25% below the usual unit price, the item was bought in ≥2 orders, and it keeps.
  - Quantity = enough for 4–8 weeks at `units_per_week`, rounded to whole packs, capped by shelf life. For "N for £X", round up to a multiple of N.
  - Show spend now (offer price × qty) and the **one-off** saving ((usual − offer) × qty). Stock-ups never claim a yearly saving.
  - If a product qualifies as both a Swap and a Stock-up, list it under Swaps only.
- A small cut on the usual item (e.g. £10 → £9.90) is neither — say nothing.

Then **everyday swaps**: for the top 10 baseline items by spend, unless the item already produced a Swap, run one Ocado search for the `type` and look for a cheaper acceptable equivalent at everyday prices. An offer on the usual item that didn't qualify (like the 1% cut) does **not** skip this search.

Then **new finds**: offers whose type matches nothing in the baseline. For each candidate, get the everyday own-brand unit price for that type (one search). Keep it if it is ≥30% cheaper. Keep the top 5 by % below.

Anything that fails its rule is silent. Don't list near-misses.

---

## Step 4 — Report

Sections are ranked by £/year saved (new finds by % below typical). Use this layout exactly:

```
## Ocado savings — 20 Nov 2026     (≈ £X/year from swaps + £Z one-off from stock-ups)
Baseline £60.00/week · £Y/year + £W one-off locked in from N accepted suggestions since 1 Nov 2026

### Swaps
| You buy | Switch to | Unit price | Saves |
|---|---|---|---|
| Lurpak Butter 500g (2/month) | Ocado Butter 500g | £5.60/kg vs £9.00/kg | £44/yr |

### Stock up this week
| Item | Offer | Unit price | Buy | Spend now | Saves (one-off) |
|---|---|---|---|---|---|
| Napolina Olive Oil 1L | Half price, £4.50 | £4.50/L vs usual £9.00/L | 2 | £9.00 | £9.00 |

### New this week
| Item | Price | vs usual for this type |
|---|---|---|
| Ocado Beef Burgers 1kg | £1.00/kg | 85% below typical £6.50/kg |
```

- An empty section says "nothing worth it this week".
- Leave out the locked-in line if `savings_log` is empty.
- Add notes for failed sections and thin history.
- End with: "Tell me which you took and I'll log the savings. `ocado-shopper` can put them in the trolley."

---

## Step 5 — Log accepted suggestions

When the user says which suggestions they took (e.g. "I took the butter swap"), append one entry per suggestion to `savings_log` in `usual.json`: `{date: today, item, kind, saving_per_year, one_off}`. A swap or new find logs its £/year with `one_off: 0`. A stock-up logs `saving_per_year: 0` and its one-off saving. Then reply with the new totals: "£Y/year + £W one-off locked in from N accepted suggestions since <first date>".
