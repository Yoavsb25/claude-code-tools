#!/usr/bin/env python3
"""stdlib-only script that owns rnd-catalogue's catalogue.json -- the running inventory of open
and recently-closed R&D postings at Yoav's watchlisted companies. Never hand-edit catalogue.json;
this script (and only this script) writes it, mirroring how job-search's job_tool.py is the only
thing that writes tracker.json/profile.json.

This script does no HTTP fetching of its own -- every posting it stores comes from job-search's
job_tool.py, called as a subprocess by the agent per rnd-catalogue's SKILL.md. This script's only
job is diffing this run's fetched-and-filtered postings against the last run's, and persisting
the result.
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

CLOSED_PRUNE_DAYS = 30


def state_dir():
    d = Path(os.environ.get("JOB_SEARCH_DIR", "~/Desktop/Job-Search")).expanduser() / "rnd-catalogue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def catalogue_path():
    return state_dir() / "catalogue.json"


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


def load_catalogue():
    return load_json(catalogue_path(), {"postings": {}})


def save_catalogue(data):
    save_json(catalogue_path(), data)


def today_str():
    return date.today().isoformat()


def parse_date(s):
    if not s:
        return None
    return date.fromisoformat(s)


def read_json_arg(arg):
    raw = sys.stdin.read() if arg == "-" else arg
    return json.loads(raw)


def posting_key(p):
    """Stable identity for a posting across runs. A posting's apply URL is normally unique and
    stable, so it's the preferred key; fall back to company+title+location for the rare case a
    source doesn't supply one."""
    url = (p.get("url") or "").strip()
    if url:
        return url
    return f"{p.get('company', '')}||{p.get('title', '')}||{p.get('location', '')}"


def cmd_diff_and_save(args):
    run_postings = read_json_arg(args.postings)
    queried_companies = (
        {c.strip().lower() for c in args.companies.split(",") if c.strip()} if args.companies else set()
    )

    data = load_catalogue()
    stored = data["postings"]
    today = today_str()

    seen_keys = set()
    new_out = []
    unchanged_count = 0

    for p in run_postings:
        key = posting_key(p)
        seen_keys.add(key)
        existing = stored.get(key)
        if existing is None or existing.get("closed_date"):
            first_seen = existing["first_seen"] if existing else today
            record = {
                "company": p.get("company"), "title": p.get("title"), "location": p.get("location"),
                "link": p.get("url"), "first_seen": first_seen, "last_seen": today, "closed_date": None,
            }
            stored[key] = record
            new_out.append({**record, "key": key})
        else:
            existing["last_seen"] = today
            existing["company"] = p.get("company")
            existing["title"] = p.get("title")
            existing["location"] = p.get("location")
            existing["link"] = p.get("url")
            unchanged_count += 1

    closed_out = []
    for key, record in stored.items():
        if key in seen_keys:
            continue
        company = (record.get("company") or "").strip().lower()
        if company not in queried_companies:
            continue  # this company wasn't (successfully) queried this run -- leave it alone
        if record.get("closed_date"):
            continue  # already marked closed
        record["closed_date"] = today
        closed_out.append({**record, "key": key})

    cutoff = date.today() - timedelta(days=CLOSED_PRUNE_DAYS)
    pruned_keys = [
        key for key, record in stored.items()
        if record.get("closed_date") and parse_date(record["closed_date"]) <= cutoff
    ]
    for key in pruned_keys:
        del stored[key]

    save_catalogue(data)
    print(json.dumps(
        {"new": new_out, "closed": closed_out, "unchanged_count": unchanged_count, "pruned_count": len(pruned_keys)},
        indent=2,
    ))


def cmd_list(args):
    data = load_catalogue()
    rows = [
        {**record, "key": key}
        for key, record in data["postings"].items()
        if not record.get("closed_date")
    ]
    if args.company:
        wanted = args.company.strip().lower()
        rows = [r for r in rows if (r.get("company") or "").strip().lower() == wanted]
    rows.sort(key=lambda r: (r.get("company") or "", r.get("title") or ""))
    print(json.dumps(rows, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(prog="catalogue_store.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_diff = sub.add_parser("diff-and-save")
    p_diff.add_argument("postings", help="JSON array of this run's filtered postings, or '-' to read from stdin")
    p_diff.add_argument(
        "--companies", required=True,
        help="Comma-separated names of companies actually queried (successfully) this run",
    )
    p_diff.set_defaults(func=cmd_diff_and_save)

    p_list = sub.add_parser("list")
    p_list.add_argument("--company", help="Filter to one company (case-insensitive exact match)")
    p_list.set_defaults(func=cmd_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
