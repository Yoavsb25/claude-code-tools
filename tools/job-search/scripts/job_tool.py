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
  job_tool.py search ats --platform greenhouse|lever|ashby --company <slug> [--query X] [--limit 25]

State lives in ~/Desktop/Job-Search/ by default (override with JOB_SEARCH_DIR env var):
  profile.json          - target role/location/industry/seniority/preferences
  tracker.json          - application rows (source of truth)
  Tracker.md            - rendered markdown view of tracker.json

The `search` group hits public, keyless JSON APIs directly (no scraping, no MCP) and always
prints a JSON object with a "results" list — a fetch failure for one source (network policy,
outage, unknown company slug) is reported as an "error" string with an empty "results" list,
never a stack trace, so a caller can fall back to another source without the whole run failing.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HTTP_TIMEOUT = 15
USER_AGENT = "job-search-skill/1.1 (+https://github.com/Yoavsb25/claude-code-tools)"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ATS_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
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


def cmd_search_ats(args):
    url = ATS_ENDPOINTS[args.platform].format(slug=args.company)
    data, err = http_get_json(url)
    if err:
        print_search_result(args.platform, [], err, {"company": args.company})
        return

    if args.platform == "greenhouse":
        raw = [
            posting(
                "greenhouse", j.get("title"), args.company, (j.get("location") or {}).get("name"),
                None, j.get("absolute_url"), [d.get("name") for d in j.get("departments", [])],
                None, j.get("updated_at"), j.get("content"),
            )
            for j in data.get("jobs", [])
        ]
    elif args.platform == "lever":
        raw = [
            posting(
                "lever", j.get("text"), args.company, (j.get("categories") or {}).get("location"),
                None, j.get("hostedUrl"), (j.get("categories") or {}).get("allLocations") or [],
                None, j.get("createdAt"), j.get("descriptionPlain") or j.get("description"),
            )
            for j in data
        ]
    else:  # ashby
        raw = [
            posting(
                "ashby", j.get("title"), args.company, j.get("location"), j.get("isRemote"),
                j.get("jobUrl"), [j["departmentName"]] if j.get("departmentName") else [],
                None, j.get("publishedAt"), j.get("descriptionPlain"),
            )
            for j in data.get("jobs", [])
        ]

    query = (args.query or "").lower()
    if query:
        raw = [r for r in raw if query in (r["title"] or "").lower()]

    print_search_result(args.platform, raw[: args.limit], None, {"company": args.company})


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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
