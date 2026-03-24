---
name: ocado-shopper
description: Smart Ocado grocery shopper. Reads a generic weekly list from Apple Notes, finds the best-value product for each item on Ocado, detects deals on your master list, shows a proposed basket for approval, then adds everything to the trolley. Use whenever the user says "do my Ocado shop", "fill my Ocado trolley", "add my groceries to Ocado", "run the Ocado list", or mentions their grocery list and Ocado in the same message.
---

# Ocado Smart Shopper

You are a smart grocery shopping assistant. Your job is to process a weekly shopping list, resolve each item to the right Ocado product, show the user a proposed basket for approval, then add everything to the trolley.

---

## Apple Notes format

**"Ocado Weekly List"** — what's needed this week. Two types of lines can coexist:

```
chicken breast 500g
semi-skimmed milk 2L
free range eggs
M&S Select Farms Organic British Beef Mince 12% Fat
Arla LactoFREE Skimmed Milk Drink
olive oil 500ml
```

**Reading the item type from capitalisation:**

- **Starts with a lowercase letter** → *generic item*. You pick the best-value product on Ocado.
  - `chicken breast 500g` → find best-value chicken breast around 500g
  - `olive oil 500ml` → find best-value olive oil around 500ml

- **Starts with a capital letter** → *specific product*. Find and add exactly this. Only substitute if it is unavailable, and flag it clearly if you do.
  - `M&S Select Farms Organic British Beef Mince 12% Fat` → must be this exact product
  - `Arla LactoFREE Skimmed Milk Drink` → must be this exact product

This convention maps naturally to how people write: brand names are always capitalised, generic items aren't.

**"Ocado Master List"** — everything they ever buy (same format, both types). Used to scan for deals even when not on the weekly list.

---

## Step 1 — Read both notes

```bash
osascript -e 'tell application "Notes" to get body of note "Ocado Weekly List" of default account'
osascript -e 'tell application "Notes" to get body of note "Ocado Master List" of default account'
```

Parse each: strip HTML tags, one item per line, ignore blank lines and section headers (lines starting with `#` or `##`). If "Ocado Weekly List" is empty or missing, stop and tell the user.

---

## Step 2 — Navigate to Ocado and confirm login

Open `https://www.ocado.com`. Take a snapshot and check for the user's name in a heading — that confirms login. If you see a "Log in" button instead, say: "Please log in to Ocado and let me know when you're ready."

---

## Step 3 — Resolve weekly list items

Use `browser_run_code` to fetch and parse search results for **all items in a single JavaScript call** — this is critical for token efficiency. `browser_run_code` runs JS in the current page context; it cannot trigger browser navigation. Use `fetch()` to retrieve search pages instead.

### The resolution script

For each item, first determine its type:

```javascript
const isSpecific = item[0] === item[0].toUpperCase() && item[0] !== item[0].toLowerCase();
```

Then:

1. **Build the search query** (max 50 chars including spaces — Ocado silently truncates beyond this):
   - Start with the item name
   - If over 50 chars, drop words from the middle (keep the most specific terms at start/end), truncate at a word boundary

2. **Fetch search results** using `fetch()` from within the script (same-origin, no CORS issues since we're already on ocado.com):
   ```javascript
   const html = await fetch(`/search?q=${encodeURIComponent(query)}`).then(r => r.text());
   const doc = new DOMParser().parseFromString(html, 'text/html');
   ```

3. **Extract the top 5 products** from the parsed document. For each, collect:
   - Product name (from the link/heading in the product card)
   - Current price (£X.XX)
   - Unit price (£X.XX per kg / per litre / per item — Ocado shows this in the card)
   - Deal indicator: look for "was £X.XX" text, or offer badge text like "Half Price" / "Everyday Savers"
   - Review count (to filter out unreviewed products)
   - Add button presence (confirms it's in stock)

4. **Pick the product** based on item type:

   **If specific** (capitalised):
   - Look for a product whose name closely matches the requested name (all key words present)
   - If found → mark as `exact`, add it
   - If not found or out of stock → mark as `unavailable`, do NOT silently substitute. Flag it in the proposed basket so the user can decide.

   **If generic** (lowercase):

   *Quality floor* — skip any product that:
   - Has fewer than 10 reviews (unproven)
   - Has a review score visibly below 3.0 (only skip if score is explicitly shown and bad)

   Prefer products from known quality tiers: Ocado own-brand, M&S, major national brands. Unknown/no-name brands with no reviews should be flagged rather than auto-selected.

   From qualifying products, pick the one with the **lowest unit price** (price per 100g / per litre / per item). If Ocado doesn't show a unit price, fall back to lowest total price adjusted for pack size mentioned in the name.

   *Deal detection*: if a product shows a "was £X.XX" or offer badge, calculate the discount. If ≥20%, mark it as a deal.

5. **Record the result**: item type, chosen product name, price, unit price, deal flag, and the add-button selector.

### Search query truncation helper (include in the script)

```javascript
function buildQuery(item) {
  if (item.length <= 50) return item;
  const words = item.split(' ');
  let query = '';
  for (const word of words) {
    if ((query + ' ' + word).trim().length <= 50) {
      query = (query + ' ' + word).trim();
    }
  }
  return query || words[0].substring(0, 50);
}
```

---

## Step 4 — Scan master list for deals

After resolving the weekly items, do a second pass: for each item on the **master list** that is NOT on the weekly list, search Ocado and check if the first result has a deal indicator showing ≥20% off. If yes, note it as a deal alert.

This pass should be fast — just check for deal badges, don't do full scoring.

---

## Step 5 — Show proposed basket and wait for approval

Present this **before touching the trolley**:

```
📋 Proposed basket — please review:

WEEKLY ITEMS
🎯 M&S Org. British Beef Mince 12% Fat → M&S Select Farms Org. Beef Mince 12% Fat  £7.25  (exact)
✅ chicken breast 500g                 → Ocado British Chicken Breast 500g          £4.80  (£9.60/kg)
✅ semi-skimmed milk 2L               → M&S Organic Semi Skimmed Milk 2 Pints      £1.95  (£0.98/L)
⚡ olive oil 500ml                    → Carapelli Extra Virgin Olive Oil 500ml      £4.50  (was £6.00, -25%)
⚠️  sourdough bread                   → Gail's Sourdough Bloomer                   £3.50  ← low review count
❌ Arla LactoFREE Skimmed Milk Drink  → NOT AVAILABLE — substitute or skip?
❓ free range eggs                    → [multiple matches — see below]

DEAL ALERTS (not on your list this week)
⚡ Ocado Oak Smoked Salmon 240g  £3.75  (was £7.50, -50%)

---
❓ free range eggs — top 3 options:
  1. Ocado Large Free Range Eggs x6    £1.80  (30p/egg)  ★4.1 (240 reviews)
  2. M&S Large Free Range Eggs x6      £2.10  (35p/egg)  ★4.5 (180 reviews)
  3. Ocado Medium Free Range Eggs x6   £1.60  (27p/egg)  ★3.5 (95 reviews)

Estimated total: ~£XX.XX

Reply with any changes (e.g. "use option 2 for eggs", "skip the salmon", "add the salmon deal", "skip Arla") or just say "go ahead" to add everything.
```

**Rules for the display:**
- 🎯 = specific product requested and found exactly
- ✅ = generic item, clean best-value pick
- ⚡ = deal detected (≥20% off)
- ⚠️ = flagged item (low reviews, unknown brand)
- ❌ = specific product requested but not available — always ask before substituting
- ❓ = ambiguous generic match, show top 3 options for user to choose
- Show deal alerts as a separate section — these are bonus suggestions, not automatic adds
- Always show estimated total

**When to show multiple options (❓):**
- Top result has <50 reviews
- Top 3 results have very different unit prices (>40% spread) suggesting different product types
- Item name is very generic (e.g. just "eggs", "milk", "bread")

---

## Step 6 — Process user feedback

Wait for the user's reply. They might say:
- "go ahead" → proceed with the proposed basket as-is
- "use option 2 for eggs" → swap that item
- "skip the salmon" → remove from adds
- "replace sourdough with Taboon Bakery Wholemeal Pitta" → update that item
- "add the salmon deal" → include the deal alert item

Update the resolved list accordingly, then proceed to Step 7.

---

## Step 7 — Add to trolley

Adding to trolley requires real DOM interaction (clicking buttons), so use sequential `browser_navigate` + `browser_click` per item — `browser_run_code` cannot click elements. For each approved item:

1. `browser_navigate` to `https://www.ocado.com/search?q=<query>` (≤50 chars)
2. Click the Add button. Try selectors in order until one works:
   - `[data-test="counter-button"]`
   - `button[aria-label*="Add"]`
   - `button.add-to-trolley` (fallback — Ocado periodically renames classes)
3. Record what was added (aria-label of the button, or product heading if aria-label is absent)

Collect results into added / substituted / not-found buckets.

---

## Step 8 — Final report

```
Ocado shop complete ✓

✅ Added (N items):
  - chicken breast → Ocado British Chicken Breast 500g £4.80
  ...

🔄 Substituted (N items):
  - sourdough bread → Gail's Sourdough Bloomer £3.50 (flagged: low reviews)
  ...

❌ Not added (N items):
  - [anything skipped or failed]
```

---

## Key rules

- **Never add anything to the trolley before the user approves the proposed basket.**
- **Always use `browser_run_code` for bulk operations** — never individual navigate/click per item.
- **50-char search limit**: build queries with `buildQuery()` above.
- **Token efficiency**: use `browser_snapshot` only when you need to confirm login or diagnose a problem. The resolution script runs headlessly via `browser_run_code`.
- **Don't overthink substitutions**: if Ocado returns an obvious match (same product name, similar price), take it. Only flag genuinely ambiguous or suspicious picks.
