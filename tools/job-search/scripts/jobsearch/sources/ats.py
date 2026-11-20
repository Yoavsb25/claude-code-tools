"""Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable."""

import re

from jobsearch.fetchconfig import DEFAULT as DEFAULT_FETCH
from jobsearch.http import http_get_json
from jobsearch.sources.common import posting, print_search_result
from jobsearch.text import ATS_SLUG_SUFFIXES

ATS_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
}
ATS_PROBE_ORDER = ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable"]

def parse_ats_payload(platform, company, data, config=None):
    """Map one platform's raw JSON payload to a list of posting() dicts."""
    config = config or DEFAULT_FETCH
    if platform == "greenhouse":
        return [
            posting(
                "greenhouse", j.get("title"), company, greenhouse_location(j),
                None, j.get("absolute_url"), [d.get("name") for d in j.get("departments", [])],
                None, j.get("updated_at"), j.get("content"),
                config=config,
            )
            for j in data.get("jobs", [])
        ]
    if platform == "lever":
        return [
            posting(
                "lever", j.get("text"), company, (j.get("categories") or {}).get("location"),
                None, j.get("hostedUrl"),
                [(j.get("categories") or {}).get("team")] if (j.get("categories") or {}).get("team") else [],
                None, j.get("createdAt"), j.get("descriptionPlain") or j.get("description"),
                config=config,
            )
            for j in data
        ]
    if platform == "ashby":
        return [
            posting(
                "ashby", j.get("title"), company, j.get("location"), j.get("isRemote"),
                j.get("jobUrl"), [j["departmentName"]] if j.get("departmentName") else [],
                None, j.get("publishedAt"), j.get("descriptionPlain"),
                config=config,
            )
            for j in data.get("jobs", [])
        ]
    if platform == "smartrecruiters":
        return [
            posting(
                "smartrecruiters", j.get("name"), company,
                ", ".join(filter(None, [
                    (j.get("location") or {}).get("city"), (j.get("location") or {}).get("country"),
                ])) or None,
                (j.get("location") or {}).get("remote"),
                j.get("postingUrl") or f"https://jobs.smartrecruiters.com/{company}/{j.get('id')}",
                [(j.get("department") or {}).get("label")] if (j.get("department") or {}).get("label") else [],
                None, j.get("releasedDate"), None,
                config=config,
            )
            for j in data.get("content", [])
        ]
    if platform == "recruitee":
        return [
            posting(
                "recruitee", j.get("title"), company,
                j.get("location") or ", ".join(filter(None, [j.get("city"), j.get("country")])) or None,
                j.get("remote"), j.get("careers_url"),
                [(j.get("department") or {}).get("name")] if isinstance(j.get("department"), dict)
                else ([j["department"]] if j.get("department") else []),
                None, j.get("created_at") or j.get("published_at"), j.get("description"),
                config=config,
            )
            for j in data.get("offers", [])
        ]
    # workable
    return [
        posting(
            "workable", j.get("title"), company, workable_location(j),
            j.get("telecommute") or str(j.get("telecommuting")).lower() == "true",
            j.get("url") or j.get("shortlink"),
            [j.get("department")] if j.get("department") else [],
            None, j.get("published_on"), j.get("description"),
            config=config,
        )
        for j in data.get("jobs", [])
    ]



def greenhouse_location(job):
    """Greenhouse's `location.name` is free text; some boards (Cloudflare) put the work style
    there ("Hybrid") and the real city only in `offices`. Join both so London isn't lost."""
    names = [(job.get("location") or {}).get("name")]
    names += [office.get("location") or office.get("name") for office in job.get("offices") or []]
    return "; ".join(dict.fromkeys(n for n in names if n)) or None


def workable_location(job):
    """Workable's widget API puts city/country at the top level plus a `locations` list for
    multi-site roles; older payloads nest them under `location`. Join every site so a London
    secondary location isn't lost."""
    nested = job.get("location") or {}
    if nested.get("location_str"):
        return nested["location_str"]
    sites = [job] + [loc for loc in job.get("locations") or [] if isinstance(loc, dict)]
    if nested:
        sites.insert(0, nested)
    names = [", ".join(filter(None, [site.get("city"), site.get("country")])) for site in sites]
    return "; ".join(dict.fromkeys(n for n in names if n)) or None


def fetch_ats_postings(platform, slug, query=None, config=None):
    """Fetch + parse one (platform, slug) pair. Returns (results, error) — never raises, same
    reliability contract as http_get_json: a bad slug or dead endpoint degrades to
    (results=[], error="..."), never a stack trace."""
    config = config or DEFAULT_FETCH
    url = ATS_ENDPOINTS[platform].format(slug=slug)
    data, err = http_get_json(url, config=config)
    if err:
        return [], err
    raw = parse_ats_payload(platform, slug, data, config=config)
    if query:
        q = query.lower()
        raw = [r for r in raw if q in (r["title"] or "").lower()]
    return raw, None


def cmd_search_ats(args):
    results, err = fetch_ats_postings(args.platform, args.company, args.query)
    if err:
        print_search_result(args.platform, [], err, {"company": args.company})
        return
    print_search_result(args.platform, results[: args.limit], None, {"company": args.company})


def candidate_slugs(name, slug_hint=None):
    """Generate a small, ordered, deduped list of plausible ATS slugs for a company name —
    concatenated/hyphenated forms, with and without common legal suffixes stripped. Capped at 4
    to bound the number of probe requests discover-ats makes.

    A name containing a literal "." also gets one more candidate: the name lowercased with
    whitespace stripped but internal punctuation kept (so "Monday.com" -> "monday.com"). Some
    companies -- monday.com's Ashby board is a confirmed live example -- use their bare domain
    as the ATS slug verbatim, which the alphanumeric-only guesses below can never produce."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    trimmed = [w for w in words if w not in ATS_SLUG_SUFFIXES] or words

    candidates = []
    if slug_hint:
        candidates.append(slug_hint.strip().lower())
    if "." in name:
        dotted = re.sub(r"[^a-z0-9.-]", "", re.sub(r"\s+", "", name.lower()))
        candidates.append(dotted)
    if trimmed:
        candidates.append("".join(trimmed))
        candidates.append("-".join(trimmed))
    if trimmed != words:
        candidates.append("".join(words))
    if trimmed:
        candidates.append(trimmed[0])

    seen, out = set(), []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out[:4]


def cmd_search_discover_ats(args):
    platforms = (
        [p.strip() for p in args.platforms.split(",") if p.strip() in ATS_ENDPOINTS]
        if args.platforms else ATS_PROBE_ORDER
    )
    chosen, confidence, attempts = discover_ats(args.company, args.slug_hint, platforms, args.query)
    if chosen is None:
        print_search_result("discover-ats", [], None, {
            "company": args.company, "detected_platform": None, "detected_slug": None,
            "confidence": "none", "candidates_tried": attempts,
        })
        return

    platform, slug, results = chosen
    print_search_result("discover-ats", results[: args.limit], None, {
        "company": args.company, "detected_platform": platform, "detected_slug": slug,
        "confidence": confidence, "candidates_tried": attempts,
    })


def discover_ats(company, slug_hint=None, platforms=None, query=None):
    """Probe candidate slugs across ATS platforms. Returns ((platform, slug, results) or None,
    confidence "high"/"low"/"none", attempts). High = a board with postings; low = a valid
    board with zero postings (could be a different, empty company using that slug)."""
    platforms = platforms or ATS_PROBE_ORDER
    slugs = candidate_slugs(company, slug_hint)

    attempts = []
    best = None      # (platform, slug, results) — non-empty results, high confidence
    fallback = None  # (platform, slug, results) — valid-looking board, zero postings, low confidence

    for slug in slugs:
        for platform in platforms:
            results, err = fetch_ats_postings(platform, slug, query)
            attempts.append({
                "platform": platform, "slug": slug, "error": err,
                "results_count": None if err else len(results),
            })
            if err:
                continue
            if results:
                best = (platform, slug, results)
                break
            elif fallback is None:
                fallback = (platform, slug, results)
        if best:
            break

    chosen = best or fallback
    confidence = "high" if best else ("low" if fallback else "none")
    return chosen, confidence, attempts
