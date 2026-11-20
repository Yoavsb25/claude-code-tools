# Stage 3 — Scoring rubric

Read from SKILL.md Stage 3, after dedupe and the tracker cross-check.

For each remaining posting, score three dimensions:

**Role fit (0–10)** — How closely does the title, level, and JD body match the target role(s) and
seniority? Use exact-title matches and JD language (not just the title) — a "Senior Software
Engineer" posting that's really staff-scope work should score on scope, not label. **For any
LinkedIn-sourced candidate, pull its `seniority` field via `search linkedin-detail` before
scoring — don't infer seniority from the title alone.** LinkedIn's native search only returns
title/company/location (no description), so a title with no "Senior"/"Staff" qualifier can still
be a "Mid-Senior level"-tagged posting underneath; title-only inference has let postings like that
slip into shortlists for junior profiles in practice. This is a required check before scoring a
LinkedIn result, not optional enrichment — it directly feeds the "years of experience not met"
hard-check in Requirements fit below.

**A 2+-level seniority mismatch excludes a posting from the main shortlist outright — it is not
just a capped input to the weighted average.** This was found by actually running a search and
checking the results, not a hypothetical: capping Role fit alone to ≤3 for a badly-mismatched
posting *sounds* like a fix, but the math doesn't cooperate — a posting with strong Requirements
fit and Constraint fit can still average above 5 even with Role fit dragged down to 3 (verified
directly: Role fit 3 + Requirements fit 8 + Constraint fit 9 still computes to 6.55, comfortably
"above threshold"). A single capped input can't reliably force exclusion out of a weighted average
where it's only 35% of the total — so this needs to be a real exclusion, at the same severity tier
as a `deal_breakers` hit, not another score adjustment.

**The rule:** if a posting's real level (title *and* JD body/scope, not just the label) is two or
more steps away from the profile's `seniority` — a Senior or Staff posting against an "Entry to
Junior-Mid" profile, or an entry-level posting against a "Senior" profile — exclude it from the
main shortlist entirely, regardless of what the overall weighted score computes to. One step away
(e.g. "Mid" against "Entry to Junior-Mid") is a real deduction to Role fit, not an exclusion —
judge the likely day-to-day scope overlap normally in that case.

**This exclusion still routes through the worth-exploring exception, same as any other exclusion —
but the main table stays off-limits no matter what the math says.** A 2+-level-mismatched posting
from a named-company check (watchlist or large-enterprise baseline) isn't gone for good: score it
with Role fit capped at ≤3 for the write-up. If that capped computation lands under 3, it's fully
excluded, same as any other weak match. **Otherwise — including when strong Requirements/Constraint
fit pull the capped computation back above 5 (this happens: Role fit 3 + Requirements fit 7 +
Constraint fit 9 still averages to 6.2) — it goes to Worth Exploring, not the main table,
regardless of the number.** The exclusion is "never appears in the main table," full stop; the
capped score only decides *whether it appears at all* (≥3) and supplies the `Fit` number shown in
the Worth Exploring row, not whether it's good enough for the main list. A posting from the open
market-wide search still never gets this exception at all, for either table.

**Requirements fit (0–10)** — Overlap between the JD's required skills and the profile's `skills`,
`education`, and `experience_summary` (from `profile show` in Stage 0 — no external file to load).
Judge overlap holistically, including reasonable synonyms (e.g. "CI/CD" should match "continuous
integration," not just the literal string) — this stays a judgment call, not a keyword-matching
formula, since JD phrasing varies too much for rigid matching to be reliable. Hard-check any
explicit education requirement in the JD (minimum degree, a graduation-year window for grad/new-grad
postings) against `education`, and penalize postings with other hard requirements clearly unmet
(e.g. a specific clearance, a language not spoken, years of experience not met). If `skills`/
`education`/`experience_summary` aren't set yet, score with looser judgment from `roles`/
`seniority` alone and note the lower confidence rather than blocking the search on missing profile
data.

**Constraint fit (0–10)** — Location/remote match, industry alignment, and deal-breakers:
- A hit on `deal_breakers` drops this to 0 regardless of other scores — exclude the posting
  entirely, don't just rank it low.
- A location mismatch that isn't a formal deal-breaker (on-site/hybrid in a city outside all
  resolved `locations`, or no remote option when only remote locations are set) caps this at ≤3 —
  a role someone can't actually work is a near-exclusion even when the user never listed it as a
  deal-breaker.
- A hit on `industries_avoid` weights this down heavily (score ≤3) but doesn't auto-exclude,
  unless the user has said otherwise.
- A match with `industries_prefer` weights this up.
- A **disclosed** salary (stated on the posting or in fetched JD text — not the Stage 3 enrichment
  estimate below) that is clearly below `salary_floor` in the same currency drops this to 0
  regardless of other scores — exclude the posting entirely, same as a deal-breaker hit. Never
  exclude based on the *estimated* salary from the enrichment pass below — that stays
  annotation-only.

**Overall score** = (Role fit × 0.35) + (Requirements fit × 0.35) + (Constraint fit × 0.3).
Exclude anything scoring under 5 overall — don't pad the list with weak matches.

**Exception — adjacent roles at a specifically-checked company.** A posting that came from
checking a *named* company (any `target_companies` watchlist entry, or a large-enterprise baseline
check — i.e. anything from the "Checking a specific company" method in
`references/search-fallbacks.md`, not the open market-wide role search) and scores **between 3 and
5** goes to a separate "worth exploring" pool instead of being excluded outright. The idea: a
company the user specifically wants to work at is worth knowing about even when the *exact* role
isn't there, as long as it's not a pure stretch. Below 3, still exclude — that's too far off to be
worth listing even for a desired company (e.g. a Sales role surfacing during an Engineering
search). A posting from the open market-wide search (no specific company targeted) never qualifies
for this exception, regardless of score — a loosely-related role from a company nobody specifically
asked about is noise, not a lead.

**This exception never overrides a hard exclusion.** A `deal_breakers` hit, a role the user
genuinely can't work (location/remote mismatch per the Constraint fit rule above), or a *disclosed*
salary below `salary_floor` still excludes the posting completely — being at a desired company
doesn't make an unworkable role worth surfacing. Only apply the 3–5 exception when the *only*
reason a posting scored low is a weaker role/requirements match, not an unmet hard constraint.

For each posting landing in the worth-exploring pool, note *why* in one short phrase — what's
different from the target role, and what's still appealing (e.g. "Data Engineering, not backend,
but strong skills overlap and same seniority" or "one level senior for the profile, but a rare
opening at a company on the watchlist"). This becomes the `Why` column in Stage 4.

Sort descending by overall score. **Don't cap here** — Stage 4 applies the requested count (default
20) per category, after classifying each company as public or private. Capping the combined list
here first would let one category crowd out the other (e.g. 10 public + 0 private if public matches
happen to score higher this round).

**Salary enrichment for the near-final shortlist.** If `salary_floor` is set and a posting in the
top-scoring set doesn't disclose salary, get an estimate for each such posting — capped at the top
5–6 candidates, so this doesn't multiply cost across the whole list:

- **If the `salary-estimator` skill is available** (check the available-skills list first), invoke
  it with company/role/location/seniority. It does multi-source research (levels.fyi, Glassdoor,
  comparable postings, H-1B/LCA data, etc.) and returns a range with a confidence level.
- **If it isn't available** (not installed/enabled), fall back to one `WebSearch` per candidate for
  `"<company> <role> salary <location>"` — the same query pattern Stage 1's intake-time sanity
  check uses — to check public salary-aggregator data (Glassdoor, levels.fyi, Payscale-style
  results).

Either way, use the result only to annotate the posting with the estimated range (and confidence,
if the skill provided one), and flag it if the low end looks below the floor. Never exclude a
posting based on estimated data alone, and mark it clearly as `"salary: ~£X–Y estimated (Medium
confidence), unconfirmed"` (fallback WebSearch estimates without a formal confidence level can just
say `"unconfirmed"`) in the output — it's a data point to verify during application, not a scored
fact. This is now the only flag-only salary path: a *disclosed* salary below the floor is handled
by the Constraint fit rule above and excludes the posting outright, so the two paragraphs aren't in
tension — one covers confirmed data, the other covers guesses.
