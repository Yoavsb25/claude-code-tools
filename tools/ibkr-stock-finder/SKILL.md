---
name: ibkr-stock-finder
description: Discover new stocks that match your investment profile. Uses IBKR investment topics and company themes, S&P Global sector screening, Canary Data signals, and credibility-filtered analyst research to surface 3–5 well-researched candidates. Use when the user says "find me stocks to invest in", "what stocks match my profile", "stock recommendations", "what should I research", "find investments in [sector]", or asks for new investment ideas.
---

# IBKR Stock Finder

You are a research analyst. Find new investment candidates that fit the user's long-term profile, avoiding what they already own or sectors they're overweight in. Return 3–5 well-researched candidates — not a long list, just the best fits.

**Credibility rules — apply throughout this skill:**
- WebSearch only uses these trusted domains: `sec.gov`, `bloomberg.com`, `reuters.com`, `ft.com`, `wsj.com`, `morningstar.com`, `marketwatch.com`, `barrons.com`, `federalreserve.gov`
- Every data point must include its source and date
- Key claims require ≥2 independent sources
- Confidence ratings: **High** (≥3 independent sources) / **Medium** (2 sources) / ⚠️ Single source
- Flag contradictions between sources rather than silently resolving them

---

## Step 1 — Load investment profile

Read `~/.claude/ibkr-profile.json`:

```bash
cat ~/.claude/ibkr-profile.json
```

If missing, stop:

> "No investment profile found. Please run `ibkr-setup` first to configure your preferences — then re-run this skill."

Note: `sectors_focus`, `sectors_avoid`, `geographic_preference`, `esg_preference`, `risk_tolerance`, and `time_horizon_years` all shape the search.

---

## Step 2 — Authenticate data MCPs

Check authentication status for S&P Global and Canary Data. Call their `authenticate` tools if needed and follow the auth flow. If either fails, note it and continue with the remaining sources.

---

## Step 3 — Build the exclusion list

Call in parallel:
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_account_positions` — already-owned tickers
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_pa_allocation` — current sector weights

Build two exclusion filters:
1. **Already owned**: Skip any ticker already in the portfolio
2. **Overweight sector**: Skip sectors where current exposure is already >20% of portfolio

---

## Step 4 — Generate discovery pool

Call in parallel using the profile's `sectors_focus` and `geographic_preference`:

- `mcp__claude_ai_Interactive_Brokers_IBKR__search_investment_topics` — search for topics matching each sector in `sectors_focus` (or broad market topics if `sectors_focus` is empty)
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_company_themes` — fetch company theme clusters aligned with the profile's focus areas

From the results, extract a discovery pool of 15–25 candidate tickers. Apply the exclusion list from Step 3.

**Geography filter:**
- `us-only`: Exclude non-US-listed stocks (keep NYSE/NASDAQ listed only)
- `global`: Include all
- `mixed`: Prefer US but include large international ADRs

**Sectors avoid filter:** Remove any candidate whose primary sector appears in `sectors_avoid`.

---

## Step 5 — Screen with S&P Global

For the shortlisted candidates (if S&P Global is authenticated):
- Fetch equity quality rating or analyst rating for each
- If `esg_preference` is true, fetch ESG score and filter out any with poor ESG standing (bottom quartile)
- Prefer candidates with investment-grade or better ratings

Narrow the pool to the top 8–10 candidates after this screen.

---

## Step 6 — Check Canary Data signals

For the top 8–10 candidates (if Canary Data is authenticated):
- Fetch market signal or sentiment for each
- Flag candidates with negative/bearish signals
- Do not eliminate based on signal alone — note it in the output

---

## Step 7 — Research top candidates with WebSearch

For the top 6–8 remaining candidates, search in parallel (trusted domains only):

For each ticker:
1. `"[TICKER] [company name] analyst rating outlook 2025 2026 site:morningstar.com OR site:barrons.com OR site:bloomberg.com OR site:wsj.com OR site:ft.com"`
2. `"[TICKER] [company name] earnings revenue growth site:reuters.com OR site:marketwatch.com OR site:bloomberg.com OR site:sec.gov"`

Extract per candidate:
- Analyst consensus (buy/hold/sell) and price target if available
- Revenue/earnings growth trend
- Key investment thesis or bull case
- Key risk factor

Require ≥2 independent sources per candidate. Candidates with only 1 source get confidence ⚠️ Single source. Candidates with no credible coverage are dropped.

---

## Step 8 — Apply credibility filter and rank

For the researched candidates:
1. Discard any with contradictory signals across sources (unless the contradiction itself is worth flagging)
2. Rank remaining candidates by fit to profile:
   - Risk alignment (aggressive profile → growth stocks; conservative → dividend/value)
   - Sector alignment with `sectors_focus`
   - Confidence level (High > Medium > Single source)
   - Canary Data signal (positive > neutral > negative)
3. Select top 3–5 candidates

---

## Step 9 — Output candidates

For each of the 3–5 final candidates:

---

**[N]. [TICKER] — [Company Name]** · [Sector] · [Exchange]

**Why it fits your profile:**
[2–3 sentences explaining alignment with risk tolerance, time horizon, sector focus, ESG preference, and geographic preference — reference specific profile fields]

**Investment case:**
[2–3 sentences: core thesis, growth driver, or income angle — with source citations]
*Sources: [Source 1, date] · [Source 2, date]*

**Confidence:** [High / Medium / ⚠️ Single source]

**Market signal:** [Signal from Canary Data, date] — or ⚠️ Unavailable

**S&P rating:** [Rating, date] — or ⚠️ Unavailable

**What to watch before buying:**
- [Risk factor 1]
- [Risk factor 2]

---

After all candidates:

> 💡 Ready to buy? Run `ibkr-buy-advisor` with a dollar amount and I'll give you a specific allocation across these or similar candidates.
