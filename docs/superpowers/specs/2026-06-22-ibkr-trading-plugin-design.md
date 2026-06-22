# IBKR Investment Skills — Design Spec
**Date:** 2026-06-22
**Status:** Approved

## Context

The user is a long-term investor managing a portfolio via Interactive Brokers. Three pain points drove this design:
1. Doesn't know which stocks to buy
2. Has no professional reviewing the portfolio
3. Wants tailored, researched recommendations

The IBKR MCP server is already connected in the user's Claude Code environment. S&P Global, Moody's, and Canary Data MCP servers are registered and available pending one-time authentication.

## Goals

- Surface professional-quality portfolio analysis on demand
- Provide researched, profile-aware stock discovery
- Give specific, citation-backed buy recommendations when cash is ready to deploy
- Never auto-execute trades — output is always a recommendation the user confirms in IBKR

## Non-Goals

- Active trading, day trading, or options strategies
- Automated / scheduled portfolio monitoring
- Executing or placing orders via IBKR MCP

## Architecture

Four focused skills, each in `tools/<name>/`. All are type `skill` (SKILL.md only, no Python).

```
tools/
  ibkr-setup/           # One-time profile capture
  ibkr-portfolio-review/  # Professional portfolio analysis
  ibkr-stock-finder/    # Discover new investment candidates
  ibkr-buy-advisor/     # Tailored buy recommendation for specific cash amount
```

Shared state: `~/.claude/ibkr-profile.json` — written by `ibkr-setup`, read by the other three.

## Shared Profile Schema (`ibkr-profile.json`)

```json
{
  "risk_tolerance": "conservative | moderate | aggressive",
  "time_horizon_years": 10,
  "sectors_focus": ["technology", "healthcare"],
  "sectors_avoid": ["tobacco", "gambling"],
  "geographic_preference": "global | us-only | mixed",
  "esg_preference": true,
  "target_allocation": {
    "stocks_pct": 80,
    "bonds_pct": 15,
    "cash_pct": 5
  },
  "notes": "Free-text additional preferences"
}
```

## Data Sources

| Source | What it provides | Used by |
|---|---|---|
| IBKR MCP | Live positions, balances, price history, performance, investment topics, company themes | All three non-setup skills |
| S&P Global MCP | ESG ratings, equity research, sector analysis, valuation data | portfolio-review, stock-finder, buy-advisor |
| Moody's MCP | Credit/bond ratings | portfolio-review |
| Canary Data MCP | Market signals, alternative data, market regime | portfolio-review, stock-finder, buy-advisor |
| WebSearch | News, analyst reports, earnings, sector trends | All three non-setup skills |

WebSearch is restricted to a trusted domain whitelist: `sec.gov`, `bloomberg.com`, `reuters.com`, `ft.com`, `wsj.com`, `morningstar.com`, `marketwatch.com`, `barrons.com`, `federalreserve.gov`.

## Credibility Filtering (all skills)

1. **Source whitelist** — WebSearch only trusts the domains above; social media, Reddit, and anonymous blogs are ignored
2. **Multi-source corroboration** — any key claim must appear in ≥2 independent sources; single-source claims are flagged "single-source, treat with caution"
3. **Cited output** — every data point includes source name and date
4. **Freshness check** — news >30 days old is flagged; financial filings >90 days old are flagged
5. **Contradiction flagging** — if two sources disagree on a key metric, the skill surfaces the conflict explicitly

## Individual Skill Designs

### `ibkr-setup`
- **Trigger:** "set up my IBKR profile" / "update my investment preferences"
- **Complexity:** simple
- **Flow:** Asks 7 questions in sequence (risk tolerance, time horizon, sectors focus, sectors avoid, geographic preference, ESG preference, target allocation). Saves to `~/.claude/ibkr-profile.json`. Confirms saved values at the end.
- **No MCP calls required**

### `ibkr-portfolio-review`
- **Trigger:** "review my portfolio" / "how is my portfolio doing"
- **Complexity:** intermediate
- **MCP servers:** interactive-brokers, s-p-global, moodys, canary-data
- **Flow:**
  1. Load profile; abort with setup prompt if missing
  2. Fetch live positions, balances, and performance from IBKR
  3. For each holding: fetch S&P Global ESG/equity rating, Moody's rating (bonds only), Canary Data signal
  4. WebSearch recent news for each holding (trusted domains, <30 days)
  5. Calculate actual vs. target allocation gap
  6. Produce structured report:
     - Portfolio summary (total value, asset breakdown)
     - Allocation vs. target (with gap analysis)
     - Holding-by-holding: rating, signal, recent news, cited sources
     - Risk flags (concentration, sector overweight, ESG misalignment)
     - Rebalancing suggestions

### `ibkr-stock-finder`
- **Trigger:** "find me stocks to invest in" / "what stocks match my profile"
- **Complexity:** intermediate
- **MCP servers:** interactive-brokers, s-p-global, canary-data
- **Flow:**
  1. Load profile; abort with setup prompt if missing
  2. Fetch current positions (to exclude already-owned and overweight sectors)
  3. Use IBKR investment topics and company themes for initial discovery pool
  4. Screen with S&P Global for ESG/sector fit and Canary Data for signals
  5. WebSearch analyst picks and sector trends (trusted domains)
  6. Apply corroboration filter: ≥2 sources per candidate
  7. Return 3–5 candidates, each with:
     - Thesis tied to user profile
     - Multi-source confidence rating (High / Medium / Single-source caution)
     - Cited sources with dates
     - "What to watch before buying" note

### `ibkr-buy-advisor`
- **Trigger:** "what should I buy with $X" / "I have $X to invest"
- **Complexity:** intermediate
- **MCP servers:** interactive-brokers, s-p-global, canary-data
- **Flow:**
  1. Load profile; abort with setup prompt if missing
  2. Ask: "How much do you want to deploy?"
  3. Fetch live positions and available cash from IBKR
  4. Identify allocation gaps vs. target
  5. Deep-research 2–3 best-fit candidates (S&P Global, Canary Data, WebSearch)
  6. Apply credibility filtering
  7. Return specific allocation:
     - "Put $X in [Stock A] and $Y in [Stock B]"
     - Reasoning per allocation, backed by cited sources
     - "What to monitor after buying" section

## Error Handling

| Scenario | Behavior |
|---|---|
| Profile missing | Stop immediately, tell user to run `ibkr-setup` first |
| MCP not authenticated | Prompt user to authenticate at session start; list which MCP needs auth |
| MCP returns no data | Note the gap explicitly in output; continue with remaining sources |
| Fewer than 2 corroborating sources | Flag claim as "single-source, treat with caution" — do not silently drop it |
| Contradictory sources | Surface the conflict; do not pick a side silently |

## Requirements

| Skill | Platform | MCP Servers | Type | Complexity |
|---|---|---|---|---|
| ibkr-setup | any | none | skill | simple |
| ibkr-portfolio-review | any | interactive-brokers, s-p-global, moodys, canary-data | skill | intermediate |
| ibkr-stock-finder | any | interactive-brokers, s-p-global, canary-data | skill | intermediate |
| ibkr-buy-advisor | any | interactive-brokers, s-p-global, canary-data | skill | intermediate |

## Verification

1. Run `ibkr-setup` → confirm `~/.claude/ibkr-profile.json` is created with correct values
2. Run `ibkr-portfolio-review` with IBKR connected → confirm report has cited sources with dates and flags stale data
3. Run `ibkr-stock-finder` → confirm ≤5 candidates returned, each with multi-source confidence rating
4. Run `ibkr-buy-advisor` with a dollar amount → confirm specific split recommendation with citations
5. Run any non-setup skill without a profile → confirm it stops and prompts to run setup
6. Run `npm run validate` → confirm all manifests pass schema validation
7. Run `npm run generate-registry` → confirm all 4 skills appear in registry.json
