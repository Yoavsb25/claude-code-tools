"""Remotive, Arbeitnow, and Apify jobs-index aggregators."""

import os
import urllib.parse

from jobsearch.http import http_get_json, http_post_json
from jobsearch.sources.common import posting, print_search_result

APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_DEFAULT_JOBS_INDEX_ACTOR = "fantastic-jobs/career-site-job-listing-api"
JOBS_INDEX_DEFAULT_LIMIT = 25
JOBS_INDEX_DEFAULT_TIME_RANGE = "6m"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"

def cmd_search_remotive(args):
    params = {}
    if args.query:
        params["search"] = args.query
    if args.category:
        params["category"] = args.category
    url = REMOTIVE_URL
    if params:
        url += "?" + urllib.parse.urlencode(params)

    data, err = http_get_json(url)
    if err:
        print_search_result("remotive", [], err)
        return

    jobs = data.get("jobs", [])[: args.limit]
    results = [
        posting(
            "remotive", j.get("title"), j.get("company_name"), j.get("candidate_required_location"),
            True, j.get("url"), j.get("tags"), j.get("salary") or None,
            j.get("publication_date"), j.get("description"),
        )
        for j in jobs
    ]
    print_search_result("remotive", results, None)


def cmd_search_arbeitnow(args):
    all_jobs = []
    url = ARBEITNOW_URL
    pages_fetched = 0

    while url and pages_fetched < args.max_pages:
        data, err = http_get_json(url)
        if err:
            if pages_fetched == 0:
                print_search_result("arbeitnow", [], err)
                return
            break
        all_jobs.extend(data.get("data", []))
        url = (data.get("links") or {}).get("next")
        pages_fetched += 1

    query = (args.query or "").lower()
    matched = [
        j for j in all_jobs
        if not query or query in (j.get("title", "") + " " + " ".join(j.get("tags", []))).lower()
    ]
    results = [
        posting(
            "arbeitnow", j.get("title"), j.get("company_name"), j.get("location"),
            j.get("remote", False), j.get("url"), j.get("tags"), None,
            j.get("created_at"), j.get("description"),
        )
        for j in matched[: args.limit]
    ]
    print_search_result("arbeitnow", results, None, {"pages_fetched": pages_fetched})

def _format_jobs_index_salary(item):
    lo, hi, cur = item.get("ai_salary_min_value"), item.get("ai_salary_max_value"), item.get("ai_salary_currency")
    if lo is None and hi is None:
        return None
    unit = item.get("ai_salary_unit_text") or ""
    if lo is not None and hi is not None and lo != hi:
        return f"{lo}-{hi} {cur or ''} {unit}".strip()
    return f"{lo if lo is not None else hi} {cur or ''} {unit}".strip()


def cmd_search_jobs_index(args):
    """Optional paid source: queries a pre-built, continuously-updated index of 175k+ company
    career sites across 54 ATS platforms (Workday, Comeet, Oracle Cloud, SuccessFactors, iCIMS,
    Phenom People, and plenty more we don't have -- and likely never will have -- a dedicated
    free integration for) via structured filters (organization/domain/title/location, AI-classified
    experience level and work arrangement) instead of free-text role-title guessing. This is the
    thing to reach for when a company matches none of the free discover-ats/discover-workday/
    discover-comeet paths -- it very likely still covers them.

    Requires APIFY_TOKEN -- with no token set, degrades like any other source (error + no
    results), never raises. Confirm with the user before running, same as `search workday`: this
    is a paid call, not a free keyless one. Kept cheap by default -- see JOBS_INDEX_DEFAULT_LIMIT
    -- but every call still costs real money. See README.md for setup/cost."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print_search_result(
            "jobs-index", [],
            "APIFY_TOKEN not set -- jobs-index search is an optional paid source, see README",
        )
        return

    actor = os.environ.get("APIFY_JOBS_INDEX_ACTOR_ID", APIFY_DEFAULT_JOBS_INDEX_ACTOR)
    run_url = f"{APIFY_API_BASE}/acts/{urllib.parse.quote(actor, safe='')}/run-sync-get-dataset-items"

    # The Actor rejects `limit` below 10 with an HTTP 400 (verified directly) -- clamp rather than
    # let a small --limit (e.g. someone being cost-conscious) turn into a confusing hard error.
    limit = max(args.limit, 10)
    payload = {"timeRange": args.time_range, "limit": limit}
    if args.company:
        payload["organizationSearch"] = [args.company]
    if args.domain:
        payload["domainFilter"] = [args.domain]
    if args.query:
        payload["titleSearch"] = [args.query]
    if args.location:
        payload["locationSearch"] = [args.location]
    if args.ats:
        payload["ats"] = [p.strip() for p in args.ats.split(",") if p.strip()]
    if args.work_arrangement:
        payload["aiWorkArrangementFilter"] = [args.work_arrangement]

    items, err = http_post_json(run_url, payload, extra_headers={"Authorization": f"Bearer {token}"})
    if err:
        print_search_result("jobs-index", [], err)
        return

    results = [
        posting(
            "jobs-index",
            item.get("title"),
            item.get("organization"),
            ", ".join(item.get("locations_derived") or []) or None,
            (item.get("ai_work_arrangement") or "").lower().startswith("remote"),
            item.get("url"),
            [item["ai_taxonomies_a"][0]] if item.get("ai_taxonomies_a") else [],
            _format_jobs_index_salary(item),
            item.get("date_posted"),
            item.get("description_text"),
        )
        for item in (items or [])
    ]
    print_search_result("jobs-index", results, None)
