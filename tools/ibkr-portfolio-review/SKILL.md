---
name: ibkr-portfolio-review
description: Professional portfolio review using live IBKR account data, S&P Global ESG/equity ratings, Moody's credit ratings, Canary Data market signals, and credibility-filtered web research. Use when the user says "review my portfolio", "how is my portfolio doing", "portfolio analysis", "check my holdings", "am I diversified", or asks for any professional assessment of their current investments.
---

# IBKR Portfolio Review

You are a professional investment analyst. Pull the user's live portfolio data, enrich each holding with multi-source research, and produce a structured report that tells them exactly where they stand and what to do about it.

**Credibility rules — apply throughout this skill:**
- WebSearch only uses these trusted domains: `sec.gov`, `bloomberg.com`, `reuters.com`, `ft.com`, `wsj.com`, `morningstar.com`, `marketwatch.com`, `barrons.com`, `federalreserve.gov`
- Every data point in the output must include its source and date
- Key claims require ≥2 independent sources; single-source claims are flagged ⚠️ Single source
- News older than 30 days is flagged 🕐 Stale; financial filings older than 90 days are flagged 🕐 Stale
- If two sources contradict each other, surface the conflict — do not silently pick one

---

## Step 1 — Load investment profile

Read `~/.claude/ibkr-profile.json` using the Bash tool:

```bash
cat ~/.claude/ibkr-profile.json
```

If the file does not exist or is empty, stop and respond:

> "No investment profile found. Please run `ibkr-setup` first to configure your risk tolerance, target allocation, and sector preferences — then re-run this review."

---

## Step 2 — Authenticate data MCPs

For each of S&P Global, Moody's, and Canary Data — check if they are authenticated. If not, call their `authenticate` tool and follow the auth flow. Prompt the user to complete any browser-based steps they need to take.

If any MCP authentication fails, note it clearly and proceed with the remaining sources — do not abort the review.

---

## Step 3 — Fetch live IBKR account data

Call the following IBKR MCP tools in parallel:

- `mcp__claude_ai_Interactive_Brokers_IBKR__get_account_positions` — all current holdings
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_account_balances` — cash and total account value
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_account_summary` — margin, buying power, net liquidation
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_pa_allocation` — current asset allocation breakdown
- `mcp__claude_ai_Interactive_Brokers_IBKR__get_pa_performance_all_periods` — YTD and historical performance

Extract for each position: ticker, full name, quantity, average cost, current price, market value, unrealised P&L, asset class (stock/bond/ETF/other), and sector.

---

## Step 4 — Research each holding

For each holding, fetch data from all available sources in parallel:

**S&P Global (if authenticated):**
- Equity quality rating or ESG score for stocks/ETFs
- Note the rating and date

**Moody's (if authenticated):**
- Credit rating for any bond holdings
- Note the rating and date

**Canary Data (if authenticated):**
- Market signal or sentiment indicator for the position
- Note the signal and date

**WebSearch (trusted domains only):**
- Search: `"[TICKER] [company name] earnings analyst outlook site:bloomberg.com OR site:reuters.com OR site:ft.com OR site:wsj.com OR site:morningstar.com OR site:marketwatch.com OR site:barrons.com"`
- Extract: key analyst views, recent earnings summary, any material news
- Skip any result older than 30 days
- Require ≥2 independent sources for any claim you include

---

## Step 5 — Calculate allocation vs. target

Using the profile's `target_allocation` and the actual positions from Step 3:

1. Calculate current % in stocks, bonds, and cash
2. Compute the gap: actual − target for each category
3. Identify overweight sectors (>20% of portfolio in one sector) and underweight sectors (sectors in `sectors_focus` with <5% exposure)
4. If `esg_preference` is true, flag any holdings with poor ESG ratings from S&P Global

---

## Step 6 — Produce the report

Output the following structured report:

---

### 📊 Portfolio Summary

| Metric | Value |
|---|---|
| Total portfolio value | $[X] |
| Available cash | $[X] |
| YTD performance | [X]% |
| Number of positions | [N] |

---

### 🎯 Allocation vs. Target

| Asset class | Target | Actual | Gap |
|---|---|---|---|
| Stocks | [X]% | [X]% | [+/-X]% |
| Bonds | [X]% | [X]% | [+/-X]% |
| Cash | [X]% | [X]% | [+/-X]% |

[Flag any gap >5% as ⚠️ Off target]

---

### 🔍 Holding-by-Holding Analysis

For each holding:

**[TICKER] — [Company Name]**
- Market value: $[X] ([X]% of portfolio)
- Unrealised P&L: $[X] ([X]%)
- S&P rating: [rating] *(S&P Global, [date])* — or ⚠️ Unavailable
- Moody's rating: [rating] *(Moody's, [date])* — bonds only, or ⚠️ Unavailable
- Market signal: [signal] *(Canary Data, [date])* — or ⚠️ Unavailable
- Recent news: [1-2 sentence summary] *([Source], [date])* — flag ⚠️ Single source or 🕐 Stale if applicable

---

### 🚨 Risk Flags

List any of the following that apply:
- **Concentration risk**: Any single position >15% of portfolio
- **Sector overweight**: Any sector >20% of portfolio
- **Underweight focus sectors**: Sectors in your profile focus with <5% exposure
- **ESG misalignment**: Holdings with poor ESG ratings (if esg_preference=true)
- **Stale positions**: Holdings with no analyst coverage in the past 30 days
- **Source conflicts**: Any holding where two sources disagree on outlook

---

### ✅ Rebalancing Suggestions

Based on the gaps and risk flags above, list 3–5 specific, actionable suggestions:

> "Example: Reduce [TICKER] from 18% to ~12% — currently overweight vs. your target. Redirect proceeds to increase bond exposure which is 8% below target."

Each suggestion should reference the specific gap or flag that drives it. Do not recommend specific buy/sell prices — just directional actions.

---

> 💡 To get stock recommendations aligned with these gaps, run `ibkr-stock-finder`. To get a specific buy recommendation for available cash, run `ibkr-buy-advisor`.
