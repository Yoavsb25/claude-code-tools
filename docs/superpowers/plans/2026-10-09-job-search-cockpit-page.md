# Cockpit Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Job Radar page into the daily cockpit: a Today tab (replies, emails to sort, follow-ups, automatic changes with undo, weekly 3/2/1), a Pipeline tab (edit tier/channel/positioning/status, history, warm contacts, copy `/resume-tailor`), an Insights tab (funnel and conversation rate by channel/positioning/tier), and tier choice when saving a role.

**Architecture:** A new `cockpit.py` holds pure functions that turn `tracker.json` + `inbox_state.json` + `connections.json` + a small `cockpit_state.json` (public-proof log) into view data, plus two guarded writers (`update_row`, `add_proof`). `radar.py serve` exposes it at `GET /api/cockpit` and a handful of POST endpoints reusing `inbox.resolve/mark_done/run_sync` and `job_tool.undo_last_status`. `radar.html` (plain JS, no build) gets three new tabs; Today becomes the default.

**Tech Stack:** Python ≥3.9 stdlib, `unittest`; plain HTML/CSS/JS in `radar.html`; Playwright MCP for the browser smoke test.

**Spec:** `docs/superpowers/specs/2026-10-09-job-search-cockpit-design.md` (build steps 3–5). Builds on `docs/superpowers/plans/2026-10-09-job-search-tracker-v2-inbox-sync.md` (merged into `job-search/radar`).

## Global Constraints

- Nothing on the page applies to jobs or sends messages. "Open in Gmail" is a link; replies are written by Yoav.
- Page writes go only through validated functions: `job_tool.upsert_tracker_row` (via `cockpit.update_row`, whitelisted fields `status, tier, channel, positioning, notes, followup_date`), `inbox.resolve`, `inbox.mark_done`, `job_tool.undo_last_status`, `cockpit.add_proof`, `radar.save_posting`.
- Stdlib only; server stays `127.0.0.1`.
- Work on branch `job-search/cockpit-page` off `job-search/radar` in `~/GitHub/claude-code-tools`; `~/.claude/skills` symlinks there, so the live 07:00 job runs whatever is checked out — every commit must keep `python3 -m unittest -q` green.
- Weekly targets: 3 applications, 2 conversations, 1 public-proof piece; week starts Monday.
- "Conversation" = status reached `Responded`, `Phone Screen`, `Interviewing` or `Offer`. Groups with fewer than 5 applications are flagged "few".
- Browser verification runs against a **copy** of `~/job-search-data` (`JOB_SEARCH_DIR`), never the real state.

## Review Focus

1. **Page edits must not corrupt rows**: a blank status, an unknown field, or an id that doesn't exist must be refused, never create or blank a row. Test: `test_update_row_guards` (Task 2).
2. **Generic company names must not invent warm contacts** ("Global" vs a connection at "Global Payments"). Test: `test_matches_company_and_guards_generic_names` (Task 1).
3. **Undo offered only where it works**: only the latest automatic status change per row shows Undo. Test: `test_today_view` asserts `undoable` (Task 1).
4. **Insights must not divide by zero or crash on rows missing v2 fields** (no events, no channel). Test: `test_insights_on_bare_rows` (Task 1).
5. **A failing inbox sync from the page must surface, not hang the button.** Test: `test_inbox_sync_endpoint_reports_error` (Task 3).

---

### Task 1: `cockpit.py` — view functions

**Files:** Create `tools/job-search/scripts/cockpit.py`, `tools/job-search/scripts/test_cockpit.py`.

**Interfaces:**
- Consumes: `job_tool.parse_date`, `normalize_company`, `company_words_match`, `compute_stale_reason`; `inbox.GENERIC_COMPANY_WORDS`.
- Produces: `CONVERSATION_STATUSES`, `WEEKLY_TARGETS`, `LOW_SAMPLE`;
  `applied(row) -> bool`; `reached_conversation(row) -> bool`; `first_response_days(row) -> int|None`;
  `breakdown(rows, key) -> {group: {"applied","conversations","rejected","ghosted","rate","low_sample"}}`;
  `weekly_kpis(rows, proof, today) -> {"week_start","applications","conversations","proof","targets"}`;
  `insights(rows, proof, today) -> {"funnel","by_channel","by_positioning","by_tier","median_days_to_response","week"}`;
  `contacts_by_row(rows, connections) -> {row_id: [{"name","position","url"}]}`;
  `today_view(rows, state, today) -> {"actions","review","followups","recent_changes","positioning_to_confirm","last_sync"}`.

- [ ] **Step 1: Failing tests** — `test_cockpit.py`:

```python
import unittest
from datetime import date

import cockpit

TODAY = date(2026, 10, 9)  # Friday; the week started Monday 2026-10-05


def r(id_, company, status, applied=None, **kw):
    row = {"id": id_, "company": company, "role": "SWE", "status": status, "applied_date": applied,
           "channel": None, "positioning": None, "tier": None, "events": [], "found_date": "2026-10-01",
           "followup_date": None}
    row.update(kw)
    return row


def sample_rows():
    return [
        r(1, "A", "Applied", "2026-10-06", channel="easy_apply", positioning="P1", tier=2),
        r(2, "B", "Rejected", "2026-10-01", channel="easy_apply", positioning="P1", tier=2, events=[
            {"date": "2026-10-01", "type": "status", "from": None, "to": "Applied", "source": "migrate"},
            {"date": "2026-10-04", "type": "status", "from": "Applied", "to": "Rejected", "source": "inbox"}]),
        r(3, "C", "Interviewing", "2026-09-30", channel="referral", positioning="P3", tier=1, events=[
            {"date": "2026-10-02", "type": "email", "kind": "interview", "msg_id": "<1>"},
            {"date": "2026-10-07", "type": "status", "from": "Responded", "to": "Interviewing", "source": "manual"}]),
        r(4, "D", "Ghosted", "2026-09-01", channel="agency"),
        r(5, "E", "Shortlisted"),
    ]


class TestInsights(unittest.TestCase):
    def test_funnel_and_median(self):
        i = cockpit.insights(sample_rows(), [], TODAY)
        self.assertEqual(i["funnel"], {"applied": 4, "heard_back": 2, "conversations": 1, "interviewing": 1,
                                       "offers": 0, "rejected": 1, "ghosted": 1, "waiting": 1})
        self.assertEqual(i["median_days_to_response"], 2.5)

    def test_breakdown_by_channel(self):
        i = cockpit.insights(sample_rows(), [], TODAY)
        b = i["by_channel"]
        self.assertEqual(list(b), ["easy_apply", "referral", "agency"])
        self.assertEqual(b["easy_apply"], {"applied": 2, "conversations": 0, "rejected": 1, "ghosted": 0,
                                           "rate": 0.0, "low_sample": True})
        self.assertEqual(b["referral"]["rate"], 1.0)
        self.assertIn("unknown", i["by_positioning"])

    def test_weekly_kpis(self):
        proof = [{"date": "2026-10-08", "title": "Blog"}, {"date": "2026-09-01", "title": "Old"}]
        w = cockpit.insights(sample_rows(), proof, TODAY)["week"]
        self.assertEqual((w["week_start"], w["applications"], w["conversations"], w["proof"]),
                         ("2026-10-05", 1, 1, 1))
        self.assertEqual(w["targets"], {"applications": 3, "conversations": 2, "proof": 1})

    def test_insights_on_bare_rows(self):
        bare = [{"id": 1, "company": "X", "role": "Y", "status": "Applied"}]
        i = cockpit.insights(bare, [], TODAY)
        self.assertEqual(i["funnel"]["applied"], 1)
        self.assertIsNone(i["median_days_to_response"])
        self.assertEqual(cockpit.insights([], [], TODAY)["by_tier"], {})


class TestContacts(unittest.TestCase):
    def test_matches_company_and_guards_generic_names(self):
        conns = [{"first_name": "Dana", "last_name": "Levi", "company": "Neo4j Inc", "position": "EM", "url": "u1"},
                 {"first_name": "Sam", "last_name": "Roe", "company": "Global Payments", "position": "Dev", "url": "u2"},
                 {"first_name": "Kim", "last_name": "Lee", "company": "Global", "position": "HR", "url": "u3"}]
        out = cockpit.contacts_by_row([r(1, "Neo4j", "Applied"), r(2, "Global", "Applied"), r(3, "Zed", "Applied")], conns)
        self.assertEqual(out[1], [{"name": "Dana Levi", "position": "EM", "url": "u1"}])
        self.assertEqual([c["name"] for c in out[2]], ["Kim Lee"])
        self.assertNotIn(3, out)


class TestToday(unittest.TestCase):
    def test_today_view(self):
        rows = [
            r(1, "Acme", "Rejected", "2026-10-01", events=[
                {"date": "2026-10-03", "type": "status", "from": "Applied", "to": "Responded", "source": "inbox"},
                {"date": "2026-10-08", "type": "status", "from": "Responded", "to": "Rejected", "source": "inbox"}]),
            r(2, "Old", "Ghosted", "2026-09-01", events=[
                {"date": "2026-09-20", "type": "status", "from": "Applied", "to": "Ghosted", "source": "auto"}]),
            r(3, "Due", "Applied", "2026-09-20", followup_date="2000-01-01", positioning="P1",
              positioning_inferred=True),
        ]
        state = {"last_sync": "2026-10-09T07:00:00+00:00", "ignored": [],
                 "actions": [{"msg_id": "<a>", "row_id": 1, "done": False, "subject": "Hi", "sender": "x",
                              "date": "2026-10-08", "kind": "reply"},
                             {"msg_id": "<b>", "row_id": 1, "done": True, "subject": "Old", "sender": "x",
                              "date": "2026-10-01", "kind": "reply"}],
                 "review": [{"msg_id": "<c>", "candidates": [1, 99], "subject": "?", "sender": "y",
                             "date": "2026-10-08", "kind": "confirmation"}]}
        t = cockpit.today_view(rows, state, TODAY)
        self.assertEqual([a["msg_id"] for a in t["actions"]], ["<a>"])
        self.assertEqual(t["actions"][0]["row"], {"id": 1, "company": "Acme", "role": "SWE"})
        self.assertEqual(t["review"][0]["candidates"], [{"id": 1, "company": "Acme", "role": "SWE"}])
        self.assertEqual([f["id"] for f in t["followups"]], [3])
        self.assertEqual([(c["row"]["id"], c["to"], c["undoable"]) for c in t["recent_changes"]],
                         [(1, "Rejected", True), (1, "Responded", False)])
        self.assertEqual(t["positioning_to_confirm"], 1)
        self.assertEqual(t["last_sync"], "2026-10-09T07:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m unittest test_cockpit -q` — Expected: `ModuleNotFoundError: No module named 'cockpit'`.

- [ ] **Step 3: Implement** `cockpit.py`:

```python
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
```

- [ ] **Step 4: Run** `python3 -m unittest -q` — Expected: OK.
- [ ] **Step 5: Commit** — `git add scripts/cockpit.py scripts/test_cockpit.py && git commit -m "job-search: cockpit view functions (today, insights, warm contacts)"`

---

### Task 2: Guarded writes — `update_row`, proof log, `build`, save with tier

**Files:** Modify `cockpit.py`, `test_cockpit.py`, `job_tool.py` (`upsert_tracker_row`: keep an explicit `positioning_inferred`), `radar.py` (`save_posting(key, tier=None)`), `test_radar.py`, `test_job_tool.py`.

**Interfaces:**
- Produces: `cockpit.update_row(body) -> (row, err)`; `cockpit.proof_path()`, `load_proof() -> list`, `add_proof(title, today=None) -> (entry, err)`;
  `cockpit.build(today=None) -> {"today","pipeline","contacts","insights","options"}` where `options = {"statuses","channels","positionings","tiers"}`;
  `radar.save_posting(key, tier=None)` stores `tier` and an inferred `positioning` (`positioning_inferred: True`).

- [ ] **Step 1: Failing tests**

`test_cockpit.py` (add `import os, tempfile`, `from unittest.mock import patch`, `import job_tool`):

```python
class TestCockpitState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_update_row_guards(self):
        row, err = cockpit.update_row({"id": 1, "tier": 1, "channel": "referral"})
        self.assertIsNone(err)
        self.assertEqual((row["tier"], row["channel"]), (1, "referral"))
        self.assertEqual(cockpit.update_row({"id": 9, "tier": 1}), (None, "no tracker row 9"))
        self.assertIn("can't edit company", cockpit.update_row({"id": 1, "company": "X"})[1])
        self.assertEqual(cockpit.update_row({"id": 1, "status": None}), (None, "status can't be empty"))
        self.assertIn("invalid tier", cockpit.update_row({"id": 1, "tier": 7})[1])
        self.assertEqual(len(job_tool.load_rows()["rows"]), 1)
        self.assertEqual(job_tool.load_rows()["rows"][0]["status"], "Applied")

    def test_proof_log(self):
        self.assertEqual(cockpit.add_proof("  "), (None, "describe the proof piece"))
        entry, err = cockpit.add_proof("Blog post on inbox sync", today=TODAY)
        self.assertEqual(entry, {"date": "2026-10-09", "title": "Blog post on inbox sync"})
        self.assertEqual(cockpit.load_proof(), [entry])

    def test_build(self):
        job_tool.save_json(job_tool.connections_path(), {"connections": [
            {"first_name": "Dana", "last_name": "Levi", "company": "Acme", "position": "EM", "url": "u"}]})
        b = cockpit.build(TODAY)
        self.assertEqual(set(b), {"today", "pipeline", "contacts", "insights", "options"})
        self.assertEqual(b["pipeline"][0]["company"], "Acme")
        self.assertEqual(b["contacts"][1][0]["name"], "Dana Levi")
        self.assertIn("Ghosted", b["options"]["statuses"])
        self.assertEqual(b["options"]["tiers"], [1, 2])
```

`test_job_tool.py` (in `TestTrackerV2`):

```python
    def test_explicit_inferred_flag_is_kept(self):
        row, _ = job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "positioning": "P2",
                                              "positioning_inferred": True})
        self.assertTrue(row["positioning_inferred"])
```

`test_radar.py` (in `TestPageServer`):

```python
    def test_save_with_tier_infers_positioning(self):
        radar.save_posting("acme|platform engineer", tier=1)
        row = radar.job_tool.load_rows()["rows"][0]
        self.assertEqual((row["tier"], row["positioning"], row["positioning_inferred"]), (1, "P2", True))
```

- [ ] **Step 2: Run** `python3 -m unittest -q` — Expected: errors for `update_row`/`add_proof`/`build`, `save_posting()` tier kwarg, and the inferred-flag test failing.

- [ ] **Step 3: Implement**

`job_tool.upsert_tracker_row`: change `if "positioning" in patch:` to
`if "positioning" in patch and "positioning_inferred" not in patch:`.

`radar.save_posting(key, tier=None)`: add to the patch dict
`"tier": tier, "positioning": job_tool.infer_positioning(p["title"]), "positioning_inferred": True,`
— but only set `positioning`/`positioning_inferred` when the row has no positioning yet, so re-saving never overwrites a confirmed value:

```python
def save_posting(key, tier=None):
    """Add a posting to the tracker as Shortlisted, with the tier chosen on the page and a guessed
    positioning for Yoav to confirm in Pipeline. Nothing is applied to or sent."""
    radar_state = job_tool.load_json(_path("radar.json"), {"postings": {}})
    p = radar_state["postings"].get(key)
    if p is None:
        return None, "unknown posting"
    patch = {
        "company": p["company"], "role": p["title"], "link": p["url"], "salary": p.get("salary"),
        "role_family": p.get("role_family"), "source": "radar",
        "notes": f"Saved from Radar ({p.get('years_min') or '?'} yrs, {p.get('level')}, fit {p.get('fit', '?')})",
    }
    if tier is not None:
        patch["tier"] = tier
    existing = next((r for r in job_tool.load_rows()["rows"]
                     if job_tool.normalize_company(r["company"]) == job_tool.normalize_company(p["company"])
                     and r["role"].strip().lower() == p["title"].strip().lower()), None)
    if not (existing and existing.get("positioning")):
        guess = job_tool.infer_positioning(p["title"])
        if guess:
            patch.update(positioning=guess, positioning_inferred=True)
    row, err = job_tool.upsert_tracker_row(patch)
    # ...rest unchanged (record in radar_state["saved"])
```

`cockpit.py` (append):

```python
# ---- guarded writes ---------------------------------------------------------------

def update_row(body):
    """The only tracker edit the page can make: whitelisted fields on an existing row."""
    row_id = body.get("id")
    if not any(row["id"] == row_id for row in job_tool.load_rows()["rows"]):
        return None, f"no tracker row {row_id}"
    patch = {k: v for k, v in body.items() if k != "id"}
    bad = [k for k in patch if k not in EDITABLE]
    if bad:
        return None, f"can't edit {', '.join(bad)} from the page"
    if "status" in patch and not patch["status"]:
        return None, "status can't be empty"
    return job_tool.upsert_tracker_row(dict(patch, id=row_id))


def proof_path():
    return job_tool.state_dir() / "cockpit_state.json"


def load_proof():
    return job_tool.load_json(proof_path(), {"proof": []})["proof"]


def add_proof(title, today=None):
    title = (title or "").strip()
    if not title:
        return None, "describe the proof piece"
    state = job_tool.load_json(proof_path(), {"proof": []})
    entry = {"date": (today or date.today()).isoformat(), "title": title[:200]}
    state["proof"].append(entry)
    job_tool.save_json(proof_path(), state)
    return entry, None


def build(today=None):
    today = today or date.today()
    rows = job_tool.load_rows()["rows"]
    return {
        "today": today_view(rows, inbox.load_state(), today),
        "pipeline": rows,
        "contacts": contacts_by_row(rows, job_tool.load_connections()["connections"]),
        "insights": insights(rows, load_proof(), today),
        "options": {"statuses": job_tool.STATUS_ORDER, "channels": list(job_tool.CHANNELS),
                    "positionings": list(job_tool.POSITIONINGS), "tiers": list(job_tool.TIERS)},
    }
```

- [ ] **Step 4: Run** `python3 -m unittest -q` — Expected: OK.
- [ ] **Step 5: Commit** — `git commit -am "job-search: cockpit guarded edits, proof log, build(); save roles with a tier"`

---

### Task 3: Server endpoints

**Files:** Modify `radar.py` (`RefreshRunner` → `Runner(target)`, `make_handler(runner, inbox_runner=None)`, `cmd_serve`, docstring), `test_radar.py`.

**Interfaces:**
- Consumes: Task 2 `cockpit.build/update_row/add_proof`, `radar.save_posting(key, tier)`, `inbox.resolve/mark_done/run_sync`, `job_tool.undo_last_status`.
- Produces: `GET /api/cockpit` → `build()` plus `inbox_syncing`, `inbox_error`; POST `/api/tracker`, `/api/inbox/resolve` (`msg_id`, optional `row_id`), `/api/inbox/done` (`msg_id`), `/api/inbox/undo` (`row_id`), `/api/inbox/sync`, `/api/proof` (`title`); `/api/save` accepts `tier`.

- [ ] **Step 1: Failing tests** (`test_radar.py`, inside `TestPageServer`; add helper)

```python
    def _serve(self, inbox_target=None):
        inbox_runner = radar.Runner(inbox_target or (lambda: None))
        server = radar.ThreadingHTTPServer(("127.0.0.1", 0), radar.make_handler(radar.Runner(lambda: None), inbox_runner))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}", inbox_runner

    def _post(self, url, body):
        req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req))

    def test_cockpit_endpoints(self):
        base, _ = self._serve()
        saved = self._post(base + "/api/save", {"key": "acme|platform engineer", "tier": 1})
        cockpit = json.load(urllib.request.urlopen(base + "/api/cockpit"))
        self.assertEqual(cockpit["pipeline"][0]["tier"], 1)
        self.assertFalse(cockpit["inbox_syncing"])
        row = self._post(base + "/api/tracker", {"id": saved["tracker_id"], "status": "Applied", "channel": "ats"})
        self.assertEqual((row["status"], row["channel"]), ("Applied", "ats"))
        self.assertEqual(self._post(base + "/api/proof", {"title": "Talk"})["title"], "Talk")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post(base + "/api/tracker", {"id": saved["tracker_id"], "company": "Evil"})
        self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError):
            self._post(base + "/api/inbox/undo", {"row_id": saved["tracker_id"]})  # last change was manual

    def test_inbox_sync_endpoint_reports_error(self):
        def failing():
            raise RuntimeError("no Keychain item")
        base, runner = self._serve(failing)
        self.assertEqual(self._post(base + "/api/inbox/sync", {}), {"started": True})
        for _ in range(50):
            if not runner.running:
                break
            time.sleep(0.02)
        cockpit = json.load(urllib.request.urlopen(base + "/api/cockpit"))
        self.assertEqual((cockpit["inbox_syncing"], cockpit["inbox_error"]), (False, "no Keychain item"))
```

(Add `import time` to the test imports. Update `test_http_endpoints` to construct `radar.Runner(lambda: None)` and expect `<title>Job Cockpit</title>`.)

- [ ] **Step 2: Run** `python3 -m unittest test_radar -q` — Expected: AttributeError `Runner`.

- [ ] **Step 3: Implement** in `radar.py`:

```python
class Runner:
    """Runs `target` on a background thread so the page never blocks on a slow fetch (a 3-minute
    radar refresh, or an inbox sync)."""

    def __init__(self, target):
        self.target = target
        self.lock = threading.Lock()
        self.running = False
        self.last_error = None

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        try:
            self.target()
            self.last_error = None
        except Exception as e:  # surfaced on the page instead of killing the server
            self.last_error = str(e)
        finally:
            with self.lock:
                self.running = False


def sync_inbox_from_page():
    inbox.run_sync()
    snapshot_state("inbox sync from the page")
```

Remove `RefreshRunner`; `cmd_serve` builds `runner = Runner(refresh)` and `inbox_runner = Runner(sync_inbox_from_page)` and passes both to `make_handler`. In `make_handler(runner, inbox_runner=None)`:

```python
    inbox_runner = inbox_runner or Runner(sync_inbox_from_page)
    actions = {
        "/api/hide": lambda body: hide_posting(body.get("key"), body.get("reason")),
        "/api/unhide": lambda body: unhide_posting(body.get("key")),
        "/api/save": lambda body: save_posting(body.get("key"), body.get("tier")),
        "/api/visit": lambda body: record_visit(),
        "/api/refresh": lambda body: ({"started": runner.start()}, None),
        "/api/watchlist": lambda body: add_to_watchlist(body.get("company")),
        "/api/tracker": cockpit.update_row,
        "/api/inbox/resolve": lambda body: inbox.resolve(body.get("msg_id"), body.get("row_id")),
        "/api/inbox/done": lambda body: inbox.mark_done(body.get("msg_id")),
        "/api/inbox/undo": lambda body: job_tool.undo_last_status(body.get("row_id")),
        "/api/inbox/sync": lambda body: ({"started": inbox_runner.start()}, None),
        "/api/proof": lambda body: cockpit.add_proof(body.get("title")),
    }
```

and in `do_GET`:

```python
            elif self.path == "/api/cockpit":
                self._send(200, dict(cockpit.build(), inbox_syncing=inbox_runner.running,
                                     inbox_error=inbox_runner.last_error))
```

`import cockpit` beside `import inbox`. Module docstring: add `cockpit_state.json - public-proof log for the weekly targets (cockpit.py)` to the State list, and say the page is the Job Cockpit (Today / Roles / Pipeline / Insights).

In `radar.html` change `<title>` and `<h1>` to `Job Cockpit` now so the title test passes (the rest of the page comes in Task 4).

- [ ] **Step 4: Run** `python3 -m unittest -q` — Expected: OK.
- [ ] **Step 5: Commit** — `git commit -am "job-search: cockpit API endpoints and background inbox sync from the page"`

---

### Task 4: Page — Today tab, tier on save, shared plumbing

**Files:** Modify `tools/job-search/scripts/radar.html`.

No JS test harness exists in this repo; Task 6's browser smoke test verifies the page. Each step here ends with `python3 -m unittest -q` (the page is served by the tested endpoints) and a syntax check: `node --check` is unavailable for inline scripts, so extract and check:

```bash
python3 -c "import re,sys;s=open('radar.html').read();open('/tmp/claude-501/cockpit.js','w').write(re.search(r'<script>(.*)</script>',s,re.S).group(1))" && node --check /tmp/claude-501/cockpit.js
```
Expected: no output (valid syntax). If `node` is missing, skip the check and rely on Task 6.

- [ ] **Step 1: Tabs and CSS.** Replace the `<nav class="tabs">` buttons with:

```html
      <button class="tab" role="tab" data-tab="today" aria-selected="true">Today</button>
      <button class="tab" role="tab" data-tab="roles" aria-selected="false">Roles</button>
      <button class="tab" role="tab" data-tab="pipeline" aria-selected="false">Pipeline</button>
      <button class="tab" role="tab" data-tab="insights" aria-selected="false">Insights</button>
      <button class="tab" role="tab" data-tab="saved" aria-selected="false">Saved</button>
      <button class="tab" role="tab" data-tab="hidden" aria-selected="false">Hidden</button>
      <button class="tab" role="tab" data-tab="coverage" aria-selected="false">Coverage</button>
```

Append to the `<style>` block (before `</style>`):

```css
  .block { margin-bottom: 22px; }
  .block h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 8px;
    display: flex; gap: 8px; align-items: center; }
  .count { background: var(--surface-2); color: var(--text); border-radius: 999px; padding: 0 8px; font-size: 12px; letter-spacing: 0; }
  .item { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 11px 13px; margin-bottom: 8px; align-items: start; }
  .item .actions { flex-wrap: wrap; justify-content: flex-end; max-width: 460px; }
  .snippet { color: var(--muted); font-size: 12.5px; margin-top: 4px; }
  .stat.met div:first-child { color: var(--good); }
  .cell-select { padding: 3px 6px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
  .btn.tiny { padding: 1px 6px; font-size: 12px; margin-left: 4px; }
  tr.prow { cursor: pointer; }
  tr.prow:hover td { background: var(--surface-2); }
  .pgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .pgrid h3, .insights h3 { font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 10px 0 6px; }
  .timeline, .contacts { margin: 0; padding-left: 18px; font-size: 13px; }
  .proof { display: flex; gap: 8px; margin: -4px 0 18px; }
  .proof input { flex: 1; padding: 6px 9px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
  .insights { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 820px) {
    .pgrid, .insights, .item { grid-template-columns: 1fr; }
    table.pipeline { display: block; overflow-x: auto; }
  }
```

- [ ] **Step 2: Shared state + loading.** Change `let ... tab = "roles"` to `tab = "today"` and add below it:

```js
let cockpit = null, flash = null;
const NO_FILTER_TABS = ["today", "pipeline", "insights", "coverage"];
const POSITIONING_LABELS = { P1: "P1 · AI tooling builder", P2: "P2 · platform engineer", P3: "P3 · FDE / solutions", P4: "P4 · technical program lead" };
const CHANNEL_LABELS = { easy_apply: "LinkedIn Easy Apply", ats: "Company careers site", agency: "Agency", referral: "Referral", other: "Other" };
const TIER_LABELS = { 1: "Tier 1 · tailored", 2: "Tier 2 · fast" };

async function loadCockpit() { cockpit = await api("/api/cockpit"); }

async function act(path, body) {
  try { await api(path, body); flash = null; }
  catch (e) { flash = e.message; }
  await loadCockpit();
  render();
}
function flashNotice() { return flash && el("div", { class: "notice warn" }, flash); }
function plusDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }
function selectTab(name) {
  tab = name;
  shown = PAGE_SIZE;
  document.querySelectorAll(".tab").forEach(t => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  render();
}
```

In `load()`, after `data = await api("/api/data");` add `await loadCockpit();`. Replace the tab click handler with
`document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => selectTab(b.dataset.tab)));`.

In `render()`, replace the first four lines after the `const` declarations with:

```js
  const noFilters = NO_FILTER_TABS.includes(tab);
  main.classList.toggle("wide", noFilters);
  filtersEl.hidden = noFilters;
  if (tab === "coverage") return content.replaceChildren(renderCoverage());
  if (tab === "today") return content.replaceChildren(renderToday());
  if (tab === "pipeline") return content.replaceChildren(renderPipeline());
  if (tab === "insights") return content.replaceChildren(renderInsights());
```

Add temporary stubs so the page works before Task 5:
`function renderPipeline() { return el("div", { class: "empty" }, "Pipeline coming next."); }` and the same for `renderInsights`.

- [ ] **Step 3: Save with tier.** In `card(p)`, replace the `☆ Save` button with:

```js
      : el("select", { "aria-label": "Save this role", onchange: e => e.target.value && save(p, Number(e.target.value)) },
          el("option", { value: "" }, "☆ Save as…"),
          el("option", { value: "1" }, "Tier 1 · tailor + warm path"),
          el("option", { value: "2" }, "Tier 2 · fast apply")));
```

and `save` becomes:

```js
async function save(p, tier) {
  try {
    data.page_state.saved[p.key] = await api("/api/save", { key: p.key, tier });
    await loadCockpit();
    render();
  } catch (e) { console.error("save failed", e); }
}
```

- [ ] **Step 4: Today tab.**

```js
function gmailLink(msgId) {
  return "https://mail.google.com/mail/u/0/#search/" + encodeURIComponent("rfc822msgid:" + msgId.replace(/[<>]/g, ""));
}
function section(title, count, body) {
  return el("section", { class: "block" }, el("h2", {}, title, el("span", { class: "count" }, count)), body);
}
function mailItem(i, buttons) {
  return el("div", { class: "card item" },
    el("div", {},
      el("div", { class: "title" }, i.subject || "(no subject)"),
      el("div", { class: "sub" }, `${i.sender} · ${i.date} · ${i.kind}`),
      i.snippet && el("div", { class: "snippet" }, i.snippet)),
    el("div", { class: "actions" }, ...buttons,
      el("a", { class: "btn", href: gmailLink(i.msg_id), target: "_blank", rel: "noopener" }, "Open in Gmail ↗")));
}
function kpiStrip(week) {
  const tile = (label, n, target) => el("div", { class: "stat" + (n >= target ? " met" : "") },
    el("div", {}, `${n}/${target}`), el("div", {}, label));
  return el("div", { class: "stat-row" },
    tile("applications this week", week.applications, week.targets.applications),
    tile("conversations this week", week.conversations, week.targets.conversations),
    tile("public-proof pieces", week.proof, week.targets.proof));
}
function rowLabel(r) { return `${r.company} — ${r.role}`; }

function renderToday() {
  const t = cockpit.today;
  const rowOptions = cockpit.pipeline.filter(r => r.status !== "Withdrawn").sort((a, b) => a.company.localeCompare(b.company));
  const empty = text => el("div", { class: "empty" }, text);

  const actions = t.actions.map(a => mailItem(a, [
    a.row && el("span", { class: "badge" }, rowLabel(a.row)),
    el("button", { class: "btn primary", type: "button", onclick: () => act("/api/inbox/done", { msg_id: a.msg_id }) }, "✓ Handled"),
  ]));
  const review = t.review.map(i => mailItem(i, [
    ...i.candidates.map(c => el("button", { class: "btn", type: "button",
      onclick: () => act("/api/inbox/resolve", { msg_id: i.msg_id, row_id: c.id }) }, `It's ${c.company}`)),
    el("select", { "aria-label": "Attach to another application",
      onchange: e => e.target.value && act("/api/inbox/resolve", { msg_id: i.msg_id, row_id: Number(e.target.value) }) },
      el("option", { value: "" }, "Another row…"), ...rowOptions.map(r => el("option", { value: r.id }, rowLabel(r)))),
    el("button", { class: "btn", type: "button", onclick: () => act("/api/inbox/resolve", { msg_id: i.msg_id }) }, "Ignore"),
  ]));
  const followups = t.followups.map(f => el("div", { class: "card item" },
    el("div", {}, el("div", { class: "title" }, rowLabel(f)), el("div", { class: "sub" }, f.reason)),
    el("div", { class: "actions" },
      f.status !== "Shortlisted" && el("button", { class: "btn", type: "button",
        onclick: () => act("/api/tracker", { id: f.id, followup_date: plusDays(7) }) }, "Followed up · remind in 7 days"),
      el("button", { class: "btn", type: "button", onclick: () => { pipelineOpen.add(f.id); pipelineFilter = "all"; selectTab("pipeline"); } }, "Open in Pipeline"))));
  const changes = t.recent_changes.map(c => el("div", { class: "card item" },
    el("div", {}, el("div", { class: "title" }, rowLabel(c.row)),
      el("div", { class: "sub" }, `${c.from || "—"} → ${c.to} · ${c.source === "auto" ? "no reply in 21 days" : "from an email"} · ${c.date}`)),
    el("div", { class: "actions" }, c.undoable && el("button", { class: "btn", type: "button",
      onclick: () => act("/api/inbox/undo", { row_id: c.row.id }) }, "Undo"))));

  return el("div", {},
    flashNotice(),
    cockpit.inbox_error && el("div", { class: "notice warn" }, `Last inbox sync failed: ${cockpit.inbox_error}`),
    el("div", { class: "summary" },
      el("div", {}, el("strong", {}, "Today"), ` · inbox synced ${t.last_sync ? ago(t.last_sync) : "never"}`),
      el("button", { class: "btn", type: "button", disabled: cockpit.inbox_syncing, onclick: syncInbox },
        cockpit.inbox_syncing ? "Syncing…" : "Sync inbox now")),
    kpiStrip(cockpit.insights.week),
    el("form", { class: "proof", onsubmit: e => { e.preventDefault(); act("/api/proof", { title: e.target.elements.title.value }); } },
      el("input", { name: "title", placeholder: "Log a public-proof piece (post, repo, talk)…", required: true, "aria-label": "Public-proof piece" }),
      el("button", { class: "btn", type: "submit" }, "Log")),
    t.positioning_to_confirm > 0 && el("div", { class: "notice" }, `${t.positioning_to_confirm} applications have a guessed positioning. `,
      el("a", { href: "#", onclick: e => { e.preventDefault(); pipelineFilter = "all"; selectTab("pipeline"); } }, "Confirm them in Pipeline")),
    section("Needs a reply", t.actions.length, actions.length ? el("div", {}, ...actions) : empty("Nothing waiting on you.")),
    section("Check these emails", t.review.length, review.length ? el("div", {}, ...review) : empty("No emails to sort.")),
    section("Follow-ups due", t.followups.length, followups.length ? el("div", {}, ...followups) : empty("No follow-ups due.")),
    section("Automatic changes · last 7 days", t.recent_changes.length, changes.length ? el("div", {}, ...changes) : empty("No automatic changes this week.")),
  );
}

async function syncInbox() {
  await act("/api/inbox/sync", {});
  const timer = setInterval(async () => {
    try { await loadCockpit(); } catch { clearInterval(timer); return; }
    if (!cockpit.inbox_syncing) clearInterval(timer);
    render();
  }, 3000);
}
```

Declare `let pipelineFilter = "active"; const pipelineOpen = new Set();` beside the other shared state (Task 5 uses them).

- [ ] **Step 5: Verify** — `python3 -m unittest -q` OK; JS syntax check passes.
- [ ] **Step 6: Commit** — `git commit -am "job-search: cockpit Today tab and save-with-tier on Roles"`

---

### Task 5: Page — Pipeline and Insights tabs

**Files:** Modify `radar.html` (replace the two stubs).

- [ ] **Step 1: Pipeline**

```js
const STATUS_GROUPS = {
  active: ["Applied", "Responded", "Phone Screen", "Interviewing", "Offer"],
  shortlisted: ["Shortlisted"],
  closed: ["Rejected", "Ghosted", "Withdrawn"],
  all: null,
};

function fieldSelect(row, key, values, label, labels = {}, allowBlank = true) {
  return el("select", { class: "cell-select", "aria-label": label, onclick: e => e.stopPropagation(),
    onchange: e => {
      const v = e.target.value;
      act("/api/tracker", { id: row.id, [key]: v === "" ? null : key === "tier" ? Number(v) : v });
    } },
    allowBlank && el("option", { value: "" }, "—"),
    ...values.map(v => el("option", { value: v, selected: row[key] === v }, labels[v] || (key === "tier" ? `Tier ${v}` : v))));
}

function renderPipeline() {
  const o = cockpit.options;
  const group = STATUS_GROUPS[pipelineFilter];
  const rows = cockpit.pipeline.filter(r => !group || group.includes(r.status))
    .sort((a, b) => (b.applied_date || b.found_date || "").localeCompare(a.applied_date || a.found_date || ""));
  const count = g => cockpit.pipeline.filter(r => !STATUS_GROUPS[g] || STATUS_GROUPS[g].includes(r.status)).length;
  const chips = el("div", { class: "chips" }, ...Object.keys(STATUS_GROUPS).map(g => el("button", {
    class: "chip", type: "button", "aria-pressed": String(g === pipelineFilter),
    onclick: () => { pipelineFilter = g; render(); } }, `${g} (${count(g)})`)));

  function rowsFor(r) {
    const contacts = cockpit.contacts[r.id] || [];
    const open = pipelineOpen.has(r.id);
    const tr = el("tr", { class: "prow", onclick: () => { open ? pipelineOpen.delete(r.id) : pipelineOpen.add(r.id); render(); } },
      el("td", {}, el("div", { class: "title" }, r.company), el("div", { class: "sub" }, r.role)),
      el("td", {}, fieldSelect(r, "status", o.statuses, "Status", {}, false)),
      el("td", {}, fieldSelect(r, "tier", o.tiers, "Tier")),
      el("td", {}, fieldSelect(r, "channel", o.channels, "Channel", CHANNEL_LABELS)),
      el("td", {}, fieldSelect(r, "positioning", o.positionings, "Positioning"),
        r.positioning_inferred && el("button", { class: "btn tiny", type: "button", title: "This was guessed from the title. Click to confirm it.",
          onclick: e => { e.stopPropagation(); act("/api/tracker", { id: r.id, positioning: r.positioning }); } }, "confirm")),
      el("td", {}, r.applied_date || "—"),
      el("td", {}, contacts.length ? `${contacts.length} 👤` : "—"));
    return open ? [tr, el("tr", {}, el("td", { colspan: 7 }, pipelineDetail(r, contacts)))] : [tr];
  }

  return el("div", {},
    flashNotice(),
    el("div", { class: "summary" }, el("div", {}, el("strong", {}, `${rows.length} applications`), " · click a row for history and Tier 1 helpers"), chips),
    rows.length
      ? el("table", { class: "pipeline" },
          el("thead", {}, el("tr", {}, ...["Company / role", "Status", "Tier", "Channel", "Positioning", "Applied", "Contacts"].map(h => el("th", {}, h)))),
          el("tbody", {}, ...rows.flatMap(rowsFor)))
      : el("div", { class: "empty" }, "Nothing in this group."));
}

function pipelineDetail(r, contacts) {
  const events = (r.events || []).slice().reverse();
  return el("div", { class: "pgrid" },
    el("div", {},
      el("h3", {}, "History"),
      events.length
        ? el("ul", { class: "timeline" }, ...events.map(e => el("li", {},
            el("span", { class: "meta" }, e.date || "date unknown"), " ",
            e.type === "status" ? `${e.from || "—"} → ${e.to}` : `${e.kind} email: ${e.subject || ""}`,
            e.source && e.source !== "manual" && el("span", { class: "meta" }, ` (${e.source})`))))
        : el("div", { class: "meta" }, "No history yet."),
      r.notes && el("p", { class: "sub" }, r.notes)),
    el("div", {},
      el("h3", {}, "Tier 1 helpers"),
      el("div", { class: "links" },
        r.link && el("a", { href: r.link, target: "_blank", rel: "noopener" }, "Job posting ↗"),
        el("button", { class: "btn", type: "button", onclick: e => copyTailor(r, e.target) }, "Copy /resume-tailor command")),
      el("h3", {}, `People you know at ${r.company}`),
      contacts.length
        ? el("ul", { class: "contacts" }, ...contacts.map(c => el("li", {},
            c.url ? el("a", { href: c.url, target: "_blank", rel: "noopener" }, c.name) : c.name,
            c.position ? ` — ${c.position}` : "")))
        : el("div", { class: "meta" }, "No connections found in your LinkedIn export.")));
}

async function copyTailor(r, button) {
  const cmd = `/resume-tailor ${r.role} at ${r.company}${r.link ? " " + r.link : ""}`;
  try { await navigator.clipboard.writeText(cmd); button.textContent = "Copied ✓"; }
  catch { button.textContent = cmd; }
}
```

- [ ] **Step 2: Insights**

```js
function pct(x) { return `${Math.round(x * 100)}%`; }

function breakdownTable(title, groups, labels) {
  const entries = Object.entries(groups);
  return el("div", {}, el("h3", {}, title),
    entries.length
      ? el("table", {},
          el("thead", {}, el("tr", {}, ...["", "Applied", "Conversations", "Rate", "Rejected", "Ghosted"].map(h => el("th", {}, h)))),
          el("tbody", {}, ...entries.map(([k, g]) => el("tr", {},
            el("td", {}, labels[k] || k),
            el("td", {}, g.applied), el("td", {}, g.conversations),
            el("td", {}, pct(g.rate), g.low_sample && el("span", { class: "meta", title: "Fewer than 5 applications: too few to trust" }, " · few")),
            el("td", {}, g.rejected), el("td", {}, g.ghosted)))))
      : el("div", { class: "meta" }, "No applications yet."));
}

function renderInsights() {
  const i = cockpit.insights;
  const f = i.funnel;
  const tile = (n, label) => el("div", { class: "stat" }, el("div", {}, n), el("div", {}, label));
  return el("div", {},
    el("div", { class: "summary" }, el("div", {}, el("strong", {}, "Insights"),
      " · conversation = any reply or invite that moved past Applied")),
    kpiStrip(i.week),
    el("div", { class: "stat-row" },
      tile(f.applied, "applied"), tile(f.heard_back, "heard back"), tile(f.conversations, "conversations"),
      tile(f.interviewing, "interviewing"), tile(f.offers, "offers"), tile(f.rejected, "rejected"),
      tile(f.ghosted, "ghosted"), tile(f.waiting, "still waiting"),
      tile(i.median_days_to_response === null ? "—" : `${i.median_days_to_response}d`, "median time to a response")),
    el("div", { class: "insights" },
      breakdownTable("By channel", i.by_channel, CHANNEL_LABELS),
      breakdownTable("By positioning", i.by_positioning, POSITIONING_LABELS),
      breakdownTable("By tier", i.by_tier, TIER_LABELS)));
}
```

- [ ] **Step 3: Verify** — `python3 -m unittest -q` OK; JS syntax check (Task 4 command) passes.
- [ ] **Step 4: Commit** — `git commit -am "job-search: cockpit Pipeline and Insights tabs"`

---

### Task 6: Browser smoke test, docs, retire the old tracker page

**Files:** `SKILL.md` (Job Radar section), `manifest.json` (1.20.0, `cockpit.py` + `test_cockpit.py`), `references/scheduled-runs.md` (unchanged unless wording mentions tabs); `~/Desktop/Job-Search/london-role-tracker.html` → `~/Desktop/Job-Search/retired/`.

- [ ] **Step 1: Serve a copy of the real state** (so clicking buttons can't touch real data):

```bash
SP=<scratchpad>; rm -rf $SP/state-copy && rsync -a --exclude .git ~/job-search-data/ $SP/state-copy/
JOB_SEARCH_DIR=$SP/state-copy python3 radar.py serve --port 8766 --no-open   # run in background
```

- [ ] **Step 2: Drive it with Playwright** (`mcp__playwright__browser_navigate` to `http://127.0.0.1:8766`), for each tab: snapshot + screenshot + `browser_console_messages` (expect no errors). Exercise: Today → Ignore one review item, "Followed up" on one follow-up, log a proof piece (tile goes 1/1); Pipeline → change a tier, confirm a positioning, open a row (history + contacts + copy button); Insights renders all three tables; Roles → "Save as… Tier 1" on one role, it appears in Pipeline with tier 1. Check the copy's `tracker.json` reflects each edit and the real `~/job-search-data` is unchanged (`git -C ~/job-search-data status --short` empty).
  Any defect: write a failing Python test if it's server-side, fix, re-run; JS defects: fix and re-run the same browser step.

- [ ] **Step 3: Docs.** `SKILL.md` Job Radar section: the page is now the Job Cockpit — Today (replies, emails to sort, follow-ups, automatic changes with Undo, weekly 3/2/1 + proof log), Roles (save as Tier 1/2), Pipeline (edit tier/channel/positioning/status, history, warm contacts, copy `/resume-tailor`), Insights (funnel, rates by channel/positioning/tier). `manifest.json`: version `1.20.0`; install entries for `scripts/cockpit.py` and `scripts/test_cockpit.py` (edit in place, keep the compact formatting). Run `npm run validate`.

- [ ] **Step 4: Retire the old page** (workspace repo):

```bash
cd ~/Desktop/Job-Search && mkdir -p retired && git mv london-role-tracker.html retired/ && git commit -m "Retire london-role-tracker.html — replaced by the Cockpit Pipeline tab"
```

- [ ] **Step 5: Commit** — `git commit -am "job-search: cockpit docs, manifest 1.20.0"`; stop the 8766 server.
