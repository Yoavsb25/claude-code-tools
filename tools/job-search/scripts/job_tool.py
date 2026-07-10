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
  job_tool.py search workday --url <company myworkdayjobs.com URL> [--query X] [--location Y] [--limit 25]

State lives in ~/Desktop/Job-Search/ by default (override with JOB_SEARCH_DIR env var):
  profile.json          - target role/location/industry/seniority/preferences
  tracker.json          - application rows (source of truth)
  Tracker.md            - rendered markdown view of tracker.json

The `search` group hits public, keyless JSON APIs directly (no scraping, no MCP) and always
prints a JSON object with a "results" list — a fetch failure for one source (network policy,
outage, unknown company slug) is reported as an "error" string with an empty "results" list,
never a stack trace, so a caller can fall back to another source without the whole run failing.
`search workday` is the one exception to "keyless" — it's an optional paid fallback via Apify
for Workday-hosted career sites (see below), off by default until APIFY_TOKEN is set.

`search discover-ats` is the one exception to "always error or results": since a company simply
not being on any of the six supported ATS platforms is a normal outcome, not a failure, it never
sets "error" — instead it reports a "confidence" of "high" (postings found), "low" (an endpoint
resolved without error but returned zero postings — some platforms don't 404 on unknown slugs, so
this is a guess, not a confirmed match), or "none" (nothing resolved on any platform/slug tried).

The `linkedin` and `linkedin-detail` sources hit LinkedIn's public jobs-guest endpoints directly
(no auth, no API key). Automated access to these pages is against LinkedIn's Terms of Service —
personal use only, keep query volume low, never bulk or commercial use.

The `workday` source runs a paid Apify Actor (Workday has no keyless API) to cover large
enterprises that WebFetch/Playwright often can't reach. Requires an APIFY_TOKEN env var — with
no token set, it degrades the same way any other source degrades on failure: an "error" string
and empty "results", never a stack trace. See tools/job-search/README.md for setup and cost.
"""

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HTTP_TIMEOUT = 15
USER_AGENT = "job-search-skill/1.2 (+https://github.com/Yoavsb25/claude-code-tools)"
APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_DEFAULT_WORKDAY_ACTOR = "automation-lab/workday-jobs-scraper"
APIFY_TIMEOUT = 90  # actor runs are synchronous and can take much longer than a plain GET
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
# is a POST with a JSON body, not a GET like every platform below). It's still reachable via the
# separate `search workday` command below (a paid Apify Actor, not a keyless API), with
# WebSearch/WebFetch in SKILL.md as the free fallback when no APIFY_TOKEN is configured.
ATS_PROBE_ORDER = ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable"]
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
    ("fit", "Fit"), ("found_date", "Found"), ("applied_date", "Applied"),
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")


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
        key = (patch["company"].strip().lower(), patch["role"].strip().lower())
        match = next(
            (r for r in rows if (r["company"].strip().lower(), r["role"].strip().lower()) == key),
            None,
        )

    if match is None:
        if not patch.get("company") or not patch.get("role"):
            print("error: new rows require both 'company' and 'role'", file=sys.stderr)
            sys.exit(1)
        row = {
            "id": data["next_id"], "company": patch["company"], "role": patch["role"],
            "status": "Shortlisted", "fit": None, "found_date": today_str(),
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


def http_post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
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
                None, j.get("hostedUrl"), (j.get("categories") or {}).get("allLocations") or [],
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
    to bound the number of probe requests discover-ats makes."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    trimmed = [w for w in words if w not in ATS_SLUG_SUFFIXES] or words

    candidates = []
    if slug_hint:
        candidates.append(slug_hint.strip().lower())
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
    run_url = (
        f"{APIFY_API_BASE}/acts/{urllib.parse.quote(actor, safe='')}"
        f"/run-sync-get-dataset-items?token={urllib.parse.quote(token)}"
    )
    payload = {
        "companyUrl": args.url,
        "searchQuery": args.query or "",
        "location": args.location or "",
        "maxJobs": args.limit,
        "includeDescription": True,
    }

    items, err = http_post_json(run_url, payload)
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
