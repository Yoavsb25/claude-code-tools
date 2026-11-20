# ocado-deals 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `ocado-deals` skill so it judges offers by unit price against what the household usually buys (from Ocado order history) and reports only swaps, stock-ups and new finds that save real money.

**Architecture:** Skill-only (`type: "skill"`, no Python). SKILL.md drives Claude: load/refresh a baseline file from order history via Claude in Chrome → scan offer pages (existing discovery logic kept) → score with fixed rules → three-section report. Evals in `tools/ocado-deals/evals/evals.json` play the role of tests.

**Tech Stack:** Markdown skill, JSON manifest + evals, Claude in Chrome MCP (`mcp__claude-in-chrome__*`), WebFetch for public offer pages, npm scripts `validate` / `generate-registry`.

**Spec:** `docs/superpowers/specs/2026-11-20-ocado-deals-value-design.md`

## Global Constraints

- Groceries only (food & drink). Exclude household/cleaning, toiletries/personal care, baby non-food, pet, clothing, homeware.
- Compare by unit price (per kg / L / each). Never rank by the product's own was-price or by % off alone.
- Acceptable brands: Ocado own-brand, M&S (on Ocado), major national brands; skip unknown brands with <10 reviews.
- Swap: ≥10% cheaper per unit AND (≥ £1/week OR ≥ £20/year) at usual quantity.
- Stock-up: bought in ≥2 orders in history, ≥25% cheaper per unit than usual, keeps; suggest ~4–8 weeks' supply capped by shelf life; show extra spend now and total saving.
- New find: not in history, ≥30% cheaper per unit than everyday own-brand price for that type; max 5.
- Baseline file `~/.claude/ocado-deals/usual.json` (already seeded 2026-11-20 from 12 real orders; never committed); history window ~3 months; refresh when missing or older than 30 days.
- Evals use generic products only — the repo is public.
- Never add to trolley (that is `ocado-shopper`).
- Manifest must pass `npm run validate`; `dest` under `~/.claude/skills/`.

## Review Focus

1. **Logged out of Ocado when refreshing history** — skill must stop and ask the user to log in, not silently produce a report with no baseline. → eval in Task 1.
2. **Thin history (new account, <2 orders)** — no stock-ups possible; swaps/new finds still work; report says history is thin. → eval in Task 1.
3. **Unit mismatch (per each vs per kg, multipacks)** — never compare across units; derive unit price from pack size or skip the comparison. → eval in Task 1.
4. **Usual product itself on offer** — that's a stock-up candidate (or nothing), never a "swap" to the same product. → eval in Task 1.
5. **Offer page discovery returns nothing (URLs changed / blocked)** — report which sections failed; don't present an empty report as "no deals". → eval in Task 1.

---

### Task 1: Evals that pin the new behaviour

**Files:**
- Create: `tools/ocado-deals/evals/evals.json` (same shape as `tools/ocado-shopper/evals/evals.json`: `skill_name`, `evals[] {id, prompt, expected_output, assertions[]}`)

**Interfaces:**
- Produces: eval ids 1–9 referenced by Task 3's dry run.

- [ ] **Step 1: Write the evals**

Each eval's prompt may embed fixture data (a baseline JSON snippet + offer list) so it's checkable without the live site. Required evals and assertions:

1. "what Ocado offers are worth it this week?" (live) — report has exactly three sections Swaps / Stock up this week / New this week; each row shows unit prices and £/year; header shows total £/year; no non-grocery items.
2. Fixture: usual = Brand X coffee £10.00 (200g), offer Brand X now £9.90; Ocado coffee 200g £5.00 → assertion: the £9.90 offer is **not** shown as a deal; Ocado coffee shown as a swap only if thresholds met at usual quantity.
3. Fixture: usual item £0.50, bought 1/month; alternative £0.40 → **not** shown (20% but < £20/yr).
4. Fixture: usual Lurpak 500g £4.50, 0.5/week; Ocado Butter 500g £2.80 → swap shown, saves ≈ £44/yr (1.70 × 26).
5. Fixture: not in history, Ocado Beef Burgers 1kg £1.00, everyday own-brand burgers £6.50/kg → appears under New this week with % below typical.
6. Fixture: usual olive oil 1L £9.00 bought in 4 orders, now £4.50 → Stock up row with quantity, extra spend now, saving; not listed as a swap.
7. Fixture: Ocado not logged in on refresh → skill asks user to log in; no report produced.
8. Fixture: history has 1 order → report notes thin history; Stock-up section says none possible yet.
9. Fixture: offer priced per each vs usual priced per kg with no pack weight → comparison skipped, not guessed.
10. Fixture: baseline_weekly_spend 60.00, savings_log has 2 entries (£41/yr, £13.50/yr) → header shows "Baseline £60.00/week" and "£41/year + £13.50 one-off locked in from 2 accepted suggestions".
11. Fixture: after a report, user says "I took the butter swap" → skill appends one savings_log entry with kind "swap" and its £/yr.

- [ ] **Step 2: Benchmark the current (1.0.0) skill**

Run evals 2–11 by hand with the 1.0.0 SKILL.md loaded; record pass/fail per assertion in `tools/ocado-deals/evals/benchmark.md` (columns: eval, 1.0.0, 2.0.0). Expected: 1.0.0 fails at least evals 2, 3, 4, 6, 10, 11.

- [ ] **Step 3: Commit**

```bash
git add tools/ocado-deals/evals/evals.json tools/ocado-deals/evals/benchmark.md
git commit -m "ocado-deals: evals for value-vs-baseline behaviour"
```

---

### Task 2: Rewrite SKILL.md

**Files:**
- Modify: `tools/ocado-deals/SKILL.md` (full rewrite; keep Step 1 URL discovery table and Big Brand Offers URL from 1.0.0)

**Interfaces:**
- Consumes: eval list from Task 1.
- Produces: baseline file schema (exact, used by later runs):
  ```json
  { "updated": "YYYY-MM-DD", "weeks_covered": 12,
    "items": [{ "name": "...", "type": "butter, salted", "pack": "500g",
                "unit_price": 9.00, "unit": "kg|l|each",
                "orders": 6, "units_per_week": 0.5 }] }
  ```

- [ ] **Step 1: Frontmatter** — `name: ocado-deals`; description triggers on Ocado offers, "is this deal worth it", "what should I stock up on", "cheaper swaps on Ocado", "cut my grocery bill".

- [ ] **Step 2: "Your rules" block at the top** — every threshold from Global Constraints as a table, with a line telling the user they can edit these numbers.

- [ ] **Step 3: Step 1 — Baseline.** Read `~/.claude/ocado-deals/usual.json`. If missing or `updated` > 30 days ago, refresh exactly as the spec's step 1 describes (orders list → navigate each `/orders/<id>/details`, wait for `Price:`, parse `[хx]` line items, sessionStorage + small-slice readback, clear keys, close tab). Keep regulars (≥2 orders), groceries only; set `baseline_weekly_spend`; preserve any existing `savings_log`. Include the working in-page parser as a code block in SKILL.md.

- [ ] **Step 4: Step 2 — Scan offers.** Keep 1.0.0 discovery + extraction (category pages, multi-buy bundle pages, Big Brand Offers), groceries only. Every offer gets `unit_price` + `unit`; multi-buy unit price = bundle total ÷ N; derive from pack size when not shown; if neither is possible, drop the offer.

- [ ] **Step 5: Step 3 — Score.** For each baseline item, find equivalent offers (same `type` and spec; brand/pack may differ). Classify:
  - same product on offer & regular & keeps & ≥25% → Stock-up
  - different product meeting swap rule → Swap (`£/yr = (usual_unit_price − offer_unit_price) × qty_per_week_in_units × 52`)
  - For baseline items in the top 10 by annual spend with no offer hit, one Ocado search for the `type` to find a cheaper everyday equivalent → Swap if rule met.
  - Offers matching no baseline type → New find if ≥30% below everyday own-brand unit price for that type (one search per candidate to get the reference); keep top 5 by % below.

- [ ] **Step 6: Step 4 — Report + savings log.** Exact layout from the spec's report block (title with date and total £/year, baseline/locked-in line, three tables, "nothing worth it this week" for empty sections, failed-section notes, thin-history note, closing line pointing to `ocado-shopper`).

- [ ] **Step 7: Step 5 — Record accepted suggestions.** When the user names suggestions they took, append `{date, item, kind, saving_per_year}` to `savings_log` and confirm the new locked-in total.

- [ ] **Step 8: Run evals 2–11 by hand** with the new SKILL.md loaded; fill the 2.0.0 column of `benchmark.md`. Expected: all pass. Fix wording and re-run until they do.

- [ ] **Step 9: Commit**

```bash
git add tools/ocado-deals/SKILL.md tools/ocado-deals/evals/benchmark.md
git commit -m "ocado-deals 2.0: judge offers against usual purchases"
```

---

### Task 3: Manifest, registry, live run

**Files:**
- Modify: `tools/ocado-deals/manifest.json` — `version: "2.0.0"`, `complexity: "intermediate"`, description (≤200 chars): "Finds Ocado offers that actually save money — compares unit prices against what you usually buy and suggests swaps, stock-ups and standout new deals.", tags add `"savings"`, `"order-history"`, `requirements.mcp_servers: ["claude-in-chrome"]`.
- Modify (generated): `registry.json`, `README.md`

- [ ] **Step 1: Validate** — Run: `npm run validate`. Expected: all manifests `valid`.

- [ ] **Step 2: Regenerate** — Run: `npm run generate-registry`. Expected: `registry.json` and README row for ocado-deals show 2.0.0 and the new description.

- [ ] **Step 3: Install locally and live run** — copy `SKILL.md` to `~/.claude/skills/ocado-deals.md`; run eval 1 against real Ocado with the user logged in. Expected: existing `usual.json` reused (no refresh needed), three-section report, every row with unit prices and £/yr, no non-grocery items. Show the report to the user.

- [ ] **Step 4: Commit**

```bash
git add tools/ocado-deals/manifest.json registry.json README.md
git commit -m "ocado-deals 2.0.0: manifest and registry"
```
