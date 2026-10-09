"""Workday CXS discovery and board fetch."""

import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobsearch.fetchconfig import DEFAULT as DEFAULT_FETCH
from jobsearch.http import http_get_html, http_get_json, http_post_json
from jobsearch.sources.common import posting, print_search_result

APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_DEFAULT_WORKDAY_ACTOR = "automation-lab/workday-jobs-scraper"
WORKDAY_URL_RE = re.compile(
    r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/\"\'?#\s]+)(?:/([^/\"\'?#\s]+))?", re.I
)
WORKDAY_LOCALE_RE = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.I)
WORKDAY_PAGE_SIZE = 20
WORKDAY_MAX_JOBS_SCANNED = 150
WORKDAY_DETAIL_WORKERS = 8

def cmd_search_workday(args):
    """Optional paid fallback: runs an Apify Actor against a company's Workday career site.
    Requires APIFY_TOKEN — with no token set, degrades like any other source (error + no results),
    never raises. See README.md for setup/cost."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print_search_result(
            "workday", [],
            "APIFY_TOKEN not set — Workday search is an optional paid fallback, see README",
        )
        return

    actor = os.environ.get("APIFY_WORKDAY_ACTOR_ID", APIFY_DEFAULT_WORKDAY_ACTOR)
    # Token goes in the Authorization header, never the URL — a query-string token would leak
    # into any error message that echoes the URL back (see http_post_json's except clauses).
    run_url = f"{APIFY_API_BASE}/acts/{urllib.parse.quote(actor, safe='')}/run-sync-get-dataset-items"
    payload = {
        "companyUrl": args.url,
        "searchQuery": args.query or "",
        "location": args.location or "",
        "maxJobs": args.limit,
        "includeDescription": True,
    }

    items, err = http_post_json(run_url, payload, extra_headers={"Authorization": f"Bearer {token}"})
    if err:
        print_search_result("workday", [], err)
        return

    results = [
        posting(
            "workday", item.get("title"), item.get("company"), item.get("location"),
            item.get("remoteType") == "Remote", item.get("url"),
            [item["category"]] if item.get("category") else [],
            item.get("compensation"), item.get("postedDate"), item.get("description"),
        )
        for item in (items or [])[: args.limit]
    ]
    print_search_result("workday", results, None)

def detect_workday_tenant(url_or_html):
    """Find a Workday-hosted career site's tenant/wd-host/site from either a bare
    myworkdayjobs.com URL or a page's raw HTML (its own career page will normally link out to it
    even when the page itself is otherwise JS-rendered, since that outbound link is typically
    part of the static markup/nav rather than client-fetched data). Returns a dict with `tenant`,
    `wd_host`, `site`, `api_base` (the CXS search API root), and `public_base` (the public
    browsing URL root -- what `.../job/<path>` external links are relative to), or None if no
    Workday link is present at all."""
    m = WORKDAY_URL_RE.search(url_or_html)
    if not m:
        return None
    tenant, wd_host, first_segment, second_segment = m.group(1), m.group(2), m.group(3), m.group(4)
    # A locale-prefixed tenant (e.g. NVIDIA's ".../en-US/NVIDIAExternalCareerSite/...") puts the
    # real site name in the *second* segment, not the first -- see WORKDAY_URL_RE's comment.
    if WORKDAY_LOCALE_RE.match(first_segment) and second_segment:
        site = second_segment
    else:
        site = first_segment
    return {
        "tenant": tenant,
        "wd_host": wd_host,
        "site": site,
        "api_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}",
        "public_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/{site}",
    }


def is_remote_location(location_text):
    return "remote" in (location_text or "").lower()


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
    return [
        v.get("id") for v in values
        if (v.get("descriptor") or "").strip().lower() in wanted and v.get("id")
    ]


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


def fetch_workday_postings(tenant_info, query=None, limit=25, max_scanned=WORKDAY_MAX_JOBS_SCANNED,
                            location_hint=None, job_family_groups=None, config=None):
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
    config = config or DEFAULT_FETCH
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

    postings, offset, total = [], 0, None
    while total is None or (len(postings) < total and len(postings) < max_scanned):
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
    postings = postings[:max_scanned]

    def fetch_one(raw):
        detail, err = http_get_json(f"{api_base}{raw['externalPath']}", config=config)
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
                jp.get("jobDescription"),
                config=config,
            ))

    # A handful of per-posting detail fetches failing (rate limit, transient network blip) among
    # many successes shouldn't sink the whole call -- only report it as a hard error when NOTHING
    # came back, mirroring discover-ats's "guess, not a confirmed miss" treatment of ambiguity.
    if not results and errors:
        return [], f"{len(errors)} detail fetch(es) failed, e.g. {errors[0]}"
    return results[:limit], None


def cmd_search_discover_workday(args):
    """Detect a company's Workday tenant from a career-page URL (or a myworkdayjobs.com URL
    directly) and, if found, immediately fetch its full posting list -- the free, keyless
    equivalent of `search discover-ats` for Workday-hosted companies. See the module docstring's
    Workday section and references/search-fallbacks.md for when to reach for this."""
    is_workday_url = bool(WORKDAY_URL_RE.search(args.url))
    if is_workday_url:
        html_or_err = (args.url, None)
    else:
        html_or_err = http_get_html(args.url)
    html, fetch_err = html_or_err

    if fetch_err:
        print_search_result("discover-workday", [], fetch_err, {
            "company": args.company, "detected_platform": None, "detected_slug": None,
            "confidence": "none",
        })
        return

    tenant_info = detect_workday_tenant(html)
    if tenant_info is None:
        print_search_result("discover-workday", [], None, {
            "company": args.company, "detected_platform": None, "detected_slug": None,
            "confidence": "none",
        })
        return

    tenant_info["company"] = args.company
    slug = f"{tenant_info['tenant']}/{tenant_info['wd_host']}/{tenant_info['site']}"
    results, err = fetch_workday_postings(
        tenant_info, args.query, args.limit,
        location_hint=args.location_hint, job_family_groups=args.job_family_groups,
    )
    if err:
        print_search_result("discover-workday", [], err, {
            "company": args.company, "detected_platform": "workday", "detected_slug": slug,
            "confidence": "low",
        })
        return

    print_search_result("discover-workday", results, None, {
        "company": args.company, "detected_platform": "workday", "detected_slug": slug,
        "confidence": "high" if results else "low",
    })


def cmd_search_workday_jobs(args):
    """Direct fetch for a Workday tenant already known (e.g. saved to target_companies by a prior
    `discover-workday` call) -- skips the career-page HTML fetch and goes straight to the CXS API."""
    try:
        tenant, wd_host, site = args.slug.split("/")
    except ValueError:
        print_search_result("workday-jobs", [], f"--slug must be '<tenant>/<wd_host>/<site>', got: {args.slug!r}")
        return

    tenant_info = {
        "tenant": tenant, "wd_host": wd_host, "site": site, "company": args.company,
        "api_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}",
        "public_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/{site}",
    }
    results, err = fetch_workday_postings(
        tenant_info, args.query, args.limit,
        location_hint=args.location_hint, job_family_groups=args.job_family_groups,
    )
    print_search_result("workday-jobs", results, err)
