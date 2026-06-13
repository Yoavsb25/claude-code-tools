---
name: ocado-deals
description: Scans Ocado offer pages — category pages and dedicated multi-buy bundles (3 for £12, 2 for £X, etc.) — to surface the best grocery deals grouped by food category. Use this skill whenever the user mentions Ocado offers, wants to find grocery deals, asks what's cheap on Ocado this week, or wants to plan their shop around savings — even if they don't explicitly say "deals" or "scan".
---

# Ocado Deals Scanner

Scan Ocado's public offer pages (category pages + dedicated multi-buy bundle pages), calculate the true per-unit saving for every deal, and present the top picks grouped by food category.

---

## Step 1 — Discover current URLs

Offer page URLs embed IDs that can change. Fetch the main offers index first:

```
Fetch: https://www.ocado.com/offers
```

Extract href paths for **all** of these (prepend `https://www.ocado.com`):

| What to look for | Example path segment |
|---|---|
| Fresh & Chilled Food | `/promotions/fresh-chilled-food/…` |
| Food Cupboard | `/promotions/food-cupboard/…` |
| Bakery | `/promotions/bakery/…` |
| Multi-buy bundle pages | any link whose text or path contains "for £" (e.g. "3 for £12", "2 for £10", "Buy any 3 for £12") |

Collect every distinct multi-buy bundle URL visible on the offers index — these are dedicated pages listing all products eligible for that bundle deal.

Also always include this fixed URL (it does not appear on the offers index but contains food deals):

| Page | URL |
|---|---|
| Big Brand Offers | `https://www.ocado.com/categories/events-inspiration/big-brand-offers/fecb2247-6f0e-4e89-85d4-63b310a6db07` |

If no URL is found for a section, skip it and note it in the output.

---

## Step 2 — Fetch all pages

Fetch **all** discovered URLs in parallel. For each page, extract every product with a genuine promotion:

### 2a — Category pages (Fresh & Chilled, Food Cupboard, Bakery)

For each product extract:

**Single-item deals** (struck-through "was £X.XX" price):
| Field | Source |
|---|---|
| Name | Product heading |
| Current price (£) | Highlighted/red price |
| Was price (£) | Struck-through or "was £X.XX" |
| Unit price | Price per kg / litre shown in smaller text |

**Mixed multi-buy deals appearing on category pages** (e.g. "Buy 2 for £4"):
| Field | Source |
|---|---|
| Name | Product heading |
| Normal per-unit price (£) | The per-unit price shown without the deal |
| Deal condition | e.g. "2 for £4" |
| Deal price per unit (£) | Deal total ÷ N |

If a category page has pagination, also fetch page 2 (`&page=2`).

### 2c — Big Brand Offers page

This page mixes food and non-food items. Apply the same extraction as 2a (single-item deals + mixed multi-buy deals), but **skip non-food products** (household cleaners, laundry, personal care, pet food, baby non-food, etc.) — only extract products that belong to one of the five food groups in Step 4.

### 2b — Dedicated multi-buy bundle pages (e.g. "3 for £12")

These pages list many products all sharing the same bundle price (e.g. any 3 items for £12). For each product:

| Field | Source |
|---|---|
| Name | Product heading |
| Weight/size | Pack size shown (e.g. 300g) |
| Normal price per unit (£) | Calculate from the per-kg/litre price shown × pack weight |
| Deal price per unit (£) | Bundle total ÷ N (e.g. £12 ÷ 3 = £4.00) |
| Food category | Infer from section headers or product type (Chicken, Fish, Beef, etc.) |

**Normal price calculation for bundle pages:**  
`normal_price = (price_per_kg × weight_g) / 1000`  
e.g. M&S Chicken Tenders 300g at £17.50/kg → normal = £5.25, deal = £4.00, saving = £1.25

---

## Step 3 — Calculate savings

**Single-item deals:**
- Saving = Was − Now
- % off = (Saving ÷ Was) × 100

**Multi-buy deals (both category-page and bundle-page):**
- Deal price per unit = Bundle total ÷ N
- Saving per unit = Normal price − Deal price per unit
- % off = (Saving ÷ Normal price) × 100
- Only include if you have the normal per-unit price to compare against

Discard any deal where you cannot calculate both normal and deal price (no orphan bundles without a baseline).

---

## Step 4 — Group by food category and present

Assign every deal to one of these five food groups based on the product type:

| Group | What belongs here |
|---|---|
| **Meat & Poultry** | Chicken, beef, pork, lamb, bacon, sausages, burgers, duck |
| **Fish & Seafood** | Salmon, tuna, cod, prawns, fishcakes, seafood mixes |
| **Deli & Dairy** | Cheese, butter, eggs, milk, yogurt, ham, charcuterie, olives, houmous |
| **Bakery** | Bread, wraps, bagels, crumpets, rolls, pastries, cakes |
| **Pantry & Snacks** | Tinned goods, pasta, oil, condiments, crisps, chocolate, coffee, tea, nuts, cereal |

Within each group, sort deals by **saving per unit descending**. Take the **top 5–8 deals** per group.

Output format:

```
## Ocado Best Deals — [DATE]

### Meat & Poultry
| # | Product | Was/unit | Now/unit | Save/unit | % Off | Deal |
|---|---------|----------|----------|-----------|-------|------|
| 1 | M&S British 4 Chicken Breast Steaks (500g) | £5.00 | £4.00 | £1.00 | 20% | 3 for £12 |
...

### Fish & Seafood
...

### Deli & Dairy
...

### Bakery
...

### Pantry & Snacks
...
```

The "Deal" column shows "single" for regular price-off items, or the bundle condition (e.g. "3 for £12") so the user knows how many units to buy.

After all five tables, add three callouts — verify these by re-scanning the displayed numbers, not from memory:
- **Biggest saver overall**: product and group with the highest Save/unit
- **Best % off overall**: product and group with the highest % Off
- **Best unit price**: cheapest price-per-kg or per-litre among all deals shown

Keep the output tight. The tables are the deliverable — no padding.

---

## Pairing with ocado-shopper

If the user wants to add any of these deals to their trolley after reviewing the list, that is handled by the `ocado-shopper` skill — suggest it if they ask.
