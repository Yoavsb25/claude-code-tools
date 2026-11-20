"""LinkedIn connections export: import, list, match warm intros."""

import csv
import io
import json
import sys
from pathlib import Path

from jobsearch.profile import profile_path
from jobsearch.store import load_json, save_json, state_dir, today_str
from jobsearch.text import company_words_match, normalize_company

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
        # Prefer the shortest original spelling as the display name (e.g. "Acme" over
        # "Acme Inc") since it's usually the cleanest form of the same company.
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



