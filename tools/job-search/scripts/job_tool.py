#!/usr/bin/env python3
"""
Job-search bookkeeping: personalization profile + application tracker.
JSON files are the source of truth; the tracker markdown is a generated view —
always mutate state through this script, never hand-edit the .md or .json.

Usage:
  job_tool.py profile show
  job_tool.py profile set '<json patch>'          (or '-' to read patch from stdin)
  job_tool.py tracker list [--status STATUS] [--stale-only]
  job_tool.py tracker upsert '<json row>'         (or '-' to read row from stdin)
  job_tool.py tracker render
  job_tool.py search remotive --query "backend" [--category X] [--limit 25]
  job_tool.py search arbeitnow --query "backend" [--limit 25] [--max-pages 3]
  job_tool.py search ats --platform greenhouse|lever|ashby|smartrecruiters|recruitee|workable \
      --company <slug> [--query X] [--limit 25]
  job_tool.py search discover-ats --company "<company name>" [--slug-hint <slug>] \
      [--platforms a,b,c] [--query X] [--limit 25]
  job_tool.py search linkedin --query "backend" --location "Remote" [--jobage 7] [--remote remote|hybrid|onsite] [--limit 25]
  job_tool.py search linkedin-detail --id <job-id|job-url>
  job_tool.py search discover-workday --url <career-page or myworkdayjobs.com URL> [--company X] [--query Y] [--limit 25]
  job_tool.py search workday-jobs --slug <tenant>/<wd_host>/<site> [--company X] [--query Y] [--limit 25]
  job_tool.py search workday --url <company myworkdayjobs.com URL> [--query X] [--location Y] [--limit 25]
  job_tool.py search discover-comeet --url <career-page URL> [--company X] [--query Y] [--limit 25]
  job_tool.py search comeet-jobs --slug <token>:<company_uid> [--company X] [--query Y] [--limit 25]
  job_tool.py search jobs-index [--company X] [--domain Y] [--query Z] [--location "City, Region, Country"] \
      [--ats workday,oraclecloud,comeet,...] [--work-arrangement "Remote OK"|"Remote Solely"|Hybrid|On-site] \
      [--time-range 1h|24h|7d|6m] [--limit 25]
  job_tool.py network import --csv "<path to LinkedIn Connections.csv>"
  job_tool.py network list [--company "<name>"]
  job_tool.py network match [--company "<name>"]
  job_tool.py network companies

State lives in ~/Desktop/Job-Search/ by default (override with JOB_SEARCH_DIR env var):
  profile.json          - target role/location/industry/seniority/preferences
  tracker.json          - application rows (source of truth)
  Tracker.md            - rendered markdown view of tracker.json
  connections.json      - imported LinkedIn connections (see `network` commands below)

The `network` group has nothing to do with job postings — it cross-references a LinkedIn
connections export against `profile.json`'s `target_companies` watchlist to surface warm-intro
contacts. `network import` reads a `Connections.csv` from LinkedIn's own official data export
(Settings & Privacy > Data Privacy > "Get a copy of your data") — no scraping, no session cookie,
no API key. `network match` does the actual company matching; `network list` is for general
browsing; `network companies` summarizes the whole imported set grouped by company so it's
scannable even with 1000+ connections. See tools/job-search/SKILL.md's "Network — warm intros"
section.

The `search` group hits public, keyless JSON APIs directly (no scraping, no MCP) and always
prints a JSON object with a "results" list — a fetch failure for one source (network policy,
outage, unknown company slug) is reported as an "error" string with an empty "results" list,
never a stack trace, so a caller can fall back to another source without the whole run failing.
`search discover-workday`/`search workday-jobs` are also keyless — they read a career page's own
HTML to find its Workday tenant, then query Workday's own CXS JSON API directly. `search workday`
(the paid Apify Actor) is a fallback for the rare case where a company's career page never links
to its myworkdayjobs.com tenant anywhere in static HTML, so discover-workday can't find it either.
`search jobs-index` is a second, broader paid source: a pre-built index of 175k+ company career
sites across 54 ATS platforms (Workday, Comeet, Oracle Cloud, SuccessFactors, iCIMS, Phenom
People, and others this script has no free/dedicated integration for and likely never will). Reach
for it once a company matches none of the free discover-ats/discover-workday/discover-comeet paths
— it very likely still covers them, since its platform list is much wider than the handful this
script talks to directly. Both paid sources are off by default until APIFY_TOKEN is set, and both
degrade like any other source (error + no results) rather than raising if it isn't.

`search discover-comeet`/`search comeet-jobs` follow the identical pattern for Comeet-hosted
career pages: read the career page's own HTML for its inline `COMEET.init({"token": ...,
"company-uid": ...})` widget config (both values are public — visible to any site visitor via
view-source, since Comeet's own client-side JS uses them the same way), then query Comeet's
public positions API directly. Unlike Workday, Comeet's endpoint returns every posting's full
detail (location, department, apply URL) in a single response — no per-posting detail fetch or
pagination needed.

`search discover-ats` is the one exception to "always error or results": since a company simply
not being on any of the six supported ATS platforms is a normal outcome, not a failure, it never
sets "error" — instead it reports a "confidence" of "high" (postings found), "low" (an endpoint
resolved without error but returned zero postings — some platforms don't 404 on unknown slugs, so
this is a guess, not a confirmed match), or "none" (nothing resolved on any platform/slug tried).
`search discover-workday` and `search discover-comeet` both follow the same "confidence" contract
for the same reason (not being hosted on that platform at all is a normal outcome, not a failure):
"high" (a tenant/config was found and it has current postings), "low" (found, zero postings right
now), "none" (no matching link/widget config anywhere in the career page's HTML — for Workday, try
the paid `search workday` Actor or Playwright next; for Comeet, there's no equivalent paid
fallback yet, go to WebSearch/WebFetch/Playwright per references/search-fallbacks.md).

The `linkedin` and `linkedin-detail` sources hit LinkedIn's public jobs-guest endpoints directly
(no auth, no API key). Automated access to these pages is against LinkedIn's Terms of Service —
personal use only, keep query volume low, never bulk or commercial use.

The `workday` source runs a paid Apify Actor (Workday has no keyless API) to cover large
enterprises that WebFetch/Playwright often can't reach. Requires an APIFY_TOKEN env var — with
no token set, it degrades the same way any other source degrades on failure: an "error" string
and empty "results", never a stack trace. See tools/job-search/README.md for setup and cost.
"""

import csv
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

HTTP_TIMEOUT = 15
USER_AGENT = "job-search-skill/1.2 (+https://github.com/Yoavsb25/claude-code-tools)"
APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_DEFAULT_WORKDAY_ACTOR = "automation-lab/workday-jobs-scraper"
APIFY_DEFAULT_JOBS_INDEX_ACTOR = "fantastic-jobs/career-site-job-listing-api"
APIFY_TIMEOUT = 90  # actor runs are synchronous and can take much longer than a plain GET
# Kept deliberately small: at Apify's FREE pricing tier this Actor is ~$0.012/job + a flat
# $0.01 Actor-Start charge, so a --limit 25 call costs well under $1. Callers can raise --limit
# explicitly for a deliberate deeper pull, but the default should never surprise anyone's bill.
JOBS_INDEX_DEFAULT_LIMIT = 25
# "6m" = Apify's backfill window (effectively "every currently active posting"), matching the
# "pull the full board, filter yourself" philosophy the free discover-ats/workday/comeet paths
# already use. Market-wide freshness scans (Stage 2b) should override this to "24h"/"7d" instead.
JOBS_INDEX_DEFAULT_TIME_RANGE = "6m"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ATS_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
}
LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
LINKEDIN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
LINKEDIN_MAX_RETRIES = 6
LINKEDIN_BACKOFF_BASE_MS = 500
LINKEDIN_BACKOFF_CAP_MS = 8000
# Platforms ATS_ENDPOINTS deliberately does NOT support: Workday has no universal keyless GET
# endpoint (tenant-specific wd{N} subdomain + variable site-name path, and the real job-data call
# is a POST with a JSON body, not a GET like every platform below). It's reachable for free via
# `search discover-workday`/`search workday-jobs` below (tenant auto-detected from a career page's
# own HTML, then queried directly against Workday's own CXS JSON API — no scraping, no paid Actor).
# `search workday` (the paid Apify Actor) remains as a fallback for the rare case where a company's
# career page never links to its myworkdayjobs.com tenant in static HTML.
ATS_PROBE_ORDER = ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable"]
# Matches a Workday-hosted career site's own URL, e.g.
# https://unitytech.wd1.myworkdayjobs.com/Unity/job/...
# or   https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/...
# Group 1 = tenant, group 2 = wd-host, group 3 = the first path segment, group 4 = the second path
# segment if present. Some tenants (NVIDIA, confirmed by hand) nest the site under a locale prefix
# like "en-US" -- the *locale* is NOT part of the CXS API path, only the site name after it is
# (verified directly: /wday/cxs/nvidia/en-US/jobs 404s, /wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs
# works). detect_workday_tenant() below resolves which of group 3 / group 4 is the real site name.
WORKDAY_URL_RE = re.compile(
    r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/\"'?#\s]+)(?:/([^/\"'?#\s]+))?", re.I
)
WORKDAY_LOCALE_RE = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.I)
# Comeet-hosted career pages embed a small inline `COMEET.init({"token": "...", "company-uid":
# "...", ...})` call to configure their JS widget -- both values are public (visible to any site
# visitor via view-source, since the widget's own client-side JS uses them directly), so treating
# them as a public tenant identifier (like Workday's tenant/site) rather than a secret is correct.
# Verified directly: GET https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={token}
# returns the company's full current posting list as a single JSON array, no auth/session needed.
COMEET_TOKEN_RE = re.compile(r'"token"\s*:\s*"([0-9A-Za-z]{16,40})"')
COMEET_COMPANY_UID_RE = re.compile(r'"company-uid"\s*:\s*"([0-9A-Za-z.]+)"')
COMEET_POSITIONS_URL = "https://www.comeet.co/careers-api/2.0/company/{company_uid}/positions?token={token}"
WORKDAY_PAGE_SIZE = 20  # Workday's CXS search endpoint rejects larger page sizes with HTTP 400
WORKDAY_MAX_JOBS_SCANNED = 150  # safety cap on per-posting detail fetches for one company
# Safety cap on pagination alone when a --location-hint narrows the (expensive) detail-fetch
# stage separately -- see fetch_workday_postings. Pagination is cheap (compact JSON, no detail
# fetch), so this can afford to be much higher than WORKDAY_MAX_JOBS_SCANNED -- large enough to
# cover NVIDIA's entire ~2,000-posting board (verified live) in one call.
WORKDAY_PAGINATION_CAP = 3000
WORKDAY_DETAIL_WORKERS = 8  # concurrency for the detail-fetch fan-out -- keep polite, not zero
ATS_SLUG_SUFFIXES = {
    "inc", "llc", "ltd", "corp", "corporation", "co", "company",
    "group", "technologies", "technology", "labs", "software", "systems",
}

STATUS_ORDER = [
    "Shortlisted", "Applied", "Phone Screen", "Interviewing",
    "Offer", "Rejected", "Withdrawn",
]
SHORTLIST_STALE_DAYS = 10
DEFAULT_FOLLOWUP_DAYS = 14
INTERVIEW_FOLLOWUP_DAYS = 7

TRACKER_COLUMNS = [
    ("company", "Company"), ("role", "Role"), ("status", "Status"),
    ("fit", "Fit"), ("salary", "Salary"), ("found_date", "Found"), ("applied_date", "Applied"),
    ("followup_date", "Follow-up"), ("resume_path", "Resume"),
    ("link", "Link"), ("notes", "Notes"),
]


def state_dir():
    d = Path(os.environ.get("JOB_SEARCH_DIR", "~/Desktop/Job-Search")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, path)


def read_json_arg(arg):
    raw = sys.stdin.read() if arg == "-" else arg
    return json.loads(raw)


def today_str():
    return date.today().isoformat()


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---- profile --------------------------------------------------------------

def profile_path():
    return state_dir() / "profile.json"


def cmd_profile_show(_args):
    profile = load_json(profile_path(), {})
    print(json.dumps(profile, indent=2))


def cmd_profile_set(args):
    patch = read_json_arg(args.patch)
    profile = load_json(profile_path(), {})
    profile.update(patch)
    profile["updated"] = today_str()
    save_json(profile_path(), profile)
    print(json.dumps(profile, indent=2))


# ---- tracker ----------------------------------------------------------------

def tracker_path():
    return state_dir() / "tracker.json"


def markdown_path():
    return state_dir() / "Tracker.md"


def load_rows():
    return load_json(tracker_path(), {"next_id": 1, "rows": []})


def save_rows(data):
    save_json(tracker_path(), data)
    render_markdown(data)


def next_followup(status, applied_date_str, prev_followup_str):
    if status == "Applied":
        base = parse_date(applied_date_str) or date.today()
        return (base + timedelta(days=DEFAULT_FOLLOWUP_DAYS)).isoformat()
    if status in ("Phone Screen", "Interviewing"):
        return (date.today() + timedelta(days=INTERVIEW_FOLLOWUP_DAYS)).isoformat()
    return prev_followup_str


def compute_stale_reason(row):
    status = row.get("status")
    today = date.today()

    if status == "Shortlisted":
        found = parse_date(row.get("found_date"))
        if found and (today - found).days >= SHORTLIST_STALE_DAYS:
            return f"Still shortlisted after {(today - found).days} days — decide or drop"

    if status in ("Applied", "Phone Screen", "Interviewing"):
        followup = parse_date(row.get("followup_date"))
        if followup and today >= followup:
            return f"Follow-up was due {row['followup_date']} — no status change logged since"

    return None


def cmd_tracker_upsert(args):
    patch = read_json_arg(args.row)
    data = load_rows()
    rows = data["rows"]

    match = None
    if patch.get("id"):
        match = next((r for r in rows if r["id"] == patch["id"]), None)
    if match is None and patch.get("company") and patch.get("role"):
        key = (normalize_company(patch["company"]), patch["role"].strip().lower())
        match = next(
            (
                r for r in rows
                if (normalize_company(r["company"]), r["role"].strip().lower()) == key
            ),
            None,
        )

    if match is None:
        if not patch.get("company") or not patch.get("role"):
            print("error: new rows require both 'company' and 'role'", file=sys.stderr)
            sys.exit(1)
        row = {
            "id": data["next_id"], "company": patch["company"], "role": patch["role"],
            "status": "Shortlisted", "fit": None, "salary": None, "found_date": today_str(),
            "applied_date": None, "followup_date": None, "resume_path": None,
            "link": None, "notes": None,
        }
        data["next_id"] += 1
        rows.append(row)
    else:
        row = match

    for k, v in patch.items():
        if k == "id":
            continue
        row[k] = v

    if "status" in patch:
        if patch["status"] == "Applied" and not row.get("applied_date"):
            row["applied_date"] = today_str()
        if "followup_date" not in patch:
            row["followup_date"] = next_followup(row["status"], row.get("applied_date"), row.get("followup_date"))

    save_rows(data)
    print(json.dumps(row, indent=2))


def cmd_tracker_list(args):
    data = load_rows()
    rows = data["rows"]
    for row in rows:
        row["stale_reason"] = compute_stale_reason(row)
    if args.status:
        rows = [r for r in rows if r["status"].lower() == args.status.lower()]
    if args.stale_only:
        rows = [r for r in rows if r["stale_reason"]]
    print(json.dumps(rows, indent=2))


def render_markdown(data):
    rows = data["rows"]
    lines = ["# Job Search Tracker", ""]
    lines.append("| " + " | ".join(h for _, h in TRACKER_COLUMNS) + " |")
    lines.append("|" + "|".join("---" for _ in TRACKER_COLUMNS) + "|")

    status_rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    for row in sorted(rows, key=lambda r: (status_rank.get(r["status"], 99), r.get("company", ""))):
        cells = []
        for key, _ in TRACKER_COLUMNS:
            val = row.get(key)
            if key == "resume_path" and val:
                val = f"[{Path(val).name}]({val})"
            elif key == "link" and val:
                val = f"[JD]({val})"
            cells.append(str(val) if val not in (None, "") else "—")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    stale = [r for r in rows if compute_stale_reason(r)]
    if stale:
        lines.append("## Needs attention")
        lines.append("")
        for row in stale:
            lines.append(f"- **{row['company']} — {row['role']}**: {compute_stale_reason(row)}")
        lines.append("")

    markdown_path().write_text("\n".join(lines), encoding="utf-8")


def cmd_tracker_render(_args):
    data = load_rows()
    render_markdown(data)
    print(str(markdown_path()))


# ---- network (LinkedIn connections / warm intros) ---------------------------

def connections_path():
    return state_dir() / "connections.json"


def load_connections():
    return load_json(connections_path(), {"connections": [], "last_imported": None, "source_file": None})


def save_connections(data):
    save_json(connections_path(), data)


def parse_linkedin_connections_csv(path):
    """LinkedIn's export prepends a few 'Notes:' preamble lines before the real header row.
    Scan for the line that actually starts the CSV data ('First Name,Last Name,...') and parse
    from there. Column keys are lowercased/stripped defensively since LinkedIn has varied exact
    column names/casing across export versions — missing columns (e.g. no URL/Email in an older
    export) degrade to blank fields rather than crashing."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()

    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().lower().startswith("first name,last name")),
        None,
    )
    if header_idx is None:
        return None, "couldn't find a 'First Name,Last Name,...' header row — is this a LinkedIn Connections.csv export?"

    reader = csv.DictReader(io.StringIO("".join(lines[header_idx:])))
    records = []
    for row in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        first, last = norm.get("first name", ""), norm.get("last name", "")
        if not first and not last:
            continue  # trailing blank line
        records.append({
            "first_name": first,
            "last_name": last,
            "company": norm.get("company", ""),
            "position": norm.get("position", ""),
            "connected_on": norm.get("connected on", ""),
            "url": norm.get("url") or norm.get("profile url") or None,
            "email": norm.get("email address") or None,
        })
    return records, None


def connection_key(rec):
    if rec.get("url"):
        return ("url", rec["url"].strip().lower().rstrip("/"))
    return ("name", f"{rec['first_name'].strip().lower()} {rec['last_name'].strip().lower()}")


def cmd_network_import(args):
    path = Path(args.csv).expanduser()
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    new_records, err = parse_linkedin_connections_csv(path)
    if err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)

    data = load_connections()
    existing = data["connections"]
    index = {connection_key(r): i for i, r in enumerate(existing)}

    added = updated = unchanged = 0
    for rec in new_records:
        key = connection_key(rec)
        if key in index:
            i = index[key]
            if any(existing[i].get(k) != v for k, v in rec.items()):
                existing[i].update(rec)
                updated += 1
            else:
                unchanged += 1
        else:
            existing.append(rec)
            index[key] = len(existing) - 1
            added += 1

    data["last_imported"] = today_str()
    data["source_file"] = str(path)
    save_connections(data)

    print(json.dumps({
        "imported_from": str(path), "added": added, "updated": updated,
        "unchanged": unchanged, "total_connections": len(existing),
    }, indent=2))


def normalize_company(name):
    """Lowercase, strip punctuation, drop common legal-suffix words (the same ATS_SLUG_SUFFIXES
    set used for ATS slug-guessing) — for comparing a connection's Company field against a
    target_companies watchlist entry."""
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    trimmed = [w for w in words if w not in ATS_SLUG_SUFFIXES]
    return trimmed or words


def company_words_match(target_words, company_words):
    """Whole-word prefix match, not raw substring: 'Google' (['google']) matches 'Google Ireland
    Limited' (['google','ireland','limited']) since it's a word-level prefix, while rejecting
    unrelated names that would false-positive under substring matching (e.g. 'Meta' vs
    'Metabase', 'Google' vs 'DeepMind'). Suffix-stripping in normalize_company already handles
    'Inc' vs 'LLC' variants collapsing to the same token list."""
    if not target_words or not company_words:
        return False
    return company_words[: len(target_words)] == target_words


def cmd_network_list(args):
    data = load_connections()
    rows = data["connections"]
    if args.company:
        needle = normalize_company(args.company)
        rows = [r for r in rows if needle and company_words_match(needle, normalize_company(r.get("company") or ""))]
    rows = sorted(rows, key=lambda r: (r.get("company") or "", r.get("last_name") or ""))
    print(json.dumps({"count": len(rows), "connections": rows}, indent=2))


def cmd_network_match(args):
    data = load_connections()
    conns = data["connections"]

    if args.company:
        targets = [{"name": args.company}]
    else:
        profile = load_json(profile_path(), {})
        targets = profile.get("target_companies") or []
        if not targets:
            print(json.dumps({
                "error": "no target_companies set in profile — run 'profile set', or pass "
                         "'network match --company <name>' to check one company ad hoc",
                "results": [],
            }, indent=2))
            return

    results = []
    for t in targets:
        t_words = normalize_company(t.get("name") or "")
        matches = []
        for c in conns:
            company = c.get("company") or ""
            if not company.strip():
                continue
            if company_words_match(t_words, normalize_company(company)):
                matches.append({
                    "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                    "position": c.get("position") or None,
                    "company": company,
                    "connected_on": c.get("connected_on") or None,
                    "url": c.get("url"),
                })
        results.append({"target_company": t.get("name"), "match_count": len(matches), "connections": matches})

    print(json.dumps({
        "target_companies_checked": len(targets),
        "results": results,
        "no_match_companies": [r["target_company"] for r in results if r["match_count"] == 0],
        "total_connections_loaded": len(conns),
    }, indent=2))


def cmd_network_companies(_args):
    data = load_connections()
    conns = data["connections"]

    groups = {}  # normalized-company tuple -> {"display": str, "count": int}
    no_company = 0
    for c in conns:
        company = (c.get("company") or "").strip()
        if not company:
            no_company += 1
            continue
        key = tuple(normalize_company(company))
        group = groups.setdefault(key, {"display": company, "count": 0})
        group["count"] += 1
        # Prefer the shortest original spelling as the display name (e.g. "SysAid" over
        # "SysAid Inc") since it's usually the cleanest form of the same company.
        if len(company) < len(group["display"]):
            group["display"] = company

    bucket_3plus, bucket_2, bucket_1 = [], [], []
    for group in groups.values():
        entry = {"company": group["display"], "count": group["count"]}
        if group["count"] >= 3:
            bucket_3plus.append(entry)
        elif group["count"] == 2:
            bucket_2.append(entry)
        else:
            bucket_1.append(entry)

    for bucket in (bucket_3plus, bucket_2, bucket_1):
        bucket.sort(key=lambda e: e["company"].lower())

    print(json.dumps({
        "total_connections": len(conns),
        "unique_companies": len(groups),
        "no_company_listed": no_company,
        "buckets": [
            {"label": "3+ connections", "companies": bucket_3plus},
            {"label": "2 connections", "companies": bucket_2},
            {"label": "1 connection", "companies": bucket_1},
        ],
    }, indent=2))


# ---- search -----------------------------------------------------------------

def strip_html(text):
    if not text:
        return text
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def decode_html_entities(text):
    if not text:
        return text

    def numeric_entity(code_point):
        return chr(code_point) if 0 <= code_point <= 0x10FFFF else ""

    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    text = re.sub(r"&#(\d+);", lambda m: numeric_entity(int(m.group(1))), text)
    text = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: numeric_entity(int(m.group(1), 16)), text)
    text = text.replace("&nbsp;", " ")
    return text


def clean_text(html):
    if not html:
        return html
    return decode_html_entities(strip_html(html))


def jobage_to_tpr(days):
    if not days or days <= 0 or days >= 9999:
        return None
    return f"r{days * 86400}"


def linkedin_work_type_flag(mode):
    return {"remote": "2", "hybrid": "3", "onsite": "1"}.get((mode or "").lower())


def normalize_linkedin_job_id(value):
    if not value:
        return None
    urn_match = re.search(r"urn:li:jobPosting:(\d+)", value)
    if urn_match:
        return urn_match.group(1)
    url_match = re.search(r"-(\d{6,})(?:\?|$)", value) or re.search(r"/(\d{6,})(?:\?|$)", value)
    if url_match:
        return url_match.group(1)
    if re.fullmatch(r"\d{6,}", value):
        return value
    return None


LINKEDIN_CARD_SPLIT_RE = re.compile(r'data-entity-urn="urn:li:jobPosting:')
LINKEDIN_ID_PREFIX_RE = re.compile(r"^(\d+)")
LINKEDIN_FULL_LINK_RE = re.compile(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', re.IGNORECASE)
LINKEDIN_TITLE_H3_RE = re.compile(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', re.IGNORECASE)
LINKEDIN_TITLE_SR_RE = re.compile(r'class="sr-only"[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
LINKEDIN_SUBTITLE_RE = re.compile(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', re.IGNORECASE)
LINKEDIN_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
LINKEDIN_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
LINKEDIN_LISTDATE_RE = re.compile(
    r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', re.IGNORECASE
)


def parse_linkedin_cards(html):
    results = []
    chunks = LINKEDIN_CARD_SPLIT_RE.split(html)[1:]

    for chunk in chunks:
        id_match = LINKEDIN_ID_PREFIX_RE.match(chunk)
        if not id_match:
            continue
        job_id = id_match.group(1)

        link_match = LINKEDIN_FULL_LINK_RE.search(chunk)
        url = decode_html_entities(link_match.group(1)).split("?")[0] if link_match else ""

        title = None
        h3_match = LINKEDIN_TITLE_H3_RE.search(chunk)
        if h3_match:
            title = clean_text(h3_match.group(1)) or None
        if not title:
            sr_match = LINKEDIN_TITLE_SR_RE.search(chunk)
            if sr_match:
                title = clean_text(sr_match.group(1)) or None
        if not title:
            continue

        company = None
        sub_match = LINKEDIN_SUBTITLE_RE.search(chunk)
        if sub_match:
            company_link = LINKEDIN_HREF_RE.search(sub_match.group(1))
            company_url = (
                decode_html_entities(company_link.group(1)).split("?")[0] if company_link else None
            )
            company = clean_text(sub_match.group(1)) or None
        else:
            company_url = None

        loc_match = LINKEDIN_LOCATION_RE.search(chunk)
        location = clean_text(loc_match.group(1)) if loc_match else None
        location = location or None

        date_match = LINKEDIN_LISTDATE_RE.search(chunk)
        posted_date = date_match.group(1) if date_match else None

        results.append({
            "id": job_id,
            "title": title,
            "company": company,
            "company_url": company_url,
            "location": location,
            "posted_date": posted_date,
            "url": url or f"https://www.linkedin.com/jobs/view/{job_id}",
        })

    return results


LINKEDIN_TOPCARD_TITLE_RE = re.compile(
    r'class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)</h[12]>', re.IGNORECASE
)
LINKEDIN_ORG_RE = re.compile(
    r'class="topcard__org-name-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', re.IGNORECASE
)
LINKEDIN_LOC_DETAIL_RE = re.compile(
    r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', re.IGNORECASE
)
LINKEDIN_DESC_RE = re.compile(
    r'class="(?:show-more-less-html__markup|description__text[^"]*)"[^>]*>([\s\S]*?)</div>',
    re.IGNORECASE,
)
LINKEDIN_BR_RE = re.compile(r"<\s*br\s*/?>", re.IGNORECASE)
LINKEDIN_BLOCK_CLOSE_RE = re.compile(r"</(p|li|ul|ol|div|h\d)>", re.IGNORECASE)
LINKEDIN_CRITERIA_RE = re.compile(
    r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?'
    r'class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>',
    re.IGNORECASE,
)
LINKEDIN_APPLY_RE = re.compile(r'class="topcard__link[^"]*"[^>]*href="([^"]+)"', re.IGNORECASE)


def _strip_tags_keep_newlines(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def parse_linkedin_detail(html, job_id):
    title_match = LINKEDIN_TOPCARD_TITLE_RE.search(html)
    title = clean_text(title_match.group(1)) if title_match else None

    org_match = LINKEDIN_ORG_RE.search(html)
    company = clean_text(org_match.group(2)) or None if org_match else None
    company_url = decode_html_entities(org_match.group(1)).split("?")[0] if org_match else None

    loc_match = LINKEDIN_LOC_DETAIL_RE.search(html)
    location = (clean_text(loc_match.group(1)) or None) if loc_match else None

    description = None
    desc_match = LINKEDIN_DESC_RE.search(html)
    if desc_match:
        with_breaks = LINKEDIN_BR_RE.sub("\n", desc_match.group(1))
        with_breaks = LINKEDIN_BLOCK_CLOSE_RE.sub("\n", with_breaks)
        text = decode_html_entities(_strip_tags_keep_newlines(with_breaks))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        description = text or None

    criteria = {}
    for match in LINKEDIN_CRITERIA_RE.finditer(html):
        key = clean_text(match.group(1)).lower()
        criteria[key] = clean_text(match.group(2))

    apply_match = LINKEDIN_APPLY_RE.search(html)
    apply_url = decode_html_entities(apply_match.group(1)).split("?")[0] if apply_match else None

    return {
        "id": job_id,
        "title": title or "(untitled)",
        "company": company,
        "company_url": company_url,
        "location": location,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "description": description,
        "seniority": criteria.get("seniority level"),
        "employment_type": criteria.get("employment type"),
        "job_function": criteria.get("job function"),
        "industries": criteria.get("industries"),
        "apply_url": apply_url,
    }


def http_get_html_backoff(url):
    delay_ms = LINKEDIN_BACKOFF_BASE_MS
    for attempt in range(LINKEDIN_MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": LINKEDIN_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.read().decode("utf-8"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "", None
            if e.code == 429 or e.code >= 500:
                if attempt == LINKEDIN_MAX_RETRIES:
                    return None, f"HTTP {e.code} from {url} after {attempt + 1} attempts"
                jitter_ms = random.randint(0, 500)
                time.sleep((delay_ms + jitter_ms) / 1000)
                delay_ms = min(delay_ms * 2, LINKEDIN_BACKOFF_CAP_MS)
                continue
            return None, f"HTTP {e.code} from {url}"
        except urllib.error.URLError as e:
            return None, f"network error reaching {url}: {e.reason}"
        except Exception as e:
            return None, f"unexpected error fetching {url}: {e}"
    return None, f"request to {url} failed after max retries"


def cmd_search_linkedin(args):
    params = {"location": args.location}
    if args.query:
        params["keywords"] = args.query
    tpr = jobage_to_tpr(args.jobage)
    if tpr:
        params["f_TPR"] = tpr
    work_type = linkedin_work_type_flag(args.remote)
    if work_type:
        params["f_WT"] = work_type
    params["start"] = str((args.page - 1) * 10)

    url = LINKEDIN_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    html, err = http_get_html_backoff(url)
    if err:
        print_search_result("linkedin", [], err)
        return

    cards = parse_linkedin_cards(html)[: args.limit]
    results = [
        posting(
            "linkedin", card["title"], card["company"], card["location"], None,
            card["url"], [], None, card["posted_date"], None,
        )
        for card in cards
    ]
    print_search_result("linkedin", results, None)


def print_detail_result(source, result, error):
    print(json.dumps({"source": source, "error": error, "result": result}, indent=2))


def cmd_search_linkedin_detail(args):
    job_id = normalize_linkedin_job_id(args.id)
    if not job_id:
        print_detail_result("linkedin", None, f"could not parse a job id from '{args.id}'")
        return

    html, err = http_get_html_backoff(f"{LINKEDIN_DETAIL_URL}/{job_id}")
    if err:
        print_detail_result("linkedin", None, err)
        return
    if not html:
        print_detail_result("linkedin", None, "job not found")
        return

    detail = parse_linkedin_detail(html, job_id)
    print_detail_result("linkedin", detail, None)


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except urllib.error.URLError as e:
        return None, f"network error reaching {url}: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON from {url}: {e}"
    except Exception as e:
        return None, f"unexpected error fetching {url}: {e}"


def http_post_json(url, payload, extra_headers=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=APIFY_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except urllib.error.URLError as e:
        return None, f"network error reaching {url}: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON from {url}: {e}"
    except Exception as e:
        return None, f"unexpected error fetching {url}: {e}"


def posting(source, title, company, location, remote, url, tags, salary, posted_date, description):
    return {
        "source": source, "title": title, "company": company, "location": location,
        "remote": remote, "url": url, "tags": tags or [], "salary": salary,
        "posted_date": posted_date, "description": strip_html(description)[:1500] if description else None,
    }


def print_search_result(source, results, error, extra=None):
    out = {"source": source, "error": error, "results": results}
    if extra:
        out.update(extra)
    print(json.dumps(out, indent=2))


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


def parse_ats_payload(platform, company, data):
    """Map one platform's raw JSON payload to a list of posting() dicts."""
    if platform == "greenhouse":
        return [
            posting(
                "greenhouse", j.get("title"), company, (j.get("location") or {}).get("name"),
                None, j.get("absolute_url"), [d.get("name") for d in j.get("departments", [])],
                None, j.get("updated_at"), j.get("content"),
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
            )
            for j in data
        ]
    if platform == "ashby":
        return [
            posting(
                "ashby", j.get("title"), company, j.get("location"), j.get("isRemote"),
                j.get("jobUrl"), [j["departmentName"]] if j.get("departmentName") else [],
                None, j.get("publishedAt"), j.get("descriptionPlain"),
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
            )
            for j in data.get("offers", [])
        ]
    # workable
    return [
        posting(
            "workable", j.get("title"), company,
            (j.get("location") or {}).get("location_str")
            or ", ".join(filter(None, [(j.get("location") or {}).get("city"), (j.get("location") or {}).get("country")])),
            j.get("telecommute"), j.get("url") or j.get("shortlink"),
            [j.get("department")] if j.get("department") else [],
            None, j.get("published_on"), j.get("description"),
        )
        for j in data.get("jobs", [])
    ]


def fetch_ats_postings(platform, slug, query=None):
    """Fetch + parse one (platform, slug) pair. Returns (results, error) — never raises, same
    reliability contract as http_get_json: a bad slug or dead endpoint degrades to
    (results=[], error="..."), never a stack trace."""
    url = ATS_ENDPOINTS[platform].format(slug=slug)
    data, err = http_get_json(url)
    if err:
        return [], err
    raw = parse_ats_payload(platform, slug, data)
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
    slugs = candidate_slugs(args.company, args.slug_hint)

    attempts = []
    best = None      # (platform, slug, results) — non-empty results, high confidence
    fallback = None  # (platform, slug, results) — valid-looking board, zero postings, low confidence

    for slug in slugs:
        for platform in platforms:
            results, err = fetch_ats_postings(platform, slug, args.query)
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
    if chosen is None:
        print_search_result("discover-ats", [], None, {
            "company": args.company, "detected_platform": None, "detected_slug": None,
            "confidence": "none", "candidates_tried": attempts,
        })
        return

    platform, slug, results = chosen
    print_search_result("discover-ats", results[: args.limit], None, {
        "company": args.company, "detected_platform": platform, "detected_slug": slug,
        "confidence": "high" if best else "low", "candidates_tried": attempts,
    })


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


def http_get_html(url):
    """Plain HTML GET for reading a career page's markup -- no retry/backoff (unlike
    http_get_html_backoff, which is tuned specifically for LinkedIn's rate limiting). Same
    (text, error) contract as http_get_json: never raises."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except urllib.error.URLError as e:
        return None, f"network error reaching {url}: {e.reason}"
    except Exception as e:
        return None, f"unexpected error fetching {url}: {e}"


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
    results, err = fetch_workday_postings(tenant_info, args.query, args.limit, location_hint=args.location_hint)
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
    results, err = fetch_workday_postings(tenant_info, args.query, args.limit, location_hint=args.location_hint)
    print_search_result("workday-jobs", results, err)


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


def fetch_comeet_postings(token, company_uid, company=None, query=None, limit=25):
    """Fetch a Comeet-hosted company's full current posting list in one request -- unlike
    Workday, Comeet's positions endpoint already returns every field needed (location, department,
    employment type, apply URL, last-updated timestamp) inline, so no per-posting detail fetch or
    pagination loop is needed here. Returns (results, error): a company genuinely having zero
    current openings is not an error, same contract as every other `search` source."""
    url = COMEET_POSITIONS_URL.format(company_uid=urllib.parse.quote(company_uid, safe=""), token=token)
    data, err = http_get_json(url)
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
            None,
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


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="group", required=True)

    p_profile = sub.add_parser("profile")
    profile_sub = p_profile.add_subparsers(dest="action", required=True)
    profile_sub.add_parser("show").set_defaults(func=cmd_profile_show)
    p_set = profile_sub.add_parser("set")
    p_set.add_argument("patch")
    p_set.set_defaults(func=cmd_profile_set)

    p_tracker = sub.add_parser("tracker")
    tracker_sub = p_tracker.add_subparsers(dest="action", required=True)
    p_list = tracker_sub.add_parser("list")
    p_list.add_argument("--status")
    p_list.add_argument("--stale-only", action="store_true")
    p_list.set_defaults(func=cmd_tracker_list)
    p_upsert = tracker_sub.add_parser("upsert")
    p_upsert.add_argument("row")
    p_upsert.set_defaults(func=cmd_tracker_upsert)
    tracker_sub.add_parser("render").set_defaults(func=cmd_tracker_render)

    p_network = sub.add_parser("network")
    network_sub = p_network.add_subparsers(dest="action", required=True)

    p_net_import = network_sub.add_parser("import")
    p_net_import.add_argument("--csv", required=True, help="Path to LinkedIn's exported Connections.csv")
    p_net_import.set_defaults(func=cmd_network_import)

    p_net_list = network_sub.add_parser("list")
    p_net_list.add_argument("--company", help="Filter to connections at this company (normalized whole-word match)")
    p_net_list.set_defaults(func=cmd_network_list)

    p_net_match = network_sub.add_parser("match")
    p_net_match.add_argument("--company", help="Check one company ad hoc instead of iterating profile's target_companies")
    p_net_match.set_defaults(func=cmd_network_match)

    p_net_companies = network_sub.add_parser("companies")
    p_net_companies.set_defaults(func=cmd_network_companies)

    p_search = sub.add_parser("search")
    search_sub = p_search.add_subparsers(dest="action", required=True)

    p_remotive = search_sub.add_parser("remotive")
    p_remotive.add_argument("--query")
    p_remotive.add_argument("--category")
    p_remotive.add_argument("--limit", type=int, default=25)
    p_remotive.set_defaults(func=cmd_search_remotive)

    p_arbeitnow = search_sub.add_parser("arbeitnow")
    p_arbeitnow.add_argument("--query")
    p_arbeitnow.add_argument("--limit", type=int, default=25)
    p_arbeitnow.add_argument("--max-pages", type=int, default=3)
    p_arbeitnow.set_defaults(func=cmd_search_arbeitnow)

    p_ats = search_sub.add_parser("ats")
    p_ats.add_argument("--platform", required=True, choices=list(ATS_ENDPOINTS))
    p_ats.add_argument("--company", required=True)
    p_ats.add_argument("--query")
    p_ats.add_argument("--limit", type=int, default=25)
    p_ats.set_defaults(func=cmd_search_ats)

    p_discover = search_sub.add_parser("discover-ats")
    p_discover.add_argument("--company", required=True)
    p_discover.add_argument("--slug-hint", dest="slug_hint", help="A likely slug to try first, e.g. parsed from a pasted URL fragment")
    p_discover.add_argument("--platforms", help="Comma-separated subset to probe (default: all supported ATS platforms)")
    p_discover.add_argument("--query")
    p_discover.add_argument("--limit", type=int, default=25)
    p_discover.set_defaults(func=cmd_search_discover_ats)

    p_linkedin = search_sub.add_parser("linkedin")
    p_linkedin.add_argument("--query")
    p_linkedin.add_argument("--location", required=True)
    p_linkedin.add_argument("--jobage", type=int)
    p_linkedin.add_argument("--remote", choices=["remote", "hybrid", "onsite"])
    p_linkedin.add_argument("--page", type=int, default=1)
    p_linkedin.add_argument("--limit", type=int, default=25)
    p_linkedin.set_defaults(func=cmd_search_linkedin)

    p_linkedin_detail = search_sub.add_parser("linkedin-detail")
    p_linkedin_detail.add_argument("--id", required=True)
    p_linkedin_detail.set_defaults(func=cmd_search_linkedin_detail)

    p_workday = search_sub.add_parser("workday")
    p_workday.add_argument("--url", required=True, help="Company's myworkdayjobs.com career-site URL")
    p_workday.add_argument("--query")
    p_workday.add_argument("--location")
    p_workday.add_argument("--limit", type=int, default=25)
    p_workday.set_defaults(func=cmd_search_workday)

    p_jobs_index = search_sub.add_parser("jobs-index")
    p_jobs_index.add_argument("--company", help="Organization name to search for (exact-ish phrase match)")
    p_jobs_index.add_argument("--domain", help="Company domain to search for (exact match, e.g. 'acme.com')")
    p_jobs_index.add_argument("--query", help="Job title to search for")
    p_jobs_index.add_argument(
        "--location",
        help="'City, State/Region, Country' format, e.g. 'London, England, United Kingdom' "
             "(English names only, no abbreviations -- see README for the exact convention)",
    )
    p_jobs_index.add_argument("--ats", help="Comma-separated ATS platform filter, e.g. 'workday,oraclecloud,comeet'")
    p_jobs_index.add_argument("--work-arrangement", dest="work_arrangement", choices=["On-site", "Hybrid", "Remote OK", "Remote Solely"])
    p_jobs_index.add_argument(
        "--time-range", dest="time_range", default=JOBS_INDEX_DEFAULT_TIME_RANGE,
        choices=["1h", "24h", "7d", "6m"],
        help="'6m' (default) = every currently active posting, for a per-company full-board pull. "
             "Use '24h'/'7d' instead for a market-wide freshness scan.",
    )
    p_jobs_index.add_argument("--limit", type=int, default=JOBS_INDEX_DEFAULT_LIMIT)
    p_jobs_index.set_defaults(func=cmd_search_jobs_index)

    p_discover_workday = search_sub.add_parser("discover-workday")
    p_discover_workday.add_argument(
        "--url", required=True,
        help="A company's career-page URL (its HTML will be scanned for a myworkdayjobs.com link), "
             "or a myworkdayjobs.com URL directly if already known",
    )
    p_discover_workday.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_discover_workday.add_argument("--query")
    p_discover_workday.add_argument(
        "--location-hint", dest="location_hint",
        help="Text to pre-filter the compact posting list on (e.g. 'United Kingdom') before the "
             "expensive per-posting detail fetch, so a large board (NVIDIA: 2,000+ postings) can "
             "be scanned in full instead of only its first --limit-worth. Omit for the default "
             "behavior (pagination and detail-fetch share the same small budget -- fine for "
             "boards under a couple hundred postings).",
    )
    p_discover_workday.add_argument("--limit", type=int, default=25)
    p_discover_workday.set_defaults(func=cmd_search_discover_workday)

    p_workday_jobs = search_sub.add_parser("workday-jobs")
    p_workday_jobs.add_argument(
        "--slug", required=True,
        help="'<tenant>/<wd_host>/<site>' as returned by a prior discover-workday call's detected_slug "
             "(e.g. 'unitytech/wd1/Unity') -- skips the career-page fetch and goes straight to the API",
    )
    p_workday_jobs.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_workday_jobs.add_argument("--query")
    p_workday_jobs.add_argument(
        "--location-hint", dest="location_hint",
        help="See 'search discover-workday --help' -- same pre-filter, for when the board is large.",
    )
    p_workday_jobs.add_argument("--limit", type=int, default=25)
    p_workday_jobs.set_defaults(func=cmd_search_workday_jobs)

    p_discover_comeet = search_sub.add_parser("discover-comeet")
    p_discover_comeet.add_argument(
        "--url", required=True,
        help="A company's career-page URL -- its HTML will be scanned for an inline COMEET.init(...) "
             "call to extract the public token + company-uid",
    )
    p_discover_comeet.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_discover_comeet.add_argument("--query")
    p_discover_comeet.add_argument("--limit", type=int, default=25)
    p_discover_comeet.set_defaults(func=cmd_search_discover_comeet)

    p_comeet_jobs = search_sub.add_parser("comeet-jobs")
    p_comeet_jobs.add_argument(
        "--slug", required=True,
        help="'<token>:<company_uid>' as returned by a prior discover-comeet call's detected_slug "
             "-- skips the career-page fetch and goes straight to the API",
    )
    p_comeet_jobs.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_comeet_jobs.add_argument("--query")
    p_comeet_jobs.add_argument("--limit", type=int, default=25)
    p_comeet_jobs.set_defaults(func=cmd_search_comeet_jobs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
