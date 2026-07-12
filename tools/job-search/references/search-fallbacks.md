# Search Fallbacks — ATS Auto-Detection, Workday, and JS-Rendered Career Pages

Conditional detail for Stage 2 of `job-search`'s SKILL.md. Only read this file when one of the
trigger conditions below actually applies — SKILL.md tells you when to branch here; this file
tells you what to do once you have.

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
