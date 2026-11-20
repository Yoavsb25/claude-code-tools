# ocado-deals benchmark — 1.0.0 vs 2.0.0

Evals: `evals.json`. Each eval was run by reading the fixture against the skill's rules, by hand. Eval 1 is the live run.

| Eval | What it checks | 1.0.0 | 2.0.0 |
|---|---|---|---|
| 1 | Live three-section report, groceries only | FAIL — category tables ranked by was-price, no swaps/stock-ups/new | PASS — live 20 Nov 2026: 4 swaps (~£262/yr), 1 stock-up, 0 new finds (all branded 30–56% offers still dearer than own-brand everyday prices); no non-grocery rows |
| 2 | £10 → £9.90 trap; cheaper everyday swap | FAIL — lists £9.90 as a £0.10 deal; never suggests the non-offer swap | PASS — 1% cut ignored; Ocado coffee swap £260/yr via everyday search |
| 3 | 20% off a 50p item is ignored | FAIL — shows it as 20% off | PASS — £1.20/yr < £20 threshold, silent |
| 4 | Butter swap ≈ £44/yr | FAIL — no baseline, no swap concept | PASS — £9.00 vs £5.60/kg, £44.20/yr |
| 5 | Burgers £1/kg → New this week | FAIL — appears in Meat table by £ saved; no "new" section | PASS — New this week, 85% below |
| 6 | Olive oil stock-up, qty 2 | FAIL — listed as a single deal, no quantity | PASS — Stock-up, qty 2 (0.33/wk × 4–8 wk), spend £9, save £9 |
| 7 | Logged out → ask to log in | FAIL — no history step; report produced with no baseline | PASS — stops and asks to log in |
| 8 | Thin history (refresh path) keeps all lines; swap found | FAIL — no history concept | PASS — <2 orders keeps every grocery line; granola swap £130/yr; stock-up 'none possible yet' |
| 9 | Per-each vs per-kg not guessed | PASS — discards deals it can't price | PASS — dropped, units not comparable |
| 10 | Baseline + locked-in savings header | FAIL — no savings log | PASS — Baseline £60.00/week · £54.50/year from 2 since 1 Nov 2026 |
| 11 | Accepted swap logged | FAIL — no savings log | PASS — one swap entry, 44.20 |

| 12 | Empty scan reported as failure | FAIL — prints empty tables | PASS — 0 cards = failed section; no "nothing worth it" |
| 13 | 1% offer on usual item doesn't skip everyday search | FAIL — no everyday search | PASS — search runs unless item already produced a Swap |
| 14 | Temporary offer isn't annualised; one section only | FAIL — listed as 50% deal | PASS — not a Swap (£13/yr at everyday price); Stock-up with one-off saving |

Eval 1 assertions were tightened after review (layout per section, Chrome load on fresh baseline, yearly/one-off split); the 20 Nov live run predates that wording — its output had all three sections with the required columns except the stock-up unit-price column, now added to the layout.

**1.0.0: 1/14 pass. 2.0.0: 13/13 fixture evals pass; eval 1 (live) passed on 20 Nov under the original wording — re-run live to confirm the tightened assertions.**
