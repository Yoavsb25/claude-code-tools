---
name: ibkr-setup
description: Set up your personal IBKR investment profile. Use this skill when the user says "set up my IBKR profile", "update my investment preferences", "configure my investor profile", "set my risk tolerance", or anything about saving their investing preferences for use with the other IBKR skills.
---

# IBKR Investment Profile Setup

You are setting up the user's long-term investment profile. Ask each question one at a time, wait for the answer, then move to the next. Save everything to `~/.claude/ibkr-profile.json` at the end.

---

## Step 1 — Risk tolerance

Ask:

> "What's your risk tolerance?
> - **Conservative** — preserve capital, accept lower returns, minimal volatility
> - **Moderate** — balanced growth and stability, some volatility acceptable
> - **Aggressive** — maximise growth, comfortable with significant volatility"

Accept: conservative / moderate / aggressive (or synonyms). Store as lowercase.

---

## Step 2 — Time horizon

Ask:

> "How many years are you investing for? (e.g. 5, 10, 20, or 'retirement in X years')"

Parse to a number of years. Store as integer.

---

## Step 3 — Sectors to focus on

Ask:

> "Which sectors do you want to prioritise? (e.g. technology, healthcare, consumer staples, energy, financials, industrials, real estate, utilities, materials, communication services)
> Type the ones you want, or 'none' for no preference."

Store as an array of lowercase strings. Empty array if "none".

---

## Step 4 — Sectors to avoid

Ask:

> "Are there any sectors you want to exclude entirely? (e.g. tobacco, gambling, defence, fossil fuels)
> Type the ones to avoid, or 'none'."

Store as an array of lowercase strings. Empty array if "none".

---

## Step 5 — Geographic preference

Ask:

> "What's your geographic focus?
> - **US-only** — US-listed stocks only
> - **Global** — international stocks and ADRs welcome
> - **Mixed** — primarily US but open to select international"

Store as: `us-only` / `global` / `mixed`.

---

## Step 6 — ESG preference

Ask:

> "Do you want to apply ESG (Environmental, Social, Governance) screening? ESG-screened recommendations will prioritise companies with strong sustainability ratings and exclude those with significant ESG controversies.
> Yes or no?"

Store as boolean (`true` / `false`).

---

## Step 7 — Target allocation

Ask:

> "What's your target portfolio allocation? Give me percentages for:
> - Stocks (equities)
> - Bonds (fixed income)
> - Cash
> They must add up to 100%."

Validate they sum to 100. If not, ask the user to correct them. Store as integers.

---

## Step 8 — Additional notes

Ask:

> "Any other preferences I should know? (e.g. 'avoid Chinese companies', 'prefer dividend payers', 'interested in small-caps') — or just say 'none'."

Store as a string. Empty string if "none".

---

## Step 9 — Save and confirm

Write the profile to `~/.claude/ibkr-profile.json`:

```json
{
  "risk_tolerance": "<conservative|moderate|aggressive>",
  "time_horizon_years": <integer>,
  "sectors_focus": ["<sector>", ...],
  "sectors_avoid": ["<sector>", ...],
  "geographic_preference": "<us-only|global|mixed>",
  "esg_preference": <true|false>,
  "target_allocation": {
    "stocks_pct": <integer>,
    "bonds_pct": <integer>,
    "cash_pct": <integer>
  },
  "notes": "<string>"
}
```

Use the Bash tool to write the file:

```bash
cat > ~/.claude/ibkr-profile.json << 'EOF'
{ ...the JSON... }
EOF
```

Then confirm to the user:

> "Profile saved. Here's what I've stored:
>
> | Setting | Value |
> |---|---|
> | Risk tolerance | [value] |
> | Time horizon | [N] years |
> | Sectors focus | [list or 'no preference'] |
> | Sectors avoid | [list or 'none'] |
> | Geography | [value] |
> | ESG screening | [yes/no] |
> | Target allocation | [X]% stocks / [Y]% bonds / [Z]% cash |
> | Notes | [value or 'none'] |
>
> Run `/ibkr-portfolio-review` to analyse your portfolio, `/ibkr-stock-finder` to discover new investments, or `/ibkr-buy-advisor` when you're ready to deploy cash."

---

## Edge cases

- **Allocation doesn't sum to 100**: Explain the constraint and ask the user to adjust before saving.
- **Unrecognised risk level**: Clarify and re-ask — don't guess.
- **File already exists**: Overwrite it — this is intentional (updating preferences).
