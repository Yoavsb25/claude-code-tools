# R&D department-based filtering — design spec

Date: 2026-09-22
Status: approved by Yoav (design sections), verified live, pending final spec review

## Problem

`rnd-catalogue`'s Catalogue mode filters postings by matching each title against a hardcoded
keyword list (`references/rnd-titles.md`). Dogfooding the skill against the real watchlist
exposed two compounding problems:

1. **Title-matching requires knowing titles in advance.** Yoav wants to explore broadly —
   "what does this company have open in R&D" — not maintain an exhaustive title vocabulary.
   Real compound titles (`"Software Performance Engineer"`, `"Senior HPC AI Cluster Engineer"`)
   routinely miss a rigid keyword list even when a human would immediately recognize them as
   engineering roles.
2. **Workday's own scan/location mechanics were silently hiding most real postings**, independent
   of the title problem. Investigated live:
   - **NVIDIA**: catalogue run found 0 UK R&D postings. Filtering NVIDIA's own site directly by
     location found **54** UK postings, of which a human judge would call **20** genuine R&D —
     the existing `--location-hint` fuzzy-text match (`"united kingdom" in locationsText`) never
     matches Workday's actual site labels (`"UK, Cambridge"`, `"UK, Remote"`), so the 150-posting
     detail-fetch budget was being spent almost entirely on non-UK postings.
   - **Intel**: confirmed genuine zero — no UK/London option exists in Intel's own location facet
     at all for this board. Not a bug.
   - **Adobe**: 18 UK postings total, but only 2 are R&D (both Product Manager) — Adobe's London
     office is Sales/Legal/Strategy-heavy. Confirms the gap isn't uniform; it's real per company.

## Investigation: how department data actually looks per source

Audited `job_tool.py`'s `parse_ats_payload` (the six ATS platforms) plus `fetch_comeet_postings`
directly against source:

| Source | Department captured into `tags` today? |
|---|---|
| Greenhouse | ✅ `departments[].name` |
| Ashby | ✅ `departmentName` |
| SmartRecruiters | ✅ `department.label` |
| Recruitee | ✅ `department.name` |
| Workable | ✅ `department` |
| Comeet | ✅ `department` |
| **Lever** | ❌ Bug — captures `categories.allLocations` (a location list) into `tags` instead of `categories.team` (the actual department field, already present in the same payload) |
| **Workday** | ❌ Gap — `tags` is always `[]`. Investigated live (see below): the per-posting **detail** JSON (`jobPostingInfo`, fetched via `{api_base}{externalPath}`) has no category field at all — location, title, description, dates only. Category exists **only** as a facet-level construct. |

**Live-verified Workday mechanism** (`POST {api_base}/jobs` with `appliedFacets: {}`):
- The response's `facets` array includes an entry with `facetParameter: "jobFamilyGroup"`,
  `descriptor: "Job Category"`, and a list of `{descriptor, id, count}` values (e.g. `Engineering`
  → `0c40f6bd1d8f10ae43ffaefd46dc7e78`, count 1756; `Research` → count 39; `Sales` → count 330).
  These IDs are per-tenant opaque strings, discovered the same way `locationHierarchy1` IDs
  already are for the existing `--location-hint`-adjacent UI flow.
- Individual postings in the compact list carry **no category field** — a posting's category can
  only be learned by querying **with** the facet applied, not by inspecting an unfiltered result.
- Applying `appliedFacets: {jobFamilyGroup: [<id>], locationHierarchy1: [<id>]}` together in one
  request returns **exactly** the category-and-location-filtered set, server-side — verified live:
  querying NVIDIA's `Engineering` + `United Kingdom` returned 16 postings matching almost exactly
  the 20 a human judge picked by reading all 54 UK titles (the 4-posting gap was `Solutions
  Architect`/pre-sales-flavored roles NVIDIA itself buckets outside `Engineering` — i.e. Workday's
  own categorization is **more accurate** than manual title judgment for exactly the case
  `rnd-titles.md`'s "Solutions Architect" exclusion rule exists to handle).

This finding **replaces** the "capture category during the existing detail fetch" idea from the
original design discussion (verbally approved before this verification pass) — that data doesn't
exist per-posting. The real, verified fix is server-side facet application, which also
subsumes and fixes the separate `--location-hint` fuzzy-matching bug in the same mechanism.

## Decisions

| Question | Decision |
|---|---|
| Title vs. department as primary filter | Department primary; `rnd-titles.md` stays only as a fallback for postings with missing/unusable department data (empty tags, or a generic bucket like `"Other"`) |
| Workday scope | Fix properly now (not deferred) — job_tool.py gains real Workday category support, not just rnd-catalogue-side workarounds |
| Workday location matching | Upgraded in the same change, from fuzzy text-substring to the same exact facet-ID mechanism as category (same underlying bug class, same fix) |

## Architecture

Two repos, same as the earlier fixes in this thread: `job-search`'s `job_tool.py` (mechanism) and
`rnd-catalogue`'s `SKILL.md`/references (policy — which department names count as R&D).

### job_tool.py changes

**1. Lever fix (one line).** `parse_ats_payload`'s Lever branch: change the `tags` field from
`(j.get("categories") or {}).get("allLocations") or []` to
`[(j.get("categories") or {}).get("team")] if (j.get("categories") or {}).get("team") else []`.
No new request — `categories.team` is already present in the existing payload.

**2. Workday: new facet-based filtering.** `search workday-jobs` and `search discover-workday`
gain two new optional flags:
- `--job-family-groups "Engineering,Research,Product Management,..."` (comma-separated category
  **names**, matched case-insensitively against each tenant's actual facet descriptors) — resolved
  to that tenant's `jobFamilyGroup` facet IDs via one extra lightweight `POST /jobs` call with
  `appliedFacets: {}` and `limit: 0` (facets are returned regardless of `limit`), then applied as
  `appliedFacets: {jobFamilyGroup: [...ids]}` on the real query. A name with no matching facet for
  that tenant is silently skipped (same graceful-degradation contract as everything else in this
  script) — not an error.
- `--location-hint` is **reimplemented** on the same mechanism: resolve the given location string
  against that tenant's `locationHierarchy1` facet descriptors (exact match, case-insensitive) to
  get its ID, then apply `appliedFacets: {locationHierarchy1: [id]}` on the real query, replacing
  the current `hint in locationsText.lower()` substring check entirely. If no facet matches (e.g.
  a typo, or a country the tenant has zero postings in), fall back to today's behavior (pagination
  budget shared with detail-fetch, no location bias) rather than erroring.

Combining both narrows the query **server-side** before any detail-fetch happens — for a company
the size of NVIDIA (2000 postings company-wide), a category+location-filtered query returns a
handful to a few dozen results, not 2000, so `WORKDAY_MAX_JOBS_SCANNED` (150) stops being a
practical constraint for a targeted rnd-catalogue-style query. The existing per-posting detail
fetch (for full location text and description) still runs on this now-much-smaller result set —
unchanged.

`job_tool.py` stays taxonomy-agnostic: it accepts category **names** as strings and resolves them
per-tenant; it has no opinion on which categories mean "R&D" — that's `rnd-catalogue`'s policy,
supplied by the caller.

### rnd-catalogue changes

**New reference file**, `references/rnd-departments.md` — same three-part shape as
`rnd-titles.md`:
- **Include**: `Engineering`, `R&D`, `Research`, `Research & Development`, `Product`, `Product
  Management`, `Data`, `Data Science`, `Data & Analytics`, `AI`, `AI/ML`, `Machine Learning`,
  `Software Engineering`, `Hardware Engineering`.
- **Exclude**: `Sales`, `GTM`, `Marketing`, `Business Development`, `Customer Success`,
  `Delivery`, `Services`, `Professional Services`, `Finance`, `Legal`, `Human Resources`,
  `People`, `Facilities`, `Administration`, `Corporate Strategy`.
- **Ambiguous** (judge from context/JD, don't auto-include or auto-exclude): `Security` (Cyber/
  InfoSec engineering is R&D; Corporate/Physical Security isn't — a bucket named bare `"Security"`
  needs a look), `Operations` (Engineering Ops/DevOps-adjacent buckets are R&D; general business
  Operations isn't), `IT - Information Technology` (internal IT support usually isn't R&D; some
  companies fold platform engineering into it), `Program Manager` (same caveat `rnd-titles.md`
  already documents for the title case — only R&D-scoped if the JD says so).

**SKILL.md Stage 1** (fetch): for Workday-platform companies, pass `--job-family-groups` built
from `rnd-departments.md`'s Include list, and keep passing `--location-hint` (now exact-matched).
For all other platforms, fetch as today (they already return the full board with a usable
`tags`/department field per posting).

**SKILL.md Stage 2** (filter): for every posting, if `tags` has a non-generic value, match it
against `rnd-departments.md` and stop — title is never consulted for these. Only when `tags` is
empty or a known-generic bucket (`"Other"`, or a company-specific label that means nothing on its
own) does the posting fall through to today's `rnd-titles.md` title-matching as a fallback. For
Workday specifically, since the fetch is already category-filtered server-side, every returned
posting is *by construction* already in an Include department — Stage 2 doesn't need to re-check
it, only the location judgment still applies (multi-location postings where UK is one of several
eligible sites, same as today).

## Testing

`test_job_tool.py`: new cases for the Lever fix (`categories.team` → `tags`) and for the Workday
facet-resolution helper (name → ID lookup, case-insensitivity, graceful skip on no match, combined
category+location `appliedFacets` construction) — these can be tested with a mocked facets
response, no live network needed, same pattern as the rest of the suite.

`rnd-catalogue`'s own test suite (`test_catalogue_store.py`) is unaffected — this change is all
upstream of `catalogue_store.py`, which only ever sees the already-filtered, already-normalized
posting array.

## Explicitly out of scope

- Re-auditing the other 6 ATS platforms' department accuracy beyond confirming the field mapping
  (Greenhouse/Ashby/SmartRecruiters/Recruitee/Workable/Comeet) — they already return real
  per-posting department data; no further verification needed before relying on it.
- Applying the same facet-discovery pattern to `search workday` (the older, paid-Apify-fallback
  command) — only `workday-jobs`/`discover-workday` are in scope, since those are what
  `rnd-catalogue` actually calls.
- Re-running the full 50-company watchlist through the new mechanism as part of this spec — that's
  a follow-up action once the implementation lands, not part of the design/build work itself.

## Environment note

Implemented in an isolated worktree (`feature/rnd-department-filtering`, branched off a clean
`origin/main` that already includes the merged `rnd-catalogue` skill (#6) and the Ashby
dotted-slug fix (#7)) — same pattern as the prior fixes in this session, to keep this reviewable
independently.
