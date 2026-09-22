# R&D Department-Based Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `rnd-catalogue`'s title-keyword filtering with department/category-based filtering, fixing a real Lever data-mapping bug and adding server-side Workday category+location filtering along the way.

**Architecture:** Two-repo change. `job_tool.py` (job-search) gains: a one-line Lever fix, and real Workday `jobFamilyGroup`/`locationHierarchy1` facet support (replacing a fuzzy, broken text-match). `rnd-catalogue` gains a new department taxonomy reference and a Stage 1/2 rewrite that filters by department primarily, falling back to the existing title taxonomy only when department data is unusable.

**Tech Stack:** Python 3 stdlib only, `unittest` (no `pytest` in this environment), Markdown for skill files.

**Spec:** `docs/superpowers/specs/2026-09-22-rnd-department-filtering-design.md`

## Global Constraints

- No new third-party dependencies — `job_tool.py` and `catalogue_store.py` stay stdlib-only.
- `job_tool.py` stays taxonomy-agnostic: it accepts category/location **names** as plain strings and resolves them per-tenant; it has no opinion on which categories mean "R&D" — that policy lives only in `rnd-catalogue`'s `references/rnd-departments.md`.
- A category or location name with no matching facet for a given tenant is silently skipped, never an error — same graceful-degradation contract as every other `job_tool.py search` source.
- The existing `fetch_workday_postings` docstring's core claim — that a posting's location must come from a per-posting *detail* fetch, not the compact list — is unaffected by this change and must not be removed; only the location/category *filtering* mechanism changes.
- Run tests with `python3 -m unittest` from each script's own `scripts/` directory.

---

## File Structure

```
tools/job-search/scripts/
  job_tool.py            # Modify: Lever fix, new facet helpers, fetch_workday_postings rewrite, CLI wiring
  test_job_tool.py        # Modify: new/updated tests

tools/rnd-catalogue/
  references/
    rnd-departments.md   # Create: department include/exclude/ambiguous taxonomy
  SKILL.md                # Modify: Catalogue mode Stage 1 (fetch) and Stage 2 (filter)
```

This plan does not touch `tools/rnd-catalogue/scripts/catalogue_store.py` — it only ever sees the already-filtered, already-normalized posting array, and its contract doesn't change.

---

### Task 1: Lever department-field fix

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (`parse_ats_payload`'s `lever` branch)
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `parse_ats_payload("lever", company, data)` now returns each posting's `tags` as `[categories.team]` (or `[]` if absent) instead of `categories.allLocations`. No other task depends on this directly, but Task 6's SKILL.md text describes Lever as an already-working department source — this task is what makes that true.

- [ ] **Step 1: Fix the existing test's now-wrong assertion, and write two new failing tests**

`class TestParseAtsPayload` in `tools/job-search/scripts/test_job_tool.py` already has a
`test_lever` method (around line 585) that currently asserts the **old, buggy** behavior:

```python
    def test_lever(self):
        data = [{
            "text": "Platform Engineer", "categories": {"location": "Berlin", "allLocations": ["Berlin"]},
            "hostedUrl": "https://jobs.lever.co/acme/1", "createdAt": "2026-06-01",
            "descriptionPlain": "JD text",
        }]
        out = job_tool.parse_ats_payload("lever", "Acme", data)
        self.assertEqual(out[0]["title"], "Platform Engineer")
        self.assertEqual(out[0]["location"], "Berlin")
        self.assertEqual(out[0]["tags"], ["Berlin"])
```

Its fixture has no `team` field, so after Step 3's fix `tags` becomes `[]`, not `["Berlin"]` —
update its last line:

```python
        self.assertEqual(out[0]["tags"], [])
```

Then add two new test methods to the same class (these are the ones this task's fix is really
about — the updated `test_lever` above only stops it from going stale, it doesn't exercise the
new behavior):

```python
    def test_lever_captures_team_as_department_tag_not_locations(self):
        data = [{
            "text": "Senior Backend Engineer",
            "categories": {
                "location": "London",
                "allLocations": ["London", "Remote UK"],
                "team": "Engineering",
            },
            "hostedUrl": "https://jobs.lever.co/spotify/abc123",
            "createdAt": 1700000000000,
            "descriptionPlain": "...",
        }]
        results = job_tool.parse_ats_payload("lever", "spotify", data)
        self.assertEqual(results[0]["tags"], ["Engineering"])
        self.assertEqual(results[0]["location"], "London")  # unaffected by this fix

    def test_lever_missing_team_gives_empty_tags(self):
        data = [{
            "text": "Something",
            "categories": {"location": "London", "allLocations": ["London"]},
            "hostedUrl": "https://jobs.lever.co/spotify/def456",
            "createdAt": 1700000000000,
        }]
        results = job_tool.parse_ats_payload("lever", "spotify", data)
        self.assertEqual(results[0]["tags"], [])
```

- [ ] **Step 2: Run to verify the fails are the expected ones**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestParseAtsPayload -v`
Expected: **two** failures — the updated `test_lever` (still-unfixed code produces `["Berlin"]`,
not the now-expected `[]`) and `test_lever_captures_team_as_department_tag_not_locations`
(produces `["London", "Remote UK"]`, not `["Engineering"]`).
`test_lever_missing_team_gives_empty_tags` passes already (both old and new code give `[]` when
there's no `allLocations`/`team` — coincidental, not a signal to skip Step 3).

- [ ] **Step 3: Fix the mapping**

In `job_tool.py`, find `parse_ats_payload`'s Lever branch:

```python
    if platform == "lever":
        return [
            posting(
                "lever", j.get("text"), company, (j.get("categories") or {}).get("location"),
                None, j.get("hostedUrl"), (j.get("categories") or {}).get("allLocations") or [],
                None, j.get("createdAt"), j.get("descriptionPlain") or j.get("description"),
            )
            for j in data
        ]
```

Replace the `tags` argument (the 7th positional argument to `posting(...)`, currently
`(j.get("categories") or {}).get("allLocations") or []`) with:

```python
                [(j.get("categories") or {}).get("team")] if (j.get("categories") or {}).get("team") else [],
```

So the full branch becomes:

```python
    if platform == "lever":
        return [
            posting(
                "lever", j.get("text"), company, (j.get("categories") or {}).get("location"),
                None, j.get("hostedUrl"),
                [(j.get("categories") or {}).get("team")] if (j.get("categories") or {}).get("team") else [],
                None, j.get("createdAt"), j.get("descriptionPlain") or j.get("description"),
            )
            for j in data
        ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestParseAtsPayload -v`
Expected: PASS (the updated `test_lever`, both new tests, plus every other pre-existing test in
that class still green — only the Lever branch was touched).

- [ ] **Step 5: Run the full suite**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v 2>&1 | tail -5`
Expected: all tests pass (baseline was 65 before this task; should be 67 after Steps 1-4 add 2).

- [ ] **Step 6: Commit**

```bash
cd tools/job-search/scripts
git add job_tool.py test_job_tool.py
git commit -m "job-search: fix Lever postings to capture department (categories.team), not locations

parse_ats_payload's Lever branch mapped categories.allLocations into tags --
a copy-paste artifact, since location already captures categories.location.
The real department field, categories.team, was already present in the same
payload and simply never read. Lever now joins Greenhouse/Ashby/SmartRecruiters/
Recruitee/Workable/Comeet as a source with real per-posting department data.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Workday facet-resolution helpers

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (three new functions, placed near `fetch_workday_postings`)
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: nothing new (uses the existing `http_post_json` helper already in the file).
- Produces (used by Task 3):
  - `fetch_workday_facets(api_base) -> (facets, error)` — one lightweight request; `facets` is the raw list from the response's `"facets"` key (or `None` on error).
  - `find_facet_values(facets, facet_parameter) -> list[dict]` — each dict shaped `{"descriptor": str, "id": str, "count": int}`; `[]` if `facet_parameter` isn't found anywhere in the tree (including nested groups).
  - `resolve_facet_ids(values, names) -> list[str]` — `values` is a `find_facet_values(...)`-shaped list; `names` is an iterable of strings; returns the matched `id`s, case-insensitively, skipping unmatched names.

- [ ] **Step 1: Write the failing tests**

Add a new test class to `test_job_tool.py`, placed just before `class TestFetchWorkdayPostings` (reuse the `TENANT_INFO_FIXTURE` already defined right above that class):

```python
WORKDAY_FACETS_FIXTURE = [
    {
        "facetParameter": "jobFamilyGroup",
        "descriptor": "Job Category",
        "values": [
            {"descriptor": "Engineering", "id": "cat-eng", "count": 1756},
            {"descriptor": "Research", "id": "cat-research", "count": 39},
            {"descriptor": "Sales", "id": "cat-sales", "count": 330},
        ],
    },
    {
        "facetParameter": "timeType",
        "descriptor": "Time Type",
        "values": [{"descriptor": "Full time", "id": "tt-full", "count": 2678}],
    },
    {
        "facetParameter": "locationMainGroup",
        "values": [
            {
                "facetParameter": "locationHierarchy2",
                "descriptor": "Location Type",
                "values": [{"descriptor": "Office", "id": "loc-office", "count": 2530}],
            },
            {
                "facetParameter": "locationHierarchy1",
                "descriptor": "Locations",
                "values": [
                    {"descriptor": "United Kingdom", "id": "loc-uk", "count": 54},
                    {"descriptor": "Germany", "id": "loc-de", "count": 56},
                ],
            },
        ],
    },
]


class TestFindFacetValues(unittest.TestCase):
    def test_finds_top_level_facet(self):
        values = job_tool.find_facet_values(WORKDAY_FACETS_FIXTURE, "jobFamilyGroup")
        self.assertEqual([v["descriptor"] for v in values], ["Engineering", "Research", "Sales"])

    def test_finds_facet_nested_under_locationMainGroup(self):
        values = job_tool.find_facet_values(WORKDAY_FACETS_FIXTURE, "locationHierarchy1")
        self.assertEqual([v["descriptor"] for v in values], ["United Kingdom", "Germany"])

    def test_returns_empty_list_when_not_found(self):
        self.assertEqual(job_tool.find_facet_values(WORKDAY_FACETS_FIXTURE, "nonexistent"), [])

    def test_empty_facets_input(self):
        self.assertEqual(job_tool.find_facet_values([], "jobFamilyGroup"), [])
        self.assertEqual(job_tool.find_facet_values(None, "jobFamilyGroup"), [])


class TestResolveFacetIds(unittest.TestCase):
    def setUp(self):
        self.values = job_tool.find_facet_values(WORKDAY_FACETS_FIXTURE, "jobFamilyGroup")

    def test_matches_case_insensitively(self):
        self.assertEqual(job_tool.resolve_facet_ids(self.values, ["engineering"]), ["cat-eng"])
        self.assertEqual(job_tool.resolve_facet_ids(self.values, ["ENGINEERING"]), ["cat-eng"])

    def test_matches_multiple_names(self):
        ids = job_tool.resolve_facet_ids(self.values, ["Engineering", "Research"])
        self.assertEqual(set(ids), {"cat-eng", "cat-research"})

    def test_skips_unmatched_names_silently(self):
        ids = job_tool.resolve_facet_ids(self.values, ["Engineering", "Nonexistent Category"])
        self.assertEqual(ids, ["cat-eng"])

    def test_no_names_matched_returns_empty_list(self):
        self.assertEqual(job_tool.resolve_facet_ids(self.values, ["Nonexistent"]), [])

    def test_handles_whitespace_around_names(self):
        self.assertEqual(job_tool.resolve_facet_ids(self.values, ["  Engineering  "]), ["cat-eng"])


class TestFetchWorkdayFacets(unittest.TestCase):
    @patch("job_tool.http_post_json")
    def test_requests_minimal_page_and_returns_facets(self, mock_post):
        mock_post.return_value = ({"total": 2678, "jobPostings": [{"title": "X"}], "facets": WORKDAY_FACETS_FIXTURE}, None)
        facets, err = job_tool.fetch_workday_facets(TENANT_INFO_FIXTURE["api_base"])
        self.assertIsNone(err)
        self.assertEqual(facets, WORKDAY_FACETS_FIXTURE)
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], f"{TENANT_INFO_FIXTURE['api_base']}/jobs")
        self.assertEqual(call_args[0][1]["limit"], 1)
        self.assertEqual(call_args[0][1]["appliedFacets"], {})

    @patch("job_tool.http_post_json")
    def test_error_propagates(self, mock_post):
        mock_post.return_value = (None, "HTTP 500 from acme")
        facets, err = job_tool.fetch_workday_facets(TENANT_INFO_FIXTURE["api_base"])
        self.assertIsNone(facets)
        self.assertEqual(err, "HTTP 500 from acme")

    @patch("job_tool.http_post_json")
    def test_missing_facets_key_gives_empty_list_not_error(self, mock_post):
        mock_post.return_value = ({"total": 0, "jobPostings": []}, None)
        facets, err = job_tool.fetch_workday_facets(TENANT_INFO_FIXTURE["api_base"])
        self.assertIsNone(err)
        self.assertEqual(facets, [])
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestFindFacetValues test_job_tool.TestResolveFacetIds test_job_tool.TestFetchWorkdayFacets -v`
Expected: FAIL — `AttributeError: module 'job_tool' has no attribute 'find_facet_values'` (and similarly for the other two; none of the three functions exist yet).

- [ ] **Step 3: Implement the three functions**

In `job_tool.py`, add these three functions immediately before `def fetch_workday_postings`:

```python
def find_facet_values(facets, facet_parameter):
    """Recursively search a Workday /jobs response's `facets` tree for the entry whose
    facetParameter matches, returning its `values` list (each {descriptor, id, count}).
    Workday nests location-related facets under a `locationMainGroup` wrapper that has no
    facetParameter match of its own -- locationHierarchy1/2 and `locations` live inside it --
    while category/type facets (e.g. jobFamilyGroup) are top-level. This walks both shapes
    uniformly. Returns [] if nothing matches."""
    for f in facets or []:
        if f.get("facetParameter") == facet_parameter:
            return f.get("values") or []
        nested = f.get("values") or []
        if nested and isinstance(nested[0], dict) and "facetParameter" in nested[0]:
            found = find_facet_values(nested, facet_parameter)
            if found:
                return found
    return []


def resolve_facet_ids(values, names):
    """Match human-readable names (case-insensitive, whitespace-trimmed) against a facet's
    `values` list (as returned by find_facet_values), returning the matched `id`s. A name with
    no match is silently skipped -- a company simply not having a given category/location isn't
    an error, same contract as every other `search` source in this script."""
    wanted = {n.strip().lower() for n in names if n and n.strip()}
    return [v["id"] for v in values if (v.get("descriptor") or "").strip().lower() in wanted]


def fetch_workday_facets(api_base):
    """One lightweight request to discover a Workday tenant's available facets (Job Category,
    Locations, etc.) -- used to resolve human-readable category/location names to the opaque
    per-tenant IDs Workday's appliedFacets filter requires. The facets list is present in the
    response regardless of `limit`, so this asks for the smallest useful page (limit=1) rather
    than a full board fetch. Returns (facets, error)."""
    data, err = http_post_json(
        f"{api_base}/jobs", {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}
    )
    if err:
        return None, err
    return data.get("facets") or [], None
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestFindFacetValues test_job_tool.TestResolveFacetIds test_job_tool.TestFetchWorkdayFacets -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Run the full suite**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v 2>&1 | tail -5`
Expected: all pass (67 from Task 1 + 12 new = 79).

- [ ] **Step 6: Commit**

```bash
cd tools/job-search/scripts
git add job_tool.py test_job_tool.py
git commit -m "job-search: add Workday facet-resolution helpers

find_facet_values/resolve_facet_ids/fetch_workday_facets -- the building
blocks for filtering a Workday board by category and location server-side
instead of scanning-then-guessing client-side. Verified live against NVIDIA's
real /wday/cxs/.../jobs endpoint that a posting's category exists only as a
facet-level construct (Job Category -> facetParameter 'jobFamilyGroup'), never
per-posting -- and that location facets (locationHierarchy1) are nested one
level deeper under a locationMainGroup wrapper, unlike category facets.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Rewire `fetch_workday_postings` onto server-side facet filtering

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (`fetch_workday_postings`)
- Test: `tools/job-search/scripts/test_job_tool.py` (`TestFetchWorkdayPostings` — one existing test is replaced, others extended)

**Interfaces:**
- Consumes: Task 2's `fetch_workday_facets`, `find_facet_values`, `resolve_facet_ids`.
- Produces: `fetch_workday_postings(tenant_info, query=None, limit=25, max_scanned=WORKDAY_MAX_JOBS_SCANNED, location_hint=None, job_family_groups=None)` — new `job_family_groups` parameter (comma-separated category names, same string convention as the CLI flag Task 4 adds). `location_hint`'s *meaning* changes: it's now resolved to an exact `locationHierarchy1` facet ID and applied via `appliedFacets`, replacing the old `hint in locationsText.lower()` substring check entirely. Return shape and error contract are unchanged.

- [ ] **Step 1: Delete the now-obsolete fuzzy-location test**

In `test_job_tool.py`, remove this entire test method from `class TestFetchWorkdayPostings` (it asserts the old client-side substring-filtering behavior — including the "ambiguous multi-location" `"3 Locations"` special case — which this task removes):

```python
    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_location_hint_paginates_past_max_scanned_but_only_detail_fetches_matches(self, mock_post, mock_get):
        # Simulates a large board (paginates well past max_scanned=25 during the cheap list stage)
        # where only a couple of postings actually mention the hinted location -- the expensive
        # detail-fetch stage should only run for those, not for the whole paginated list.
        pages = []
        for page_num in range(3):  # 3 pages x 20 = 60 postings paginated, only 2 relevant
            postings = []
            for i in range(job_tool.WORKDAY_PAGE_SIZE):
                idx = page_num * job_tool.WORKDAY_PAGE_SIZE + i
                if idx == 5:
                    loc = "London, United Kingdom"
                elif idx == 45:
                    loc = "3 Locations"  # ambiguous multi-location -- should also be treated as a candidate
                else:
                    loc = "Mountain View, CA, USA"
                postings.append({"title": f"J{idx}", "externalPath": f"/job/{idx}", "locationsText": loc, "postedOn": "Posted Today"})
            pages.append({"total": 60, "jobPostings": postings})
        mock_post.side_effect = [(p, None) for p in pages]
        mock_get.return_value = ({"jobPostingInfo": {"title": "J", "location": "London, United Kingdom"}}, None)

        results, err = job_tool.fetch_workday_postings(
            TENANT_INFO_FIXTURE, limit=25, max_scanned=25, location_hint="United Kingdom",
        )
        self.assertIsNone(err)
        self.assertEqual(mock_post.call_count, 3)  # pagination ran past max_scanned=25 to see all 60
        self.assertEqual(mock_get.call_count, 2)   # only the London match + the ambiguous "3 Locations" one
```

This test's replacement is written fresh in Step 2 below (not a 1:1 rename — the new mechanism doesn't paginate-then-filter, it filters at the query, so the whole scenario is different).

- [ ] **Step 2: Write the new failing tests**

Add these methods to `class TestFetchWorkdayPostings` (they call `fetch_workday_facets` internally, which itself calls `http_post_json` — same mock target as the main search call, so `mock_post.side_effect` needs one entry per call in order: facets call first, then each paginated search call):

```python
    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_job_family_groups_resolved_and_applied_server_side(self, mock_post, mock_get):
        mock_post.side_effect = [
            ({"total": 0, "jobPostings": [], "facets": WORKDAY_FACETS_FIXTURE}, None),  # facets discovery call
            ({"total": 1, "jobPostings": [{"title": "A", "externalPath": "/job/A", "locationsText": "X", "postedOn": "Posted Today"}]}, None),  # the real search
        ]
        mock_get.return_value = ({"jobPostingInfo": {"title": "A", "location": "X"}}, None)

        results, err = job_tool.fetch_workday_postings(
            TENANT_INFO_FIXTURE, job_family_groups="Engineering,Research",
        )
        self.assertIsNone(err)
        self.assertEqual(len(results), 1)
        # second call is the real search -- assert it carried the resolved facet IDs
        search_call_body = mock_post.call_args_list[1][0][1]
        self.assertEqual(set(search_call_body["appliedFacets"]["jobFamilyGroup"]), {"cat-eng", "cat-research"})

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_location_hint_resolved_to_exact_facet_id_not_substring_matched(self, mock_post, mock_get):
        mock_post.side_effect = [
            ({"total": 0, "jobPostings": [], "facets": WORKDAY_FACETS_FIXTURE}, None),
            ({"total": 1, "jobPostings": [{"title": "A", "externalPath": "/job/A", "locationsText": "UK, Cambridge", "postedOn": "Posted Today"}]}, None),
        ]
        mock_get.return_value = ({"jobPostingInfo": {"title": "A", "location": "UK, Cambridge"}}, None)

        results, err = job_tool.fetch_workday_postings(
            TENANT_INFO_FIXTURE, location_hint="United Kingdom",
        )
        self.assertIsNone(err)
        self.assertEqual(len(results), 1)
        search_call_body = mock_post.call_args_list[1][0][1]
        self.assertEqual(search_call_body["appliedFacets"]["locationHierarchy1"], ["loc-uk"])

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_both_filters_combined_in_one_applied_facets_dict(self, mock_post, mock_get):
        mock_post.side_effect = [
            ({"total": 0, "jobPostings": [], "facets": WORKDAY_FACETS_FIXTURE}, None),
            ({"total": 0, "jobPostings": []}, None),
        ]
        job_tool.fetch_workday_postings(
            TENANT_INFO_FIXTURE, job_family_groups="Engineering", location_hint="United Kingdom",
        )
        search_call_body = mock_post.call_args_list[1][0][1]
        self.assertEqual(search_call_body["appliedFacets"]["jobFamilyGroup"], ["cat-eng"])
        self.assertEqual(search_call_body["appliedFacets"]["locationHierarchy1"], ["loc-uk"])

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_unmatched_location_hint_falls_back_to_no_location_filter(self, mock_post, mock_get):
        mock_post.side_effect = [
            ({"total": 0, "jobPostings": [], "facets": WORKDAY_FACETS_FIXTURE}, None),
            ({"total": 0, "jobPostings": []}, None),
        ]
        job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE, location_hint="Atlantis")
        search_call_body = mock_post.call_args_list[1][0][1]
        self.assertNotIn("locationHierarchy1", search_call_body["appliedFacets"])

    @patch("job_tool.http_post_json")
    def test_facets_discovery_error_propagates(self, mock_post):
        mock_post.return_value = (None, "HTTP 500 from acme")
        results, err = job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE, location_hint="United Kingdom")
        self.assertEqual(results, [])
        self.assertEqual(err, "HTTP 500 from acme")

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_no_hint_or_groups_skips_facets_discovery_entirely(self, mock_post, mock_get):
        # Backward-compat: a plain call with neither filter must not spend the extra facets
        # request at all -- same call count as before this feature existed.
        mock_post.return_value = ({"total": 0, "jobPostings": []}, None)
        job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE)
        self.assertEqual(mock_post.call_count, 1)
```

- [ ] **Step 3: Run to verify the new tests fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestFetchWorkdayPostings -v`
Expected: FAIL — `fetch_workday_postings() got an unexpected keyword argument 'job_family_groups'` (and the other new tests fail similarly; the old deleted test is gone so it doesn't show up at all). The pre-existing tests in this class (pagination, zero-postings, detail-fetch-error, max_scanned cap, no-hint-unchanged-budget) should currently **pass** unchanged — they don't touch the new parameter.

- [ ] **Step 4: Rewrite `fetch_workday_postings`**

Replace the entire function body (keep the same `def fetch_workday_postings(...)` signature line but add the new parameter, and keep the function's opening docstring paragraph about per-posting detail fetches being necessary — extend it, don't remove it):

```python
def fetch_workday_postings(tenant_info, query=None, limit=25, max_scanned=WORKDAY_MAX_JOBS_SCANNED,
                            location_hint=None, job_family_groups=None):
    """Paginate a Workday CXS job-search endpoint, then fetch full detail for every posting found
    (bounded by max_scanned) and return them in posting() shape.

    Fetching every detail matters, not just the compact search list: a posting's *primary* office
    can be outside the target location (e.g. "Copenhagen, Denmark") while the target location is
    still one of several `additionalLocations` a candidate can choose -- the compact list's
    `locationsText` sometimes collapses this down to "N Locations" but sometimes just shows the
    primary city with no hint it's multi-site at all. This gap was found and verified by hand by
    cross-checking Unity's live board against unity.com/careers directly in a browser.

    `location_hint` and `job_family_groups` are both applied server-side via Workday's own
    `appliedFacets` filter, not by scanning and re-filtering client-side. Verified live against
    NVIDIA: a posting's category is NOT present in either the compact list or the per-posting
    detail JSON -- it exists only as a facet-level construct (facetParameter "jobFamilyGroup"),
    discoverable via one lightweight `fetch_workday_facets` call, then applied as an exact ID
    match via `find_facet_values`/`resolve_facet_ids`. This replaces an earlier, shipped version
    of `location_hint` that did a fuzzy `hint in locationsText.lower()` substring check --
    verified live to silently fail against real site labels like "UK, Cambridge" (which does not
    contain the substring "united kingdom"). That client-side filtering step is removed entirely
    in favor of this.

    Combining both filters narrows the query at the source: a company the size of NVIDIA (2,000
    postings company-wide) returns a handful to a few dozen results for a category+location
    query, not 2,000 -- so `max_scanned` stops being a practical constraint for a targeted query
    like this, even though it still exists as an outer safety cap for the case where only one
    broad filter (or neither) is applied.

    `job_family_groups`, if given, is a comma-separated string of category names (matched
    case-insensitively against that tenant's actual facet descriptors, e.g. "Engineering,
    Research"). A name with no matching facet for this tenant is silently skipped, not an error --
    same contract `resolve_facet_ids` already documents.

    Returns (results, error). A company genuinely having zero current openings is not an error --
    it comes back as (empty results, None), same contract as every other `search` source."""
    api_base = tenant_info["api_base"]
    public_base = tenant_info["public_base"]

    applied_facets = {}
    if job_family_groups or location_hint:
        facets, err = fetch_workday_facets(api_base)
        if err:
            return [], err
        if job_family_groups:
            names = job_family_groups.split(",")
            ids = resolve_facet_ids(find_facet_values(facets, "jobFamilyGroup"), names)
            if ids:
                applied_facets["jobFamilyGroup"] = ids
        if location_hint:
            ids = resolve_facet_ids(find_facet_values(facets, "locationHierarchy1"), [location_hint])
            if ids:
                applied_facets["locationHierarchy1"] = ids

    pagination_cap = WORKDAY_PAGINATION_CAP if applied_facets else max_scanned

    postings, offset, total = [], 0, None
    while total is None or (len(postings) < total and len(postings) < pagination_cap):
        data, err = http_post_json(
            f"{api_base}/jobs",
            {"appliedFacets": applied_facets, "limit": WORKDAY_PAGE_SIZE, "offset": offset, "searchText": query or ""},
        )
        if err:
            return [], err
        total = data.get("total", 0)
        page = data.get("jobPostings", [])
        if not page:  # safety valve: a page reporting nothing ends pagination even if `total` claims more
            break
        postings.extend(page)
        offset += WORKDAY_PAGE_SIZE
    postings = postings[:pagination_cap]
    postings = postings[:max_scanned]

    def fetch_one(raw):
        detail, err = http_get_json(f"{api_base}{raw['externalPath']}")
        return raw, detail, err

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=WORKDAY_DETAIL_WORKERS) as pool:
        futures = [pool.submit(fetch_one, raw) for raw in postings]
        for future in as_completed(futures):
            raw, detail, err = future.result()
            if err:
                errors.append(err)
                continue
            jp = (detail or {}).get("jobPostingInfo", {})
            location = jp.get("location") or raw.get("locationsText") or ""
            additional = jp.get("additionalLocations") or []
            results.append(posting(
                "workday",
                jp.get("title") or raw.get("title"),
                tenant_info.get("company"),
                ", ".join([location, *additional]) if additional else location,
                is_remote_location(location) or any(is_remote_location(loc) for loc in additional),
                jp.get("externalUrl") or f"{public_base}{raw['externalPath']}",
                [],
                None,
                jp.get("postedOn") or raw.get("postedOn"),
                None,
            ))

    if not results and errors:
        return [], f"{len(errors)} detail fetch(es) failed, e.g. {errors[0]}"
    return results[:limit], None
```

The only substantive changes from the current version: the new `job_family_groups` parameter and the `applied_facets` resolution block before the pagination loop; the pagination loop's request body now sends `applied_facets` instead of always `{}`; `pagination_cap` is now keyed on `applied_facets` (truthy if either filter resolved to at least one ID) instead of only on `location_hint`; and the old `if location_hint: postings = [...]` client-side substring-filter block (which sat between the two `postings[:...]` capping lines) is deleted outright.

- [ ] **Step 5: Run to verify all tests pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestFetchWorkdayPostings -v`
Expected: PASS — the 5 pre-existing tests (pagination, search-error, zero-postings, all-detail-fetches-failing, max_scanned cap) plus the 6 new ones from Step 2 (11 total; the one deleted test is gone, not replaced 1:1).

- [ ] **Step 6: Run the full suite**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v 2>&1 | tail -5`
Expected: all pass. (79 after Task 2, minus 1 deleted, plus 6 new = 84.)

- [ ] **Step 7: Commit**

```bash
cd tools/job-search/scripts
git add job_tool.py test_job_tool.py
git commit -m "job-search: filter Workday postings by category and location server-side

fetch_workday_postings gains job_family_groups (comma-separated category
names) and reimplements location_hint on the same mechanism: both resolve to
exact appliedFacets IDs via fetch_workday_facets, applied at the query, not
guessed client-side afterward. Removes the old hint-in-locationsText substring
check, which verified live to silently miss real Workday site labels like
'UK, Cambridge' (no 'united kingdom' substring).

Verified live against NVIDIA: an Engineering+United Kingdom query returned 16
of the 20 postings a human judge picked from reading all 54 UK titles by
hand -- the 4-posting gap was pre-sales-flavored 'Solutions Architect' roles
NVIDIA itself buckets outside Engineering, i.e. this is *more* accurate than
manual title judgment for exactly the case rnd-titles.md's Solutions Architect
exclusion rule exists to handle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire `--job-family-groups` through the CLI

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (`cmd_search_discover_workday`, `cmd_search_workday_jobs`, and the two argparse subparsers)
- Test: `tools/job-search/scripts/test_job_tool.py` (`TestCmdSearchDiscoverWorkday`, `TestCmdSearchWorkdayJobs`)

**Interfaces:**
- Consumes: Task 3's `fetch_workday_postings(..., job_family_groups=...)`.
- Produces: `python3 job_tool.py search workday-jobs --slug <slug> --job-family-groups "Engineering,Research" [...]` and the same flag on `search discover-workday` — used by Task 6's SKILL.md instructions.

- [ ] **Step 1: Write the failing tests**

In `class TestCmdSearchDiscoverWorkday`, update the `_run` helper to accept the new field and add one test:

```python
    def _run(self, url, company=None, query=None, limit=25, location_hint=None, job_family_groups=None):
        args = argparse.Namespace(
            url=url, company=company, query=query, limit=limit,
            location_hint=location_hint, job_family_groups=job_family_groups,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_discover_workday(args)
        return json.loads(buf.getvalue())
```

Add to the same class:

```python
    @patch("job_tool.http_post_json")
    @patch("job_tool.http_get_html")
    def test_job_family_groups_flag_is_passed_through(self, mock_html, mock_post):
        mock_html.return_value = (
            '<html><a href="https://acme.wd1.myworkdayjobs.com/Acme">Careers</a></html>', None,
        )
        mock_post.side_effect = [
            ({"total": 0, "jobPostings": [], "facets": []}, None),
            ({"total": 0, "jobPostings": []}, None),
        ]
        self._run("https://acme.com/careers", company="Acme Corp", job_family_groups="Engineering")
        # facets-discovery call happened -- proves job_family_groups reached fetch_workday_postings
        self.assertEqual(mock_post.call_count, 2)
```

In `class TestCmdSearchWorkdayJobs`, same pattern:

```python
    def _run(self, slug, company=None, query=None, limit=25, location_hint=None, job_family_groups=None):
        args = argparse.Namespace(
            slug=slug, company=company, query=query, limit=limit,
            location_hint=location_hint, job_family_groups=job_family_groups,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_workday_jobs(args)
        return json.loads(buf.getvalue())
```

Add to the same class:

```python
    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_job_family_groups_flag_is_passed_through(self, mock_post, mock_get):
        mock_post.side_effect = [
            ({"total": 0, "jobPostings": [], "facets": []}, None),
            ({"total": 0, "jobPostings": []}, None),
        ]
        self._run("acme/wd1/Acme", company="Acme Corp", job_family_groups="Engineering")
        self.assertEqual(mock_post.call_count, 2)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdSearchDiscoverWorkday test_job_tool.TestCmdSearchWorkdayJobs -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'job_family_groups'` (the two command functions don't read that field yet, but the bigger issue is the argparse-built `args` in real usage won't have it either — this step's Namespace already includes it manually, so the failure is specifically inside `cmd_search_discover_workday`/`cmd_search_workday_jobs` not passing it through to `fetch_workday_postings`).

- [ ] **Step 3: Update the two command functions**

In `cmd_search_discover_workday`, find:

```python
    results, err = fetch_workday_postings(tenant_info, args.query, args.limit, location_hint=args.location_hint)
```

Replace with:

```python
    results, err = fetch_workday_postings(
        tenant_info, args.query, args.limit,
        location_hint=args.location_hint, job_family_groups=args.job_family_groups,
    )
```

In `cmd_search_workday_jobs`, find the identical line and apply the same replacement.

- [ ] **Step 4: Add the argparse flag to both subparsers**

Find the `p_discover_workday` block and add, right after the existing `--location-hint` argument (update that argument's help text too, since its behavior changed in Task 3):

```python
    p_discover_workday.add_argument(
        "--location-hint", dest="location_hint",
        help="Location name to filter to server-side via Workday's own location facet (exact "
             "match against that tenant's facet descriptors, e.g. 'United Kingdom'). A name with "
             "no matching facet for this tenant is silently skipped, not an error.",
    )
    p_discover_workday.add_argument(
        "--job-family-groups", dest="job_family_groups",
        help="Comma-separated category names to filter to server-side via Workday's Job Category "
             "facet (e.g. 'Engineering,Research'), matched case-insensitively against that "
             "tenant's actual facet descriptors. A name with no match for this tenant is silently "
             "skipped, not an error.",
    )
```

Apply the identical two `add_argument` calls (same flags, same help text) to the `p_workday_jobs` block, replacing its existing `--location-hint` argument and adding `--job-family-groups` right after it.

- [ ] **Step 5: Run to verify tests pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdSearchDiscoverWorkday test_job_tool.TestCmdSearchWorkdayJobs -v`
Expected: PASS (all tests in both classes, including the 2 new ones).

- [ ] **Step 6: Run the full suite**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v 2>&1 | tail -5`
Expected: all pass (84 from Task 3 + 2 new = 86).

- [ ] **Step 7: Manual CLI smoke test**

```bash
cd tools/job-search/scripts
python3 job_tool.py search workday-jobs --help 2>&1 | grep -A2 "job-family-groups"
```
Expected: the new flag's help text is printed, confirming the parser wiring is syntactically valid (argparse would raise at import/parse time otherwise).

- [ ] **Step 8: Commit**

```bash
cd tools/job-search/scripts
git add job_tool.py test_job_tool.py
git commit -m "job-search: expose --job-family-groups on workday-jobs and discover-workday

Wires Task 3's server-side category filtering through the CLI. --location-hint's
help text is updated to describe its new exact-facet-match behavior.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Department taxonomy reference

**Files:**
- Create: `tools/rnd-catalogue/references/rnd-departments.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a reference file Task 6's SKILL.md points to by path (`references/rnd-departments.md`, relative to the skill directory) — content only, no code interface.

- [ ] **Step 1: Write the reference file**

Create `tools/rnd-catalogue/references/rnd-departments.md`:

```markdown
# R&D department taxonomy — Engineering / Product / Data

Used by Catalogue mode's Stage 2 (see `../SKILL.md`) as the **primary** filter: if a posting's
`tags` (its department/category, as returned by `job_tool.py`) has a usable value, match it
against this file and stop there — the title is never consulted for these. Title-matching
(`rnd-titles.md`) only runs as a fallback when `tags` is empty or a known-generic bucket (e.g.
`"Other"`).

Match against each `tags` entry as a whole value, case-insensitively — not a title-style
substring search. A posting can have multiple tags (rare, but some sources allow it); it counts
as a match if *any* tag is in Include and *none* is in Exclude.

## Include

Engineering, R&D, Research, Research & Development, Product, Product Management, Data,
Data Science, Data & Analytics, AI, AI/ML, Machine Learning, Software Engineering,
Hardware Engineering.

## Exclude — takes priority over an Include match on another tag from the same posting

Sales, GTM, Marketing, Business Development, Customer Success, Delivery, Services,
Professional Services, Finance, Legal, Human Resources, People, Facilities, Administration,
Corporate Strategy.

## Ambiguous — use judgment, don't auto-include or auto-exclude

- **Security** — Cybersecurity/Information Security engineering is R&D; Corporate/Physical
  Security isn't. A bucket named bare `"Security"` (no further qualifier) needs a look at the
  posting itself before deciding either way.
- **Operations** — Engineering Ops / DevOps-adjacent buckets are R&D; general business
  Operations isn't. Same "look before deciding" rule as Security.
- **IT - Information Technology** — internal IT support usually isn't R&D; some companies fold
  platform engineering into an "IT" bucket instead of "Engineering". Check the posting.
- **Program Manager** — same caveat `rnd-titles.md` already documents for the title case: only
  R&D-scoped if the posting itself makes that clear, not by department label alone.

## Fallback trigger

Treat a posting's department data as unusable (fall through to `rnd-titles.md`'s title-matching
instead) when `tags` is empty, or every tag present is a company-specific label that carries no
generic meaning on its own (e.g. `"ORCAserv Technologies"` — a department tag that's really just
the company's own name, seen live on ORCA's Greenhouse board).
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -c '^## ' tools/rnd-catalogue/references/rnd-departments.md`
Expected: `4` (Include, Exclude, Ambiguous, Fallback trigger).

- [ ] **Step 3: Commit**

```bash
git add tools/rnd-catalogue/references/rnd-departments.md
git commit -m "docs(rnd-catalogue): add R&D department taxonomy reference

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Rewrite Catalogue mode Stage 1 and Stage 2

**Files:**
- Modify: `tools/rnd-catalogue/SKILL.md`

**Interfaces:**
- Consumes: Task 4's `--job-family-groups`/`--location-hint` CLI flags; Task 5's `references/rnd-departments.md`; the existing `references/rnd-titles.md` (kept, now fallback-only).
- Produces: nothing further downstream — this is the last task.

- [ ] **Step 1: Replace Stage 1's Workday fetch command**

In `SKILL.md`'s Catalogue mode, Stage 1 currently reads (find this exact block):

```
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search ats --platform <platform> --company <slug> --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search workday-jobs --slug <slug> --company "<name>" --location-hint "United Kingdom" --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search comeet-jobs --slug <slug> --company "<name>" --limit 500
```
`--location-hint` matters specifically for Workday: detail-fetching is capped at 150 postings
per company regardless of `--limit`, so for a large board (NVIDIA: 2,000+ postings company-wide)
the hint is what makes sure that budget is spent on UK-relevant postings instead of the first
150 encountered. Always pass it for `workday-jobs` — it's harmless on small boards.
```

Replace it with:

```
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search ats --platform <platform> --company <slug> --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search workday-jobs --slug <slug> --company "<name>" --location-hint "United Kingdom" --job-family-groups "Engineering,R&D,Research,Research & Development,Product,Product Management,Data,Data Science,Data & Analytics,AI,AI/ML,Machine Learning,Software Engineering,Hardware Engineering" --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search comeet-jobs --slug <slug> --company "<name>" --limit 500
```
`--job-family-groups` is `references/rnd-departments.md`'s Include list, verbatim, comma-joined —
this filters Workday's own index to R&D-category postings server-side, before any detail fetch
happens. `--location-hint` now resolves to an exact facet match (not the old fuzzy text guess),
so it's both cheap and reliable — always pass both for `workday-jobs`, they're harmless on small
boards and dramatically narrow large ones (a category+location-filtered query returns a handful
to a few dozen results even for a 2,000-posting board, well under any detail-fetch budget
concern).
```

- [ ] **Step 2: Rewrite Stage 2's filtering logic**

Stage 2 currently reads (find this exact block, right after Stage 1):

```
### Stage 2 — Filter to London/remote-UK, Engineering/Product/Data

For every posting from Stage 1:
- **Location**: keep if it's London, or marked/tagged remote in a way that includes the UK
  (judge from `location`/`remote`/`tags` — same holistic judgment `job-search` already applies,
  no separate script for this).
- **R&D scope**: read `references/rnd-titles.md`. Keep if the title matches an include keyword
  and isn't excluded by the exclude list. Where the posting has a `tags` list (Greenhouse/Lever
  populate this from the board's own department/category field), treat a tag that's obviously
  non-R&D (Sales, Marketing, HR, Finance, Legal, Customer Success) as a veto even if the title
  alone would have matched — this is a real signal, not a guess, when the source provides it.

Before building the filtered array to pass into Stage 3, normalize every posting's `company`
field to the matching `target_companies` entry's `name` — not whatever `job_tool.py search`
returned. `search ats` in particular echoes back the ATS **slug** (e.g. `"monzo"`), not the
display name (`"Monzo"`); since Stage 3's `--companies` list is built from `name`, leaving the
slug in place means `catalogue_store.py` can never match that posting to a queried company, so it
silently never gets marked closed.
```

Replace it with:

```
### Stage 2 — Filter to London/remote-UK, R&D department (title as fallback only)

For every posting from Stage 1:
- **Location**: keep if it's London, or marked/tagged remote in a way that includes the UK
  (judge from `location`/`remote`/`tags` — same holistic judgment `job-search` already applies,
  no separate script for this). For Workday postings already fetched with `--job-family-groups`,
  this is still needed — the category filter doesn't replace the location judgment, since a
  posting can list the UK as one of several eligible sites without the compact text saying so
  plainly (see the multi-location note in `job_tool.py`'s own `fetch_workday_postings`
  docstring).
- **R&D scope — department first**: if the posting's `tags` has a usable value (not empty, not a
  company-specific label that means nothing on its own — see `references/rnd-departments.md`'s
  "Fallback trigger" section), match it against that file's Include/Exclude lists and stop there.
  **Do not also check the title for these** — a department match is decisive on its own,
  Workday's own categorization has been directly verified to catch cases (pre-sales-flavored
  "Solutions Architect" titles) that title-matching alone got wrong.
- **R&D scope — title fallback**: only when `tags` is empty or generic, fall through to
  `references/rnd-titles.md`'s title-matching (unchanged from before this change).
- **Workday postings specifically**: since Stage 1 already fetched with `--job-family-groups` set
  to the Include list, every returned posting is *by construction* already in an Include
  department — there's no `tags` data to double-check against (Workday postings still come back
  with empty `tags`, see `job_tool.py`'s Workday integration), so treat a Workday posting from
  this fetch as already department-matched; only the location judgment above still applies to it.

Before building the filtered array to pass into Stage 3, normalize every posting's `company`
field to the matching `target_companies` entry's `name` — not whatever `job_tool.py search`
returned. `search ats` in particular echoes back the ATS **slug** (e.g. `"monzo"`), not the
display name (`"Monzo"`); since Stage 3's `--companies` list is built from `name`, leaving the
slug in place means `catalogue_store.py` can never match that posting to a queried company, so it
silently never gets marked closed.
```

- [ ] **Step 3: Verify the edits landed cleanly**

Run: `grep -n 'job-family-groups\|department first\|title fallback' tools/rnd-catalogue/SKILL.md`
Expected: matches in both the Stage 1 command block and the new Stage 2 text — confirms both
edits are present and didn't silently no-op (e.g. from a stale `old_string` match failing).

Run: `grep -c '^```' tools/rnd-catalogue/SKILL.md`
Expected: an even number — confirms no stray/unbalanced code fence was introduced (this exact
class of mistake happened once already in this skill's history; worth checking every time this
file is edited).

- [ ] **Step 4: Commit**

```bash
git add tools/rnd-catalogue/SKILL.md
git commit -m "docs(rnd-catalogue): filter Catalogue mode by department first, title as fallback

Stage 1's workday-jobs fetch now passes --job-family-groups (the new
references/rnd-departments.md Include list) alongside --location-hint,
filtering server-side before any detail fetch. Stage 2 checks a posting's
department tag first and only falls through to the existing title-matching
(rnd-titles.md) when department data is missing or unusable.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## After this plan

No task in this plan re-runs the full 50-company watchlist through the new mechanism — that's a
real, user-visible action (fetches, possibly `profile set` writes) that belongs to a follow-up
"run the catalogue" invocation, not to building the feature. The natural next step once this
plan is complete and merged is Yoav asking to re-run Catalogue mode so the new department-based
results replace the ad-hoc, partially-manual results from this session's dogfooding.
