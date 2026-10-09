"""Application tracker: status machine, events, markdown view."""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from jobsearch.store import load_json, parse_date, read_json_arg, save_json, state_dir, today_str
from jobsearch.text import normalize_company

STATUS_ORDER = [
    "Shortlisted", "Applied", "Responded", "Phone Screen", "Interviewing",
    "Offer", "Rejected", "Ghosted", "Withdrawn",
]
FOLLOWUP_STATUSES = ("Applied", "Responded", "Phone Screen", "Interviewing")
CHANNELS = ("easy_apply", "ats", "agency", "referral", "other")
POSITIONINGS = ("P1", "P2", "P3", "P4")
TIERS = (1, 2)
GHOST_AFTER_DAYS = 21
SHORTLIST_STALE_DAYS = 10
DEFAULT_FOLLOWUP_DAYS = 14
INTERVIEW_FOLLOWUP_DAYS = 7

TRACKER_COLUMNS = [
    ("company", "Company"), ("role", "Role"), ("status", "Status"),
    ("tier", "Tier"), ("channel", "Channel"), ("positioning", "Pos"),
    ("fit", "Fit"), ("salary", "Salary"), ("found_date", "Found"), ("applied_date", "Applied"),
    ("followup_date", "Follow-up"), ("resume_path", "Resume"),
    ("link", "Link"), ("notes", "Notes"),
]


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
    if status in ("Responded", "Phone Screen", "Interviewing"):
        return (date.today() + timedelta(days=INTERVIEW_FOLLOWUP_DAYS)).isoformat()
    return prev_followup_str


def compute_stale_reason(row):
    status = row.get("status")
    today = date.today()

    if status == "Shortlisted":
        found = parse_date(row.get("found_date"))
        if found and (today - found).days >= SHORTLIST_STALE_DAYS:
            return f"Still shortlisted after {(today - found).days} days — decide or drop"

    if status in FOLLOWUP_STATUSES:
        followup = parse_date(row.get("followup_date"))
        if followup and today >= followup:
            return f"Follow-up was due {row['followup_date']} — no status change logged since"

    return None


def cmd_tracker_upsert(args):
    row, err = upsert_tracker_row(read_json_arg(args.row))
    if err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(row, indent=2))


def validate_tracker_patch(patch):
    for key, allowed in (("status", STATUS_ORDER), ("channel", CHANNELS),
                         ("positioning", POSITIONINGS), ("tier", TIERS)):
        value = patch.get(key)
        if value is not None and (isinstance(value, bool) or value not in allowed):
            return f"invalid {key} {patch[key]!r}; expected one of {list(allowed)}"
    return None


def upsert_tracker_row(patch, source="manual", event=None, when=None):
    """Insert or update one tracker row (matched by id, else company + role). Returns
    (row, error). Shared by `tracker upsert`, the Radar page's Save button and inbox sync.
    A status change is recorded in the row's `events` history with `source` (manual | radar |
    inbox | auto | undo) and dated `when` (default today); `event`, if given, is appended as-is."""
    err = validate_tracker_patch(patch)
    if err:
        return None, err
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
            return None, "new rows require both 'company' and 'role'"
        row = {
            "id": data["next_id"], "company": patch["company"], "role": patch["role"],
            "status": "Shortlisted", "fit": None, "salary": None, "found_date": today_str(),
            "applied_date": None, "followup_date": None, "resume_path": None,
            "link": None, "notes": None,
            "channel": None, "tier": None, "positioning": None, "events": [],
        }
        data["next_id"] += 1
        rows.append(row)
        old_status = None
    else:
        row = match
        old_status = row.get("status")

    for k, v in patch.items():
        if k in ("id", "events"):
            continue
        row[k] = v
    if "positioning" in patch and "positioning_inferred" not in patch:
        row["positioning_inferred"] = False

    events = row.setdefault("events", [])

    if "status" in patch:
        if patch["status"] == "Applied" and not row.get("applied_date"):
            row["applied_date"] = today_str()
        if "followup_date" not in patch:
            row["followup_date"] = next_followup(row["status"], row.get("applied_date"), row.get("followup_date"))
        if patch["status"] == "Shortlisted" and old_status not in (None, "Shortlisted") and "applied_date" not in patch:
            row["applied_date"] = row["followup_date"] = None  # back to "not applied yet"
        if patch["status"] != old_status:
            events.append({"date": when or today_str(), "type": "status", "from": old_status,
                           "to": patch["status"], "source": source})
    if event:
        events.append({"date": today_str(), **event})

    save_rows(data)
    return row, None


def undo_last_status(row_id):
    """Revert the most recent automatic (inbox sync or ghosting) status change on a row."""
    data = load_rows()
    row = next((r for r in data["rows"] if r["id"] == row_id), None)
    if row is None:
        return None, f"no tracker row {row_id}"
    last = next((e for e in reversed(row.get("events") or []) if e.get("type") == "status"), None)
    if last is None or last.get("source") not in ("inbox", "auto") or last.get("from") is None:
        return None, "last status change was not automatic; nothing to undo"
    row["status"] = last["from"]
    if row["status"] == "Shortlisted":
        row["applied_date"] = row["followup_date"] = None
    row["events"].append({"date": today_str(), "type": "status", "from": last["to"],
                          "to": last["from"], "source": "undo"})
    save_rows(data)
    return row, None


def mark_ghosted(today=None, skip_ids=()):
    """Applied rows with no reply for GHOST_AFTER_DAYS become Ghosted. Only call this right after a
    successful inbox sync — otherwise a reply that was never read would be mistaken for silence."""
    today = today or date.today()
    data = load_rows()
    ghosted = []
    for row in data["rows"]:
        applied = parse_date(row.get("applied_date"))
        if (row["status"] != "Applied" or not applied or row["id"] in skip_ids
                or (today - applied).days < GHOST_AFTER_DAYS):
            continue
        row["status"] = "Ghosted"
        row.setdefault("events", []).append({"date": today.isoformat(), "type": "status",
                                             "from": "Applied", "to": "Ghosted", "source": "auto"})
        ghosted.append(row)
    if ghosted:
        save_rows(data)
    return ghosted


CHANNEL_RULES = [
    ("referral", re.compile(r"\breferred\b|via referral|referral (submitted|made)", re.I)),
    ("agency", re.compile(r"recruitment agency|\bagency\b", re.I)),
    ("easy_apply", re.compile(r"easy apply", re.I)),
    ("ats", re.compile(r"greenhouse|lever\.co|ashby|workable|teamtailor|workday|smartrecruiters|recruitee|"
                       r"jobs\.gem\.com|comeet|bamboohr|personio|hibob", re.I)),
]
# First match wins, so the more specific lanes come before the catch-all P2.
POSITIONING_RULES = [
    ("P4", re.compile(r"program|project|product manager|\btpm\b|delivery", re.I)),
    ("P3", re.compile(r"forward[- ]deploy|\bfde\b|solutions?\b|implementation|customer", re.I)),
    ("P1", re.compile(r"\bai\b|artificial intelligence|\bml\b|machine learning|\bllm|automation|"
                      r"enablement|transformation", re.I)),
    ("P2", re.compile(r"platform|devops|infrastructure|\bsre\b|reliability|build|developer experience|"
                      r"software engineer|backend|python developer|quality", re.I)),
]
REJECTION_DATE_RE = re.compile(r"rejection[^0-9]{0,40}(\d{4}-\d{2}-\d{2})", re.I)


def infer_channel(row):
    text = f"{row.get('notes') or ''} {row.get('link') or ''}"
    return next((name for name, rx in CHANNEL_RULES if rx.search(text)), None)


def infer_positioning(role):
    return next((p for p, rx in POSITIONING_RULES if rx.search(role or "")), None)


def backfill_events(row):
    events = []
    if row.get("applied_date"):
        events.append({"date": row["applied_date"], "type": "status", "from": None, "to": "Applied",
                       "source": "migrate"})
    if row.get("status") not in ("Shortlisted", "Applied"):
        m = REJECTION_DATE_RE.search(row.get("notes") or "") if row["status"] == "Rejected" else None
        events.append({"date": m.group(1) if m else None, "type": "status",
                       "from": "Applied" if row.get("applied_date") else None, "to": row["status"],
                       "source": "migrate"})
    return events


def migrate_tracker():
    """Bring every row up to the v2 schema (backing up tracker.json first). Safe to re-run: only
    fills fields that are missing, never overwrites a value already set."""
    data = load_rows()
    backup = tracker_path().with_name(f"tracker.json.bak-{today_str()}")
    if tracker_path().exists() and not backup.exists():
        save_json(backup, data)
    filled = {"channel": 0, "positioning": 0, "events": 0}
    for row in data["rows"]:
        row.setdefault("tier", None)
        if not row.get("channel"):
            row["channel"] = infer_channel(row)
            filled["channel"] += row["channel"] is not None
        if not row.get("positioning"):
            row["positioning"] = infer_positioning(row.get("role"))
            row["positioning_inferred"] = row["positioning"] is not None
            filled["positioning"] += row["positioning"] is not None
        if "events" not in row:
            row["events"] = backfill_events(row)
            filled["events"] += bool(row["events"])
    save_rows(data)
    return filled


def cmd_tracker_migrate(_args):
    print(json.dumps(migrate_tracker(), indent=2))


def cmd_tracker_undo(args):
    row, err = undo_last_status(args.id)
    if err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
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



