# job-search — Stage 2 Rule-Interaction Eval Scenarios

Companion to the 2026-07-12 skill-reviewer audit of `tools/job-search/`. Static review confirmed
Stage 2's individual rules are each well-specified, but flagged that their sheer number and
interactions (large-enterprise ATS-skip × `discover-ats` × Workday routing × the
proactive-discovery budget cap) can't be verified by reading alone. Run these three scenarios
against a fresh Claude instance with `job-search` installed — either manually, or via
`skill-creator`'s benchmarking flow — and grade the transcript against each scenario's checklist.

## Scenario 1 — Large-enterprise skip vs. `discover-ats` vs. Workday routing

**Setup:** A profile with `roles: ["Staff Backend Engineer"]`, `locations: ["Remote EU"]`, and
`target_companies` containing three entries with no `platform`/`slug` set: `"Microsoft"`,
`"Anthropic"`, `"Acme Corp"` (a fictional small company).

**Turn:** "Find me some jobs."

**Checklist — the transcript must show:**
- [ ] `Microsoft` is **not** probed via `search discover-ats` or `search ats` — SKILL.md's
  large-enterprise skip rule ("Large enterprises go straight to Stage 2b") routes it straight to
  Stage 2b's direct career-page search.
- [ ] `Anthropic` and `Acme Corp` **are** probed via `search discover-ats` first, since neither is
  an obvious large enterprise and neither has a `platform`/`slug` set.
- [ ] If `search discover-ats` for either returns `confidence: "none"`, the transcript falls back
  to Stage 2b's direct career-page search for that company — it does not report "nothing found"
  based on the `discover-ats` miss alone.
- [ ] If a `myworkdayjobs.com` URL surfaces for Microsoft during the Stage 2b career-page search,
  the transcript follows the three-path order from `references/search-fallbacks.md` § "Workday-hosted
  companies" (Apify MCP → `APIFY_TOKEN` → `WebFetch`) and does **not** attempt `search ats` on it.

## Scenario 2 — `discover-ats` low confidence is a guess, not a confirmed miss

**Setup:** Same profile as Scenario 1, but mock/observe a `search discover-ats` call for
`"Acme Corp"` that returns `confidence: "low"` (a platform resolved with zero postings).

**Turn:** "Any luck with Acme Corp?"

**Checklist — the transcript must show:**
- [ ] The low-confidence result is **not** reported to the user as "Acme Corp has no open roles."
- [ ] The transcript notes the result is a guess and either runs the Stage 2b direct career-page
  search for Acme Corp's real domain, or explicitly asks the user for Acme Corp's careers URL.

## Scenario 3 — Proactive-discovery cap is not double-counted against the large-enterprise baseline

**Setup:** A profile with `roles: ["Staff Backend Engineer"]`, `industries_prefer: ["fintech"]`,
and an **empty** `target_companies` list (no large enterprises named yet, none surfaced yet this
session).

**Turn:** "Find me some jobs" (first turn in a fresh conversation).

**Checklist — the transcript must show:**
- [ ] Proactive-discovery `WebSearch` queries run (e.g. `"who is hiring" Staff Backend Engineer
  fintech 2026`) and surface up to ~5 newly-discovered companies.
- [ ] **Separately**, 3–5 well-known large employers relevant to the role/industry are checked via
  Stage 2b's direct career-page search as the large-enterprise baseline — this set is additional
  to, not carved out of, the ~5-company proactive-discovery cap. The transcript should show more
  than 5 total newly-checked companies this round (proactive-discovery's ~5 plus the baseline's
  3–5), not exactly 5.
- [ ] Both the proactive-discovery hits and the baseline-check hits are described in the Stage 4
  summary as separate categories of "how we found this," not merged into one undifferentiated list.

## Recording results

For each scenario, note pass/fail per checklist item and paste the specific transcript excerpt
that confirms or contradicts it. Any unchecked item is a real defect in `SKILL.md`'s Stage 2 —
file it the same way the original audit findings were filed, with the specific rule text that
needs tightening.
