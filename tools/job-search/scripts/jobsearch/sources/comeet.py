"""Comeet career-page discovery and positions API."""

import re
import urllib.parse

from jobsearch.fetchconfig import DEFAULT as DEFAULT_FETCH
from jobsearch.http import http_get_html, http_get_json
from jobsearch.sources.common import posting, print_search_result

COMEET_TOKEN_RE = re.compile(r'"token"\s*:\s*"([0-9A-Za-z]{16,40})"')
COMEET_COMPANY_UID_RE = re.compile(r'"company-uid"\s*:\s*"([0-9A-Za-z.]+)"')
COMEET_POSITIONS_URL = (
    "https://www.comeet.co/careers-api/2.0/company/{company_uid}/positions?token={token}&details=true"
)

def detect_comeet_config(html):
    """Find a Comeet-hosted career page's public token + company-uid from its own HTML (the
    inline `COMEET.init({...})` call every Comeet embed includes). Returns a dict with `token`
    and `company_uid`, or None if neither is present. If a page happens to embed more than one
    distinct token/company-uid pair (unusual), the first of each is used -- good enough for the
    single-widget-per-page case this exists to handle; a page defying that gets a wrong-but-safe
    "none" outcome from fetch_comeet_postings's own error handling downstream, never a crash."""
    token_match = COMEET_TOKEN_RE.search(html)
    uid_match = COMEET_COMPANY_UID_RE.search(html)
    if not token_match or not uid_match:
        return None
    return {"token": token_match.group(1), "company_uid": uid_match.group(1)}


def fetch_comeet_postings(token, company_uid, company=None, query=None, limit=25, config=None):
    """Fetch a Comeet-hosted company's full current posting list in one request -- unlike
    Workday, Comeet's positions endpoint already returns every field needed (location, department,
    employment type, apply URL, last-updated timestamp) inline, so no per-posting detail fetch or
    pagination loop is needed here. Returns (results, error): a company genuinely having zero
    current openings is not an error, same contract as every other `search` source."""
    config = config or DEFAULT_FETCH
    url = COMEET_POSITIONS_URL.format(company_uid=urllib.parse.quote(company_uid, safe=""), token=token)
    data, err = http_get_json(url, config=config)
    if err:
        return [], err
    if not isinstance(data, list):
        return [], f"unexpected response shape from {url}"

    if query:
        q = query.lower()
        data = [p for p in data if q in (p.get("name") or "").lower()]

    results = []
    for p in data[:limit]:
        loc = p.get("location") or {}
        location_parts = [part for part in [loc.get("city"), loc.get("state"), loc.get("name")] if part]
        results.append(posting(
            "comeet",
            p.get("name"),
            company or p.get("company_name"),
            ", ".join(dict.fromkeys(location_parts)) or None,  # dedupe city==name etc. while keeping order
            bool(loc.get("is_remote")),
            p.get("url_active_page") or p.get("url_comeet_hosted_page") or p.get("position_url"),
            [p["department"]] if p.get("department") else [],
            None,
            p.get("time_updated"),
            " ".join(d.get("value") or "" for d in p.get("details") or []) or None,
            config=config,
        ))
    return results, None


def cmd_search_discover_comeet(args):
    """Detect a company's Comeet token/company-uid from a career-page URL and, if found,
    immediately fetch its full posting list -- the free, keyless equivalent of
    `search discover-ats`/`search discover-workday` for Comeet-hosted companies."""
    html, fetch_err = http_get_html(args.url)
    if fetch_err:
        print_search_result("discover-comeet", [], fetch_err, {
            "company": args.company, "detected_platform": None, "detected_slug": None,
            "confidence": "none",
        })
        return

    config = detect_comeet_config(html)
    if config is None:
        print_search_result("discover-comeet", [], None, {
            "company": args.company, "detected_platform": None, "detected_slug": None,
            "confidence": "none",
        })
        return

    slug = f"{config['token']}:{config['company_uid']}"
    results, err = fetch_comeet_postings(config["token"], config["company_uid"], args.company, args.query, args.limit)
    if err:
        print_search_result("discover-comeet", [], err, {
            "company": args.company, "detected_platform": "comeet", "detected_slug": slug,
            "confidence": "low",
        })
        return

    print_search_result("discover-comeet", results, None, {
        "company": args.company, "detected_platform": "comeet", "detected_slug": slug,
        "confidence": "high" if results else "low",
    })


def cmd_search_comeet_jobs(args):
    """Direct fetch for a Comeet token/company-uid already known (e.g. saved to target_companies
    by a prior `discover-comeet` call) -- skips the career-page HTML fetch entirely."""
    try:
        token, company_uid = args.slug.split(":")
    except ValueError:
        print_search_result("comeet-jobs", [], f"--slug must be '<token>:<company_uid>', got: {args.slug!r}")
        return

    results, err = fetch_comeet_postings(token, company_uid, args.company, args.query, args.limit)
    print_search_result("comeet-jobs", results, err)
