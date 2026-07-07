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

State lives in ~/Desktop/Job-Search/ by default (override with JOB_SEARCH_DIR env var):
  profile.json          - target role/location/industry/seniority/preferences
  tracker.json          - application rows (source of truth)
  Tracker.md            - rendered markdown view of tracker.json
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
