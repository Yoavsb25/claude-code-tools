---
name: amazon-shopper
description: Use when a run-todos buy/order task is classified as Amazon-appropriate — physical goods, electronics, clothing, accessories, home items (not food/grocery, not flights/services/bookings).
disable-model-invocation: true
---

# Amazon Shopper

Searches Amazon UK for the item, picks the best match (rating ≥3.5, ≥20 reviews, Prime-preferred), shows it for confirmation, then adds it to the basket. Never completes checkout — basket only.

---

## Step 1 — Ambiguity safety net

Re-check the task for sufficient detail before searching.

**Flag and stop if** the product has high variation and a key spec is missing (size, quantity, colour, model, or budget):

| Task | Action |
|---|---|
| "Buy 2 iPhone 17 cases" | Proceed — specific |
| "Buy a white pocket square" | Proceed — specific |
| "Buy batteries" | Proceed — use AA 4-pack as safe default, note assumption |
| "Buy a TV" | Stop — ask: "What size and rough budget?" |
| "Buy a jacket" | Stop — ask: "What size, and is this casual or smart?" |

If flagged: tell the user exactly what's missing. Do not guess on high-variance products.

---

## Step 2 — Navigate to Amazon UK and confirm login

Navigate to `https://www.amazon.co.uk`. Take a snapshot. Look for the user's name in the nav bar ("Hello, [Name]"). If you see "Sign in" instead: "Please sign in to Amazon and let me know when you're ready."

---

## Step 3 — Search and pick best match

Use `browser_run_code` to search and parse results in one call:

```javascript
const query = encodeURIComponent("TASK_DESCRIPTION");
const html = await fetch(`/s?k=${query}`).then(r => r.text());
const doc = new DOMParser().parseFromString(html, 'text/html');

const results = [];
doc.querySelectorAll('[data-component-type="s-search-result"]').forEach(el => {
  // Skip sponsored results
  if (el.querySelector('.s-sponsored-label-info-icon') ||
      el.querySelector('[data-component-type="sp-sponsored-result"]')) return;

  const titleEl = el.querySelector('h2 a span');
  const title = titleEl?.textContent?.trim();
  if (!title) return;

  const url = el.querySelector('h2 a.a-link-normal')?.getAttribute('href');
  const priceEl = el.querySelector('.a-price .a-offscreen');
  const price = priceEl?.textContent?.trim();

  const ratingText = el.querySelector('.a-icon-star-small .a-icon-alt, [class*="a-star"] .a-icon-alt')?.textContent;
  const rating = ratingText ? parseFloat(ratingText) : null;

  const reviewText = el.querySelector('span[aria-label*="ratings"], .a-size-base.s-underline-text')
    ?.textContent?.replace(/,/g, '');
  const reviews = reviewText ? parseInt(reviewText) : 0;

  const prime = !!el.querySelector('[aria-label="Amazon Prime"], .s-prime');

  results.push({ title, url, price, rating, reviews, prime });
});

// Filter: ≥3.5 stars (if rating shown), ≥20 reviews
const candidates = results.filter(r =>
  (r.rating === null || r.rating >= 3.5) && r.reviews >= 20
);

// Sort: Prime first, then by rating descending
candidates.sort((a, b) => {
  if (a.prime !== b.prime) return a.prime ? -1 : 1;
  return (b.rating || 0) - (a.rating || 0);
});

return JSON.stringify(candidates.slice(0, 3));
```

If no candidates pass the filter, take the top raw result and flag it with ⚠️.

---

## Step 4 — Show pick and wait for confirmation

```
🛍 Amazon pick for: "<task>"

  <title>
  £<price>  ★<rating> (<N> reviews)  [Prime]
  amazon.co.uk/<url>

Add this to your basket? (yes / pick a different one / skip)
```

Wait for the user's reply before touching the basket.

---

## Step 5 — Add to basket

1. `browser_navigate` to `https://www.amazon.co.uk<url>`
2. If quantity was specified in the task (e.g. "2 cases"), set the quantity field: `select#quantity` or `input[name="quantity"]`
3. Click Add to Basket — try selectors in order:
   - `#add-to-cart-button`
   - `input[name="submit.add-to-cart"]`
   - `button:has-text("Add to Basket")`
4. Take a snapshot to confirm the basket notification appeared ("Added to Basket" or cart count incremented)

---

## Step 6 — Report back

```
✅ Added to basket:
   <product name>
   £<price>  ★<rating> (<N> reviews)
   https://www.amazon.co.uk<url>
```

If add failed: `❌ Could not add to basket — <reason>. URL: <url>`

---

## Key rules

- **Basket only** — never attempt checkout or payment.
- **Never proceed on vague tasks** — stop at Step 1 if key specs are missing.
- **Use `browser_run_code` for search** — never navigate item-by-item during research.
- **One item per invocation** — `run-todos` invokes this skill once per qualifying buy task.
- **Avoid unbranded generics for electronics** — prefer known brands even if rated.
