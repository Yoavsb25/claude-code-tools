# Search Fallbacks — ATS Auto-Detection, Workday, and JS-Rendered Career Pages

Conditional detail for Stage 2 of `job-search`'s SKILL.md. Only read this file when one of the
trigger conditions below actually applies — SKILL.md tells you when to branch here; this file
tells you what to do once you have.

## Checking a specific company (location-first method)

**When to run this:** whenever you're checking a specific `target_companies` entry or a
large-enterprise baseline company — as an alternative to `<company> + <one role title>` queries,
which are unreliable: they silently under-cover roles (checking only 1-2 of the profile's `roles`
titles per company misses the rest), and they miss postings entirely when the company uses a
different internal title for the same job family. Known synonyms worth trying before concluding a
company has nothing open in a given family:

| Job family | Common alternate titles |
|---|---|
| Solutions/pre-sales engineering | Google: "Customer Engineer" · Microsoft: "Cloud Solution Architect" / "Technical Specialist" · AWS: "Solutions Architect" |
| Customer-embedded software engineering | OpenAI, Anthropic, Palantir-style AI labs: "Forward Deployed Engineer" (a software-engineer/solutions-engineer hybrid — won't match a plain "Software Engineer" or "Solutions Engineer" query) |

**The method**, since the result set for one named company is naturally bounded (unlike an
open-ended market-wide search, where title-based querying is still necessary):
1. **Known ATS (`search ats`):** omit `--query` entirely and pull the full board (raise `--limit`
   as needed), then filter the results down to the profile's `locations` yourself.
2. **No known ATS / large enterprise:** run `search linkedin --query "<Company Name>"` (company
   name only, no role) `--location "<location>"`, which returns that company's actual open
   postings at that location across whatever titles they use.
3. **Either way, evaluate every remaining posting against the profile holistically** — title,
   scope, and description against `roles`/`skills`/`experience_summary` — rather than
   pre-filtering by whether the title matches one of the profile's role strings. A posting can be
   an excellent fit under a title nobody would have thought to search for.

This is slower per company than a single title query, but far more thorough — reserve it for named
`target_companies` and large-enterprise baseline checks, not the open market-wide search across all
of Stage 2a/2b, where there's no natural per-company boundary to exploit this way.

**A company not in `target_companies` can still be missed even with a great-fitting posting.**
Market-wide role searches (`search linkedin --query "<role>"` with no company) only return a
capped, relevance/recency-ranked slice (`--limit`) of what can be thousands of matching postings
citywide — there's no guarantee a specific company's specific posting surfaces in that slice, even
when it's an excellent fit. The only reliable way to guarantee a specific company gets checked is
to add it to `target_companies` (or run an ad hoc per-company check per the method above). If the
user asks about a specific posting that didn't come up, check whether its company was actually in
`target_companies` before diagnosing anything else — that's the most common reason, and the fix is
adding the company to the watchlist, not just tweaking query phrasing.

**Company-name-only queries are unreliable for short/common names.** Tested directly: a bare
`--query "Palo Alto Networks"` (distinctive, multi-word) correctly returned ~10 real postings from
that company. But bare queries for short or common single-word names — `"NVIDIA"`, `"Intel"`,
`"Dell"`, `"Microsoft"`, `"Salesforce"`, `"Amdocs"`, `"ServiceNow"` — returned unrelated noise with
zero actual postings from that company, even though some of these companies do have open London
roles (confirmed separately). Always check the `company` field of returned results actually
matches before concluding "nothing found" — if it doesn't, don't trust the negative result; fall
back to the direct career-page/Workday route (below) instead of reporting the company as having no
openings.

## ATS auto-detection

**When to run this:**
- A company in `target_companies` has no `platform`/`slug` set, or
- Stage 2b's proactive discovery surfaces a candidate company that isn't an obvious large
  enterprise (see SKILL.md's large-enterprise skip rule).

**Command:**
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-ats --company "<company name>" --query "<role keyword>"
```

**What it does:** probes slug guesses derived from the company name (concatenated/hyphenated
forms, with and without legal suffixes like "Inc"/"Ltd") against each supported ATS platform's
keyless JSON API — Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable, in that order —
and returns whichever combination actually resolves.

**Reading `confidence` in the response:**
- `"high"` — postings were actually found. Trust this.
- `"low"` — the endpoint responded without error but returned zero postings. Some platforms don't
  distinguish "unknown slug" from "real board, no current openings" — treat this as a guess, not a
  confirmed miss.
- `"none"` — nothing matched any platform/slug combination tried. Fall back to Stage 2b's direct
  career-page search for this company, targeting its real domain directly, not just LinkedIn.

**If `detected_platform` is non-null:**
1. Treat the returned postings as Stage 2a results (same dedupe priority as any other `search
   ats` call).
2. After presenting the shortlist, ask the user: `"Found <Company>'s job board on <platform>
   (<slug>, confidence: <level>) — want me to save that to your watchlist?"`
3. If yes: read the current `target_companies` from `profile show` (Stage 0's copy, or a fresh
   call if this is late in a long turn), add or update the entry by matching `name`
   case-insensitively, and write back the **full merged array** — `profile set` replaces
   `target_companies` wholesale (`profile.update(patch)` is a shallow merge), so never patch with
   just the new entry, or the rest of the watchlist is silently dropped:
   ```bash
   python3 ~/.claude/skills/job-search/scripts/job_tool.py profile set '{"target_companies": [ ...existing entries unchanged..., {"name": "<Company>", "platform": "<platform>", "slug": "<slug>"} ]}'
   ```

## Workday-hosted companies

**When this applies:** a WebSearch result surfaces a `myworkdayjobs.com` URL for a
target/discovered company. Don't try `search ats` for it — `job_tool.py`'s keyless ATS endpoints
don't cover Workday. This is the single most common outcome for large enterprises, so expect it
often.

**Three paths, in order:**

1. **`mcp__apify__*` tools available in this session** (check the deferred-tools list —
   independent of any environment variable). Preferred path:
   - Confirm the target company list with the user first, unless they already named the companies
     explicitly — this is a paid call regardless of which path runs it.
   - Call `mcp__apify__fetch-actor-details` on `automation-lab/workday-jobs-scraper` to confirm
     its input schema.
   - Call `mcp__apify__call-actor` with the company's `myworkdayjobs.com` URL, a role keyword, and
     location.
   - Default `maxJobs` to 10 (well under the Actor's own 20–50 default) rather than pulling
     everything.
   - Fetch results with a `fields` projection (`title,location,postedDate,url,compensation`
     first) before pulling full descriptions — only fetch full descriptions for the subset that
     survives that first pass. A large unprojected result set can overflow tool output entirely
     and get dumped to a file instead of returned inline, which defeats the point of a quick
     check.

2. **Else, `APIFY_TOKEN` configured for this install.** Run:
   ```bash
   python3 ~/.claude/skills/job-search/scripts/job_tool.py search workday --url <the myworkdayjobs.com URL> --query "<role keyword>" --location "<location>"
   ```
   - Same graceful-degradation contract as every other source (a bad URL or Actor hiccup degrades
     to `{"error": ..., "results": []}`, never blocks the rest of the run).
   - Same confirm-before-spend and lean-query discipline as path 1: confirm target companies with
     the user first unless already named.
   - Don't run this as a blanket re-check every round — reserve it for `target_companies`
     watchlist entries and the proactive-discovery hits already covered by the "~5
     newly-discovered companies per round" cap in SKILL.md's Stage 2b, the same restraint applied
     to the Playwright fallback below.

3. **Neither available, or the call errors.** Fall back to `WebFetch` on the public career-page
   listing directly — same optional-enrichment/graceful-degradation treatment as any other page in
   Stage 2b.

## JS-rendered career pages (Playwright fallback)

**When this applies:** `WebFetch` only reads raw HTML — it can't execute JavaScript, so many
custom/non-ATS career pages that render listings client-side come back as an empty shell (no job
titles, mostly boilerplate/nav text).

**What to do, if `mcp__playwright__browser_*` tools are available in the current environment:**
1. `browser_navigate` to the career-page URL.
2. `browser_snapshot` to read the rendered accessibility tree and extract the actual listings from
   it.

**Guardrails:**
- This is slower than `WebFetch` — only use it on pages that look genuinely JS-rendered (not just
  short), never as a first resort.
- Keep it within the same "cap ~5 newly-discovered companies per round" budget from Stage 2b's
  proactive discovery.
- If Playwright tools aren't configured in a given install (this MCP server isn't guaranteed to be
  present), skip this step entirely and fall back to the WebSearch snippet exactly as before —
  this is optional enrichment on top of optional enrichment, never a hard requirement.
