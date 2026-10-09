#!/usr/bin/env python3
"""
Cockpit views for the Radar page: turns tracker.json + inbox_state.json + connections.json into
what the Today, Pipeline and Insights tabs show, and guards the few edits the page may make.
The view functions are pure (rows/state in, dicts out); radar.py serves build() at /api/cockpit.

State it adds: cockpit_state.json — {"proof": [{"date", "title"}]}, the public-proof log behind
the weekly 3/2/1 target.
"""

import statistics
from datetime import date, timedelta

import inbox
import job_tool

CONVERSATION_STATUSES = ("Responded", "Phone Screen", "Interviewing", "Offer")
WEEKLY_TARGETS = {"applications": 3, "conversations": 2, "proof": 1}
LOW_SAMPLE = 5  # fewer applications than this in a group: too few to trust its rate
RECENT_DAYS = 7
EDITABLE = ("status", "tier", "channel", "positioning", "notes", "followup_date")


# ---- per-row facts ------------------------------------------------------------

def applied(row):
    return bool(row.get("applied_date")) or row.get("status") != "Shortlisted"


def _status_events(row):
    return [e for e in row.get("events") or [] if e.get("type") == "status"]


def reached_conversation(row):
    return row.get("status") in CONVERSATION_STATUSES or any(
        e.get("to") in CONVERSATION_STATUSES for e in _status_events(row))


def first_response_days(row):
    """Days from applying to the first employer reaction (an email that isn't a confirmation, or a
    status change to a conversation or Rejected). None if nothing came back yet."""
    applied_on = job_tool.parse_date(row.get("applied_date"))
    if not applied_on:
        return None
    heard = []
    for e in row.get("events") or []:
        reaction = ((e.get("type") == "email" and e.get("kind") in ("rejection", "interview", "reply")) or
                    (e.get("type") == "status" and e.get("to") in CONVERSATION_STATUSES + ("Rejected",)))
        d = job_tool.parse_date(e.get("date"))
        if reaction and d:
            heard.append(max((d - applied_on).days, 0))
    return min(heard) if heard else None


# ---- insights -----------------------------------------------------------------

def breakdown(rows, key):
    groups = {}
    for row in rows:
        if not applied(row):
            continue
        g = groups.setdefault(str(row.get(key) or "unknown"),
                              {"applied": 0, "conversations": 0, "rejected": 0, "ghosted": 0})
        g["applied"] += 1
        g["conversations"] += reached_conversation(row)
        g["rejected"] += row.get("status") == "Rejected"
        g["ghosted"] += row.get("status") == "Ghosted"
    for g in groups.values():
        g["rate"] = round(g["conversations"] / g["applied"], 2)
        g["low_sample"] = g["applied"] < LOW_SAMPLE
    return dict(sorted(groups.items(), key=lambda kv: -kv[1]["applied"]))


def weekly_kpis(rows, proof, today):
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)

    def in_week(value):
        d = job_tool.parse_date(value)
        return d is not None and start <= d <= end

    return {
        "week_start": start.isoformat(),
        "applications": sum(1 for row in rows if in_week(row.get("applied_date"))),
        "conversations": sum(1 for row in rows for e in _status_events(row)
                             if e.get("to") in CONVERSATION_STATUSES and in_week(e.get("date"))),
        "proof": sum(1 for p in proof if in_week(p.get("date"))),
        "targets": WEEKLY_TARGETS,
    }


def insights(rows, proof, today):
    done = [row for row in rows if applied(row)]
    days = [d for d in map(first_response_days, done) if d is not None]
    status = [row.get("status") for row in done]
    return {
        "funnel": {
            "applied": len(done),
            "heard_back": sum(1 for row in done if first_response_days(row) is not None
                              or row.get("status") in CONVERSATION_STATUSES + ("Rejected",)),
            "conversations": sum(map(reached_conversation, done)),
            "interviewing": sum(1 for row in done if row.get("status") in ("Interviewing", "Offer")
                                or any(e.get("to") == "Interviewing" for e in _status_events(row))),
            "offers": status.count("Offer"),
            "rejected": status.count("Rejected"),
            "ghosted": status.count("Ghosted"),
            "waiting": status.count("Applied"),
        },
        "by_channel": breakdown(rows, "channel"),
        "by_positioning": breakdown(rows, "positioning"),
        "by_tier": breakdown(rows, "tier"),
        "median_days_to_response": statistics.median(days) if days else None,
        "week": weekly_kpis(rows, proof, today),
    }


# ---- warm contacts --------------------------------------------------------------

def contacts_by_row(rows, connections, limit=8):
    """Connections whose company matches each row's company. A one-word dictionary name ("Global")
    must match exactly, so a contact at "Global Payments" isn't offered as a way into "Global"."""
    index = [(job_tool.normalize_company(c.get("company")), c) for c in connections]
    out = {}
    for row in rows:
        target = job_tool.normalize_company(row["company"])
        generic = len(target) == 1 and target[0] in inbox.GENERIC_COMPANY_WORDS
        hits = [{"name": f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip(),
                 "position": c.get("position"), "url": c.get("url")}
                for words, c in index
                if (words == target if generic else job_tool.company_words_match(target, words))]
        if hits:
            out[row["id"]] = hits[:limit]
    return out


# ---- today ----------------------------------------------------------------------

def today_view(rows, state, today):
    by_id = {row["id"]: row for row in rows}

    def label(row_id):
        row = by_id.get(row_id)
        return {"id": row_id, "company": row["company"], "role": row["role"]} if row else None

    since = (today - timedelta(days=RECENT_DAYS)).isoformat()
    recent = []
    for row in rows:
        events = _status_events(row)
        for e in events:
            if e.get("source") in ("inbox", "auto") and (e.get("date") or "") >= since:
                recent.append(dict(e, row=label(row["id"]), undoable=e is events[-1]))
    recent.sort(key=lambda c: c["date"], reverse=True)

    followups = []
    for row in rows:
        reason = job_tool.compute_stale_reason(row)
        if reason:
            followups.append({"id": row["id"], "company": row["company"], "role": row["role"],
                              "status": row["status"], "reason": reason})

    return {
        "actions": [dict(a, row=label(a.get("row_id"))) for a in state["actions"] if not a["done"]],
        "review": [dict(i, candidates=[label(c) for c in i["candidates"] if c in by_id])
                   for i in state["review"]],
        "followups": followups,
        "recent_changes": recent,
        "positioning_to_confirm": sum(1 for row in rows if row.get("positioning_inferred")),
        "last_sync": state.get("last_sync"),
    }
