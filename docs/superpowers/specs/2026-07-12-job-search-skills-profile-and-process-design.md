# Job Search — Structured Skills Profile & Process Hardening — Design Spec
**Date:** 2026-07-12
**Status:** Approved

## Context

A live job-search session surfaced two kinds of problems:

1. **Skills/experience/education aren't really used.** The only skills-matching input is a hardcoded read of `~/Desktop/Work/SysAid/profile-summaries/overall-profile.md` — a narrative work-history file for one specific employer, tied to one machine. It's only consulted for post-search scoring (Stage 3), never to shape what gets searched in the first place. Education isn't captured anywhere.
2. **A handful of process gaps caused wasted or missed work in the same session**: an ambiguous role title ("Automation Engineer") burned a full search round before the mismatch was caught; a salary floor incompatible with the stated seniority wasn't flagged until after several enrichment calls; large-enterprise career pages were only checked because the user asked; a directly-configured Apify MCP server wasn't considered as an alternative to the `APIFY_TOKEN`-gated path; a paid Workday scrape returned a payload large enough to overflow tool output; and cross-round deduplication only checks the persisted tracker, not postings already shown earlier in the same conversation.

This spec covers both: making the skill actually profile-aware, and hardening the process gaps found along the way.

## Goals

- Replace the hardcoded, single-machine SysAid file dependency with a portable, structured profile that `job_tool.py` already supports (schema-less `profile set`/`profile show`).
- Let skills/education inform *which* searches get run (Stage 2), not just how results get scored after the fact (Stage 3).
- Catch two classes of intake-time mistakes before they cost search calls: unresolved ambiguous role titles, and a salary floor that's inconsistent with stated seniority.
- Make the Workday/Apify path resilient to either configuration (MCP server or `APIFY_TOKEN`), cheaper by default, explicit about cost, and immune to the aggregator-noise and payload-overflow issues seen this session.
- Extend Stage 3 dedupe to cover postings already shown earlier in the same conversation, not just the persisted tracker.

## Non-Goals

- No change to `job_tool.py` — every change here is achievable through existing schema-less `profile set` plus updated SKILL.md instructions. No new subcommands, no new script logic.
- No rigid, formula-driven scoring engine. Requirements-fit stays a holistic judgment call anchored to structured data, not a keyword-matching point system — JD phrasing varies too much for that to be reliable.
- Persisting this session's already-found roles to the tracker is out of scope for this spec — it's a one-off follow-up action, not a skill behavior change.
- No hardcoded market-salary tables. The salary/seniority sanity check uses a live search, not a static lookup that would go stale.

## Data Model Changes

Three new optional fields in `profile.json`, set via the existing `profile set` (a plain shallow merge — `profile.update(patch)` — so no script changes are needed):

```json
{
  "skills": ["JavaScript", "TypeScript", "React", "Node.js", "CI/CD", "GitHub Actions", "ArgoCD", "Kubernetes", "Python"],
  "education": [
    {"degree": "BSc", "field": "Computer Science", "institution": "...", "graduation_year": 2024}
  ],
  "experience_summary": "2 years as a Software Engineer, focused on CI/CD infrastructure, deployment automation, and internal developer tools using React/Node."
}
```

- `skills`: flat list of strings — the vocabulary used for both search-steering (Stage 2) and requirements-fit scoring (Stage 3).
- `education`: a list (not a single object) to support multiple degrees. Used to hard-check JD education requirements (minimum degree, graduation-year windows for grad schemes).
- `experience_summary`: short free text — the portable replacement for the SysAid narrative file. One paragraph, not a structured job history — enough for holistic judgment, not meant to be exhaustive.

The hardcoded `~/Desktop/Work/SysAid/profile-summaries/overall-profile.md` reference is removed from both the Role Discovery step and the Requirements-fit scoring step in SKILL.md, replaced by reading these three fields directly from the profile. This removes the skill's only remaining dependency on a path specific to one person's machine, making it self-contained for anyone installing it from the registry.

## Stage 1 — Intake Changes

**New fields.** `skills`, `education`, and `experience_summary` are asked for alongside the existing intake fields (roles, locations, seniority, etc.) on first run. Existing profiles that predate this change get a one-time backfill prompt the next time the skill runs, then are never asked again.

**Ambiguous role titles — resolved at intake, not mid-search.** The skill already instructs asking a clarifying question "if context doesn't resolve" an ambiguous title (e.g. Automation Engineer, Analyst) — but this session showed the failure mode: adjacency in the `roles` list (e.g. "Automation Engineer" sitting next to "Software Engineer") was treated as sufficient context when it wasn't; the mismatch (industrial/controls automation, not software test automation) was only caught after a full LinkedIn search round. Tightened rule: **adjacency to another role in the list no longer counts as resolving the ambiguity by itself.** For any title on the known-ambiguous list, resolution requires an explicit qualifying word already present in the stored role string itself (e.g. "Software Automation Engineer," "QA Automation Engineer," "Test Automation Engineer"). Otherwise, ask the one-line clarifying question during Stage 1 intake — before Stage 2 runs any search for that role.

**Salary floor vs. seniority sanity check.** New step: whenever `salary_floor` and `seniority` are both set (on profile creation or edit) and `seniority` reads as junior/entry-level, run one quick WebSearch for typical market salary at that role/seniority/location combination *before* running the full multi-source search. If the floor looks materially above market, flag it to the user up front — e.g. "Your £60k floor is well above typical London junior rates (~£35–49k) — want to adjust, or proceed knowing most matches may fall short?" — rather than discovering the mismatch only after several rounds of per-posting salary enrichment in Stage 3, which is what happened this session. This is a single check at intake time, distinct from and in addition to the existing per-posting Stage 3 salary enrichment for the near-final shortlist.

## Stage 2 — Search Changes

**Skill-flavored query (search-steering).** Alongside the existing per-role WebSearch queries in Stage 2b, add exactly **one** additional query per role that blends the role title with the top 2–3 `skills` (e.g. `"Software Engineer React Node CI/CD hiring London"`). This is additive, not a replacement for the existing broad per-role queries. Bounded to one extra query per role — not one per skill — to keep search volume from multiplying.

**Preferring individual postings over aggregator pages.** This session's WebSearch queries frequently returned aggregator/listicle landing pages (Glassdoor "147 jobs in..." pages, Totaljobs category pages) instead of individual postings — low signal for the tokens spent. Query-phrasing guidance is tightened: the per-role queries (both the existing plain-title query and the new skill-flavored query) should prefer patterns that resolve to individual posting pages — `site:linkedin.com/jobs/view/`, `site:boards.greenhouse.io`, `site:jobs.lever.co`, or a company's own `/careers/` or `/job/` URL pattern — over generic phrasing like "who is hiring X" or "best companies for X 2026," which reliably surface aggregator pages instead. The broader, intentionally-generic "proactive company discovery" queries (used to surface *candidate company names*, not scoreable postings) are unaffected — that's a different purpose and aggregator noise there is expected and fine, since only company names are extracted from those hits.

**Large-enterprise baseline check.** Stage 2b already instructs checking large, well-known enterprises via their direct career pages rather than probing ATS platforms — but this session showed that step only actually ran because the user explicitly asked for it; the proactive-discovery WebSearch queries didn't reliably surface big-company names on their own. New baseline: when the profile has no large enterprises in `target_companies` and none have surfaced via proactive discovery, the skill still checks a small number (3–5, same budget as the existing proactive-discovery cap) of well-known large employers relevant to the resolved role/industry as a guaranteed part of every search round — not contingent on WebSearch phrasing luck. This is a default baseline, not a replacement for user-specified `target_companies`, which always take priority.

## Stage 3 — Scoring & Dedupe Changes

**Requirements-fit scoring**, now anchored to the structured profile fields instead of an external file: judge overlap between the JD and `skills` (including reasonable synonyms — "CI/CD" should match "continuous integration," not just the literal string), and hard-check any explicit education requirement in the JD (minimum degree, graduation-year window for grad/new-grad postings) against `education`. This stays a holistic 0–10 judgment call, not a computed formula — JD language varies too much for rigid keyword matching to be reliable on its own.

**Cross-round dedupe.** The existing dedupe step checks new results against the persisted tracker (`tracker list` from Stage 0). It's extended to also check against any postings already shown earlier in the *same conversation* — so a follow-up request ("check big companies too," "check these via Workday") doesn't risk re-presenting something already surfaced in an earlier round of the same session, even before anything's been saved to the tracker.

## Workday / Apify Process Changes

**Apify MCP as a first-class path.** The "Workday-hosted companies" section currently only documents `job_tool.py search workday`, gated on the `APIFY_TOKEN` environment variable. It's updated to check first whether `mcp__apify__*` tools are already available in the current session (as they were this session, independent of any env var) and, if so, prefer calling the Workday scraper Actor directly via `mcp__apify__call-actor` (using `fetch-actor-details` first to confirm the input schema, same as any other Actor call). The `APIFY_TOKEN`-gated `job_tool.py search workday` path remains the fallback when the MCP server isn't configured. Both paths are optional and degrade the same way — no Workday coverage isn't a failure, just a gap noted in the Stage 4 summary.

**Confirm before spending.** Before running any paid Actor through either path, the skill now explicitly requires confirming the target company list with the user first — unless the user already named the companies explicitly — mirroring what happened organically this session (an `AskUserQuestion` before the first Workday run). This was previously just good judgment applied in the moment; it's now a documented requirement, since it's real money regardless of which path (MCP or `search workday`) is used.

**Lean dataset queries.** Default `maxJobs` for any Workday scrape (either path) drops to 10, rather than the Actor's own default of 20–50 — matching what worked well this session. Results are fetched with a `fields` projection (title, location, postedDate, url first) before pulling full descriptions for the promising subset, avoiding the payload-truncation issue that hit this session's Salesforce run (10 items, 104K characters, dumped to an on-disk file that was never actually read back). If full descriptions are needed for scoring, they're fetched selectively for the subset that survives an initial title/location/date pass, not for every raw result.

## Rollout / Migration

All changes are documentation-only (`SKILL.md` prose), since `job_tool.py`'s `profile set`/`profile show` already handle arbitrary schema-less JSON. No script changes, no migration script needed — existing `profile.json` files simply gain new keys the next time the skill runs and prompts for backfill. Nothing breaks for profiles that never get the new fields filled in; the skill just falls back to holistic judgment without the structured anchors, same as today.

## Testing / Validation

Since this is a prose-only change to an agent-executed skill (no code path to unit test), validation is a manual dry run after editing:
1. Fresh profile creation — confirm intake asks for `skills`/`education`/`experience_summary` alongside existing fields, and that an ambiguous title (e.g. "Automation Engineer" with no qualifier) triggers the one-line clarifying question before any search runs.
2. Existing profile (missing new fields) — confirm the one-time backfill prompt fires once and doesn't re-ask on subsequent runs.
3. A profile with `salary_floor` + junior `seniority` — confirm the market-rate sanity check runs and surfaces a flag before the full search executes.
4. A search round that finds a Workday-hosted company — confirm the skill checks for `mcp__apify__*` tool availability before falling back to the `APIFY_TOKEN` path, confirms target companies before spending, and requests a bounded `maxJobs` with field projection.
5. A second search round in the same conversation — confirm postings from the first round aren't re-presented.
