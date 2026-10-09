# Tracker v2 + Inbox Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the application tracker learnable (channel / tier / positioning / event history) and keep it in sync with Gmail automatically every morning, read-only.

**Architecture:** `job_tool.py` gains the v2 tracker schema (validation, status-change events, undo, ghosting, backfill migration). A new stdlib-only `inbox.py` reads Gmail over IMAP (EXAMINE + `BODY.PEEK`), classifies job emails with fixed rules, matches them to tracker rows, auto-applies only unambiguous matches and queues the rest for review. `radar.py daily` becomes the 07:00 launchd entry point (refresh, then inbox sync).

**Tech Stack:** Python ≥3.9 stdlib only (`imaplib`, `email`, `subprocess` → macOS `security`), `unittest` (run with `python3 -m unittest`; pytest is not installed for the launchd interpreter).

**Spec:** `docs/superpowers/specs/2026-10-09-job-search-cockpit-design.md` (this plan covers build steps 1–2; Today/Pipeline/Insights/Tier-1 helpers get their own plan once real inbox data has validated the classifier).

## Global Constraints

- Never submit applications or send email/messages. The mailbox is opened read-only; only `BODY.PEEK[...]` fetch items; no `STORE`, `COPY`, `MOVE`, `EXPUNGE`, `APPEND`.
- Stdlib only; launchd runs `/opt/homebrew/bin/python3`.
- State lives in `~/job-search-data/` via `job_tool.state_dir()` (`JOB_SEARCH_DIR` overrides it in tests). Never under `~/Desktop`.
- The app password lives in the macOS Keychain, service `job-search-imap`. Never written to disk or logs.
- Statuses: `Shortlisted, Applied, Responded, Phone Screen, Interviewing, Offer, Rejected, Ghosted, Withdrawn`.
- `channel` ∈ `easy_apply, ats, agency, referral, other`; `tier` ∈ `1, 2`; `positioning` ∈ `P1, P2, P3, P4`.
- Ghost after 21 days in `Applied`, and only after an inbox sync succeeded in the same run.
- All work in `tools/job-search/` of `~/GitHub/claude-code-tools` (symlinked as `~/.claude/skills`). Tests: `cd tools/job-search/scripts && python3 -m unittest -q`.

## Review Focus

1. **The mailbox must stay untouched**: no message marked read, moved or flagged. Test: `test_sync_only_peeks_and_never_mutates` (Task 5), `test_open_mailbox_is_read_only` (Task 6).
2. **Short or generic company names** ("Global", "Byte") appearing in an unrelated email body must never auto-change a row. Test: `test_body_only_company_mention_goes_to_review` (Task 4).
3. **Confirmation boilerplate that mentions interviews** ("we'll be in touch to arrange an interview") must classify as a confirmation, not an invite. Test: `test_confirmation_mentioning_interview_stays_confirmation` (Task 4).
4. **Missing Keychain item or failed login at 07:00**: the radar refresh still runs, the log says why, and no row is ghosted. Test: `test_daily_survives_inbox_failure_without_ghosting` (Task 6).
5. **Re-running or overlapping sync windows** must not duplicate events, review items or actions. Test: `test_resync_with_days_does_not_duplicate` (Task 5).

---

### Task 0: Baseline

**Files:** none new.

- [ ] **Step 1: Run the suite on the current working tree** (it has uncommitted radar work from 2026-10-04 — skill-fit scoring, title flags)

Run: `cd ~/GitHub/claude-code-tools/tools/job-search/scripts && python3 -m unittest -q`
Expected: `Ran 175 tests ... OK`

- [ ] **Step 2: Commit that work as-is, then branch**

```bash
cd ~/GitHub/claude-code-tools
git add tools/job-search/scripts/radar.py tools/job-search/scripts/radar.html tools/job-search/scripts/test_radar.py
git commit -m "job-search: radar skill-fit scoring and title flags"
git switch -c job-search/cockpit
git add docs/superpowers/specs/2026-10-09-job-search-cockpit-design.md docs/superpowers/plans/2026-10-09-job-search-tracker-v2-inbox-sync.md
git commit -m "docs: job-search cockpit design + tracker v2/inbox sync plan"
```

---

### Task 1: Tracker v2 schema — statuses, enums, status-change events

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (constants ~L186–200, `next_followup`, `compute_stale_reason`, `upsert_tracker_row`)
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Produces: `STATUS_ORDER`, `CHANNELS`, `POSITIONINGS`, `TIERS`, `FOLLOWUP_STATUSES`, `GHOST_AFTER_DAYS`;
  `validate_tracker_patch(patch) -> str | None`;
  `upsert_tracker_row(patch, source="manual", event=None, when=None) -> (row, err)`. A status change appends
  `{"date": when or today, "type": "status", "from": old, "to": new, "source": source}`; `event` is appended as
  `{"date": today, **event}`. Patching `positioning` sets `positioning_inferred: False`. New rows carry
  `channel/tier/positioning = None`, `events = []`.

- [ ] **Step 1: Write the failing tests** (add `import os` to the test imports)

```python
class TrackerStateMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class TestTrackerV2(TrackerStateMixin, unittest.TestCase):
    def test_rejects_unknown_enum_values(self):
        for patch_ in ({"status": "Ghosting"}, {"channel": "carrier pigeon"},
                       {"tier": 3}, {"positioning": "P9"}):
            with self.subTest(patch_=patch_):
                row, err = job_tool.upsert_tracker_row(dict(company="Acme", role="SWE", **patch_))
                self.assertIsNone(row)
                self.assertIn("invalid", err)

    def test_new_row_has_v2_fields(self):
        row, _ = job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE"})
        self.assertEqual((row["channel"], row["tier"], row["positioning"], row["events"]),
                         (None, None, None, []))

    def test_status_change_records_event(self):
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE"})
        row, _ = job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"},
                                             source="inbox", when="2026-10-01")
        self.assertEqual(row["events"][-1], {"date": "2026-10-01", "type": "status", "from": "Shortlisted",
                                             "to": "Applied", "source": "inbox"})

    def test_same_status_records_no_event(self):
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})
        row, _ = job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})
        self.assertEqual(sum(e["type"] == "status" for e in row["events"]), 1)

    def test_extra_event_is_appended(self):
        row, _ = job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE"},
                                             event={"type": "email", "kind": "viewed", "msg_id": "<1@x>"})
        self.assertEqual(row["events"][-1]["kind"], "viewed")
        self.assertIn("date", row["events"][-1])

    def test_setting_positioning_clears_inferred_flag(self):
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE"})
        data = job_tool.load_rows()
        data["rows"][0].update(positioning="P2", positioning_inferred=True)
        job_tool.save_rows(data)
        row, _ = job_tool.upsert_tracker_row({"id": 1, "positioning": "P1"})
        self.assertFalse(row["positioning_inferred"])

    def test_responded_counts_for_followups(self):
        row, _ = job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Responded",
                                              "followup_date": "2000-01-01"})
        self.assertIn("Follow-up was due", job_tool.compute_stale_reason(row))

    def test_markdown_has_new_columns(self):
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "tier": 1, "channel": "ats"})
        text = job_tool.markdown_path().read_text()
        self.assertIn("| Tier | Channel | Pos |", text)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest test_job_tool.TestTrackerV2 -q`
Expected: FAIL/ERROR (`upsert_tracker_row() got an unexpected keyword argument 'source'`, invalid values accepted).

- [ ] **Step 3: Implement**

Constants (replace `STATUS_ORDER`, add the rest beside it):

```python
STATUS_ORDER = [
    "Shortlisted", "Applied", "Responded", "Phone Screen", "Interviewing",
    "Offer", "Rejected", "Ghosted", "Withdrawn",
]
FOLLOWUP_STATUSES = ("Applied", "Responded", "Phone Screen", "Interviewing")
CHANNELS = ("easy_apply", "ats", "agency", "referral", "other")
POSITIONINGS = ("P1", "P2", "P3", "P4")
TIERS = (1, 2)
GHOST_AFTER_DAYS = 21
```

`TRACKER_COLUMNS`: insert `("tier", "Tier"), ("channel", "Channel"), ("positioning", "Pos")` right after `("status", "Status")`.

`next_followup`: `if status in ("Responded", "Phone Screen", "Interviewing"):`. `compute_stale_reason`: `if status in FOLLOWUP_STATUSES:`.

```python
def validate_tracker_patch(patch):
    for key, allowed in (("status", STATUS_ORDER), ("channel", CHANNELS),
                         ("positioning", POSITIONINGS), ("tier", TIERS)):
        if patch.get(key) is not None and patch[key] not in allowed:
            return f"invalid {key} {patch[key]!r}; expected one of {list(allowed)}"
    return None
```

`upsert_tracker_row(patch, source="manual", event=None, when=None)`: call `validate_tracker_patch` first; new-row dict adds `"channel": None, "tier": None, "positioning": None, "events": []`; remember `old_status = None` for new rows / `match["status"]` for matches; skip `"events"` as well as `"id"` when copying the patch; then

```python
    if "positioning" in patch:
        row["positioning_inferred"] = False

    events = row.setdefault("events", [])
    if "status" in patch:
        # existing applied_date / followup_date logic stays here
        if patch["status"] != old_status:
            events.append({"date": when or today_str(), "type": "status", "from": old_status,
                           "to": patch["status"], "source": source})
    if event:
        events.append({"date": today_str(), **event})
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest -q`
Expected: OK (radar's `save_posting` still calls `upsert_tracker_row(patch)` positionally — unchanged).

- [ ] **Step 5: Commit** — `git commit -am "job-search: tracker v2 statuses, enum validation, status events"`

---

### Task 2: Undo and ghosting

**Files:** Modify `job_tool.py` (after `upsert_tracker_row`); Test `test_job_tool.py`.

**Interfaces:**
- Produces: `undo_last_status(row_id) -> (row, err)` — reverts the latest status event only when its source is `inbox` or `auto`; `mark_ghosted(today=None) -> list[row]`.

- [ ] **Step 1: Failing tests**

```python
class TestUndoAndGhosting(TrackerStateMixin, unittest.TestCase):
    def test_undo_reverts_inbox_change(self):
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})
        job_tool.upsert_tracker_row({"id": 1, "status": "Rejected"}, source="inbox")
        row, err = job_tool.undo_last_status(1)
        self.assertIsNone(err)
        self.assertEqual(row["status"], "Applied")
        self.assertEqual(row["events"][-1]["source"], "undo")

    def test_undo_refuses_manual_change(self):
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})
        row, err = job_tool.undo_last_status(1)
        self.assertIsNone(row)
        self.assertIn("not automatic", err)

    def test_undo_unknown_row(self):
        self.assertEqual(job_tool.undo_last_status(99), (None, "no tracker row 99"))

    def test_ghosts_applied_rows_after_21_days(self):
        job_tool.upsert_tracker_row({"company": "Old", "role": "SWE", "status": "Applied",
                                     "applied_date": "2026-09-01"})
        job_tool.upsert_tracker_row({"company": "New", "role": "SWE", "status": "Applied",
                                     "applied_date": "2026-09-25"})
        job_tool.upsert_tracker_row({"company": "Talking", "role": "SWE", "status": "Responded",
                                     "applied_date": "2026-09-01"})
        ghosted = job_tool.mark_ghosted(date(2026, 10, 9))
        self.assertEqual([r["company"] for r in ghosted], ["Old"])
        old = job_tool.load_rows()["rows"][0]
        self.assertEqual((old["status"], old["events"][-1]["source"]), ("Ghosted", "auto"))
        self.assertEqual(job_tool.undo_last_status(1)[0]["status"], "Applied")
```

(Add `from datetime import date` to the test imports.)

- [ ] **Step 2: Run** `python3 -m unittest test_job_tool.TestUndoAndGhosting -q` — Expected: AttributeError.

- [ ] **Step 3: Implement**

```python
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
    row["events"].append({"date": today_str(), "type": "status", "from": last["to"],
                          "to": last["from"], "source": "undo"})
    save_rows(data)
    return row, None


def mark_ghosted(today=None):
    """Applied rows with no reply for GHOST_AFTER_DAYS become Ghosted. Only call this right after a
    successful inbox sync — otherwise a reply that was never read would be mistaken for silence."""
    today = today or date.today()
    data = load_rows()
    ghosted = []
    for row in data["rows"]:
        applied = parse_date(row.get("applied_date"))
        if row["status"] != "Applied" or not applied or (today - applied).days < GHOST_AFTER_DAYS:
            continue
        row["status"] = "Ghosted"
        row.setdefault("events", []).append({"date": today.isoformat(), "type": "status",
                                             "from": "Applied", "to": "Ghosted", "source": "auto"})
        ghosted.append(row)
    if ghosted:
        save_rows(data)
    return ghosted
```

- [ ] **Step 4: Run** `python3 -m unittest -q` — Expected: OK.
- [ ] **Step 5: Commit** — `git commit -am "job-search: undo automatic status changes, ghost silent applications"`

---

### Task 3: Backfill migration + CLI

**Files:** Modify `job_tool.py` (tracker section + argparse ~L1723 + usage docstring); Test `test_job_tool.py`.

**Interfaces:**
- Produces: `infer_channel(row) -> str | None`, `infer_positioning(role) -> str | None`, `backfill_events(row) -> list`,
  `migrate_tracker() -> {"channel": n, "positioning": n, "events": n}`; CLI `tracker migrate`, `tracker undo --id N`.

- [ ] **Step 1: Failing tests**

```python
class TestMigration(TrackerStateMixin, unittest.TestCase):
    def test_infer_channel(self):
        cases = [
            ({"notes": "LinkedIn Easy Apply (recruitment agency)"}, "agency"),
            ({"notes": "LinkedIn Easy Apply"}, "easy_apply"),
            ({"notes": "Workday confirmation"}, "ats"),
            ({"notes": None, "link": "https://jobs.ashbyhq.com/freetrade/x"}, "ats"),
            ({"notes": "Referred by Dana"}, "referral"),
            ({"notes": "Ask for referral first"}, None),
            ({"notes": "Confirmation from Global recruitment"}, None),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(job_tool.infer_channel(row), expected)

    def test_infer_positioning(self):
        cases = [
            ("AI Engineer", "P1"), ("Lead AI & Automation Engineer", "P1"), ("AI Enablement Engineer", "P1"),
            ("Platform Engineer", "P2"), ("Software Engineer, Test & Build Engineering", "P2"),
            ("AI Solutions Engineer", "P3"), ("Forward Deployed Engineer", "P3"),
            ("Product Manager - Payroll - UK", "P4"), ("Technical Program Manager", "P4"),
            ("Product Data Scientist (Data Labs)", None),
        ]
        for role, expected in cases:
            with self.subTest(role=role):
                self.assertEqual(job_tool.infer_positioning(role), expected)

    def _seed(self, rows):
        job_tool.save_json(job_tool.tracker_path(), {"next_id": len(rows) + 1, "rows": rows})

    def test_migrate_backfills_and_is_idempotent(self):
        self._seed([
            {"id": 1, "company": "Byte", "role": "AI Engineer", "status": "Applied",
             "applied_date": "2026-10-07", "notes": "LinkedIn Easy Apply", "link": None},
            {"id": 2, "company": "Freetrade", "role": "Platform Engineer", "status": "Rejected",
             "applied_date": "2026-10-01", "notes": "Ashby confirmation; rejection email 2026-10-08", "link": None},
            {"id": 3, "company": "Neo4j", "role": "SWE", "status": "Shortlisted", "positioning": "P2",
             "applied_date": None, "notes": None, "link": None},
        ])
        job_tool.migrate_tracker()
        rows = job_tool.load_rows()["rows"]
        self.assertEqual((rows[0]["channel"], rows[0]["positioning"], rows[0]["positioning_inferred"]),
                         ("easy_apply", "P1", True))
        self.assertEqual(rows[1]["events"][-1], {"date": "2026-10-08", "type": "status", "from": "Applied",
                                                 "to": "Rejected", "source": "migrate"})
        self.assertEqual((rows[2]["positioning"], rows[2].get("positioning_inferred")), ("P2", None))
        self.assertTrue(job_tool.tracker_path().with_name(f"tracker.json.bak-{job_tool.today_str()}").exists())
        before = job_tool.load_rows()
        job_tool.migrate_tracker()
        self.assertEqual(job_tool.load_rows(), before)
```

- [ ] **Step 2: Run** `python3 -m unittest test_job_tool.TestMigration -q` — Expected: AttributeError.

- [ ] **Step 3: Implement**

```python
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
    ("P3", re.compile(r"forward deployed|\bfde\b|solutions?\b|implementation|customer", re.I)),
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
```

CLI functions + argparse (after the `render` parser) + two usage lines in the module docstring
(`job_tool.py tracker migrate`, `job_tool.py tracker undo --id N`):

```python
def cmd_tracker_migrate(_args):
    print(json.dumps(migrate_tracker(), indent=2))


def cmd_tracker_undo(args):
    row, err = undo_last_status(args.id)
    if err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(row, indent=2))
```

```python
    tracker_sub.add_parser("migrate").set_defaults(func=cmd_tracker_migrate)
    p_undo = tracker_sub.add_parser("undo")
    p_undo.add_argument("--id", type=int, required=True)
    p_undo.set_defaults(func=cmd_tracker_undo)
```

- [ ] **Step 4: Run** `python3 -m unittest -q` — Expected: OK.
- [ ] **Step 5: Migrate the real tracker and show Yoav the result**

```bash
python3 job_tool.py tracker migrate
python3 -c "import json,collections;r=json.load(open('$HOME/job-search-data/tracker.json'))['rows'];print(collections.Counter(x['channel'] for x in r));print(collections.Counter(x['positioning'] for x in r))"
```
Expected: backup `tracker.json.bak-2026-10-09` exists; most rows have a channel; positioning mostly filled.

- [ ] **Step 6: Commit** — `git commit -am "job-search: tracker migrate (channel/positioning/events backfill) and undo CLI"`

---

### Task 4: `inbox.py` — classifier and matcher

**Files:** Create `tools/job-search/scripts/inbox.py`, `tools/job-search/scripts/test_inbox.py`.

**Interfaces:**
- Consumes: `job_tool.normalize_company`, `job_tool.clean_text`, `job_tool.today_str`.
- Produces: message dict `{"uid", "msg_id", "date", "sender", "subject", "body"}`;
  `parse_message(uid, raw, with_body=True) -> dict`; `classify(msg) -> "noise"|"rejection"|"viewed"|"interview"|"confirmation"|"reply"|"other"`;
  `match(msg, rows) -> (row|None, "strong"|"weak"|None, [row ids])`; `next_status(kind, current) -> str|None`;
  `decide(msg, kind, rows) -> {"type": "apply", "row_id", "status", "action": bool} | {"type": "review", "candidates": [...]} | {"type": "skip"}`;
  `is_candidate(head, company_words) -> bool`.

- [ ] **Step 1: Failing tests**

```python
import email.message
import unittest

import inbox


def make_raw(subject, sender, body, date="Wed, 08 Oct 2026 10:00:00 +0000", msg_id="<m1@x>"):
    m = email.message.EmailMessage()
    m["Subject"], m["From"], m["Date"], m["Message-ID"] = subject, sender, date, msg_id
    m.set_content(body)
    return m.as_bytes()


def msg(subject, sender="Acme Talent <talent@acme.com>", body=""):
    return {"uid": 1, "msg_id": "<m1@x>", "date": "2026-10-08", "sender": sender, "subject": subject, "body": body}


def row(id_, company, role="Software Engineer", status="Applied"):
    return {"id": id_, "company": company, "role": role, "status": status}


class TestParse(unittest.TestCase):
    def test_parse_message(self):
        m = inbox.parse_message(7, make_raw("Your application", "Acme <jobs@acme.com>", "Hello there"))
        self.assertEqual((m["uid"], m["msg_id"], m["date"], m["sender"], m["subject"]),
                         (7, "<m1@x>", "2026-10-08", "Acme <jobs@acme.com>", "Your application"))
        self.assertIn("Hello there", m["body"])

    def test_html_only_body_is_stripped(self):
        mm = email.message.EmailMessage()
        mm["Subject"], mm["From"], mm["Date"] = "Hi", "a@b.com", "Wed, 08 Oct 2026 10:00:00 +0000"
        mm.set_content("<p>We regret to inform you</p>", subtype="html")
        self.assertIn("We regret to inform you", inbox.parse_message(1, mm.as_bytes())["body"])
        self.assertNotIn("<p>", inbox.parse_message(1, mm.as_bytes())["body"])


class TestClassify(unittest.TestCase):
    CASES = [
        ("Your application to Acme", "Unfortunately we have decided to move forward with other candidates.", "rejection"),
        ("Update on your application", "We will not be progressing your application at this time.", "rejection"),
        ("Thank you for applying to Acme", "We have received your application and will review it.", "confirmation"),
        ("Your application was sent to Acme", "", "confirmation"),
        ("Your application was viewed by Acme", "", "viewed"),
        ("Next steps", "We'd love to invite you to a first interview. Please book a time via calendly.com/acme", "interview"),
        ("Acme - interview", "Could you share your availability for next week?", "interview"),
        ("Job alert: AI Engineer in London", "Acme is hiring", "noise"),
        ("Jobs you may be interested in", "Acme, Byte", "noise"),
    ]

    def test_cases(self):
        for subject, body, expected in self.CASES:
            with self.subTest(subject=subject):
                self.assertEqual(inbox.classify(msg(subject, body=body)), expected)

    def test_confirmation_mentioning_interview_stays_confirmation(self):
        body = ("Thank you for your application. If your experience matches, we'll be in touch "
                "to arrange an interview.")
        self.assertEqual(inbox.classify(msg("Application received", body=body)), "confirmation")

    def test_human_vs_automated_unclassified(self):
        self.assertEqual(inbox.classify(msg("Quick question", "Dana <dana@acme.com>", "Notice period?")), "reply")
        self.assertEqual(inbox.classify(msg("Update", "no-reply@acme.com", "Profile tips")), "other")

    def test_linkedin_message_is_reply(self):
        m = msg("Dana sent you a new message", "LinkedIn <messages-noreply@linkedin.com>", "")
        self.assertEqual(inbox.classify(m), "reply")


class TestMatch(unittest.TestCase):
    def test_sender_names_company(self):
        r, strength, ids = inbox.match(msg("Your application", "Freetrade Hiring <no-reply@ashbyhq.com>"),
                                       [row(1, "Freetrade"), row(2, "Byte")])
        self.assertEqual((r["id"], strength, ids), (1, "strong", [1]))

    def test_subject_names_company(self):
        r, strength, _ = inbox.match(msg("Your application to Cboe Global Markets", "noreply@myworkday.com"),
                                     [row(1, "Cboe")])
        self.assertEqual((r["id"], strength), (1, "strong"))

    def test_body_only_company_mention_goes_to_review(self):
        m = msg("Your application", "Talent <talent@acme.com>", "We work with global brands.")
        r, strength, ids = inbox.match(m, [row(5, "Global", "Python Developer")])
        self.assertEqual((r, strength, ids), (None, "weak", [5]))
        self.assertEqual(inbox.decide(m, "rejection", [row(5, "Global", "Python Developer")])["type"], "review")

    def test_word_boundaries(self):
        r, strength, _ = inbox.match(msg("Metabase newsletter", "news@metabase.com"), [row(1, "Meta")])
        self.assertEqual((r, strength), (None, None))

    def test_two_roles_same_company_disambiguated_by_role(self):
        rows = [row(1, "Acme", "Platform Engineer"), row(2, "Acme", "AI Solutions Engineer")]
        r, strength, _ = inbox.match(msg("Your application for AI Solutions Engineer at Acme"), rows)
        self.assertEqual((r["id"], strength), (2, "strong"))
        r, strength, ids = inbox.match(msg("Your application at Acme"), rows)
        self.assertEqual((r, strength, ids), (None, "weak", [1, 2]))

    def test_withdrawn_rows_ignored(self):
        self.assertEqual(inbox.match(msg("Hi"), [row(1, "Acme", status="Withdrawn")])[1], None)


class TestDecide(unittest.TestCase):
    def test_next_status(self):
        self.assertEqual(inbox.next_status("confirmation", "Shortlisted"), "Applied")
        self.assertIsNone(inbox.next_status("confirmation", "Applied"))
        self.assertEqual(inbox.next_status("rejection", "Ghosted"), "Rejected")
        self.assertIsNone(inbox.next_status("rejection", "Offer"))
        self.assertEqual(inbox.next_status("interview", "Applied"), "Responded")
        self.assertIsNone(inbox.next_status("interview", "Interviewing"))
        self.assertIsNone(inbox.next_status("viewed", "Applied"))

    def test_strong_interview_is_applied_with_action(self):
        d = inbox.decide(msg("Interview with Acme"), "interview", [row(1, "Acme")])
        self.assertEqual(d, {"type": "apply", "row_id": 1, "status": "Responded", "action": True})

    def test_unmatched_reply_and_other_are_skipped(self):
        self.assertEqual(inbox.decide(msg("Hi", "x@y.com"), "reply", [row(1, "Acme")]), {"type": "skip"})
        self.assertEqual(inbox.decide(msg("Hi"), "other", [row(1, "Acme")]), {"type": "skip"})

    def test_unmatched_confirmation_goes_to_review(self):
        d = inbox.decide(msg("Thanks for applying", "jobs@unknown.io"), "confirmation", [row(1, "Acme")])
        self.assertEqual(d, {"type": "review", "candidates": []})


class TestCandidateFilter(unittest.TestCase):
    def test_filters(self):
        words = [["freetrade"]]
        self.assertTrue(inbox.is_candidate(msg("Your application", "x@y.com"), words))
        self.assertTrue(inbox.is_candidate(msg("Hello", "Freetrade <hi@freetrade.io>"), words))
        self.assertTrue(inbox.is_candidate(msg("Hello", "no-reply@us.greenhouse-mail.io"), words))
        self.assertFalse(inbox.is_candidate(msg("Job alert: 30 new jobs", "jobalerts-noreply@linkedin.com"), words))
        self.assertFalse(inbox.is_candidate(msg("Your Ocado order", "orders@ocado.com"), words))
```

- [ ] **Step 2: Run** `python3 -m unittest test_inbox -q` — Expected: `ModuleNotFoundError: No module named 'inbox'`.

- [ ] **Step 3: Implement `inbox.py` (part 1)**

```python
#!/usr/bin/env python3
"""
Inbox sync: reads Gmail over IMAP (read-only) and keeps the application tracker in step with what
employers actually sent — confirmations, rejections, interview invites, recruiter replies.

Usage:
  inbox.py setup                          check the Keychain credential and the IMAP login
  inbox.py sync [--days N] [--dry-run]    process new mail (first run looks back 30 days)
  inbox.py review                         emails waiting for a decision
  inbox.py resolve <msg_id> (--row ID | --ignore)
  inbox.py actions [--all]                replies and invites that need an answer from you
  inbox.py done <msg_id>                  mark an action handled
  inbox.py undo <row_id>                  revert the last automatic status change on a row

Only unambiguous matches change the tracker (confirmation → Applied, rejection → Rejected,
invite/reply → Responded + an action item). Anything uncertain lands in the review queue.

Safety: the mailbox is opened with EXAMINE (read-only) and bodies are fetched with BODY.PEEK, so
nothing is marked read, moved, deleted or sent. The app password lives in the macOS Keychain.
"""

import argparse
import email
import email.policy
import email.utils
import imaplib
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import job_tool

KEYCHAIN_SERVICE = "job-search-imap"
IMAP_HOST = "imap.gmail.com"
MAILBOX = '"[Gmail]/All Mail"'
FIRST_SYNC_DAYS = 30
FETCH_BATCH = 200
BODY_CHARS = 6000
HEADER_PART = "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]"
FULL_PART = "BODY.PEEK[]"

ACTION_KINDS = ("interview", "reply")
REVIEW_KINDS = ("confirmation", "rejection", "interview")
ROLE_STOPWORDS = {"senior", "junior", "lead", "engineer", "engineering", "the", "and", "of", "for", "a",
                  "uk", "london", "remote", "hybrid", "i", "ii", "iii"}

NOISE_SUBJECT_RE = re.compile(
    r"job alert|jobs? you may be interested|new jobs? (for you|match|in)|recommended (jobs|for you)|"
    r"jobs? similar to|is hiring|are hiring|top job picks|newsletter|webinar|people also (viewed|applied)", re.I)
JOB_HINT_RE = re.compile(
    r"applica|applying|applied|interview|candida|position|\brole\b|opportunit|recruit|talent|hiring|"
    r"career|offer|assessment", re.I)
ATS_SENDER_RE = re.compile(
    r"greenhouse|lever\.co|ashbyhq|workable|teamtailor|workday|smartrecruiters|recruitee|gem\.com|"
    r"comeet|bamboohr|personio|hibob|jobvite|icims|successfactors|linkedin", re.I)
NOREPLY_RE = re.compile(r"no-?reply|do-?not-?reply|notification|mailer|automated", re.I)

REJECTION_RE = re.compile(
    r"unfortunately|regret to inform|not (be )?(moving|move|progress\w*|proceed\w*) (forward|further|ahead)|"
    r"(decided|chosen) to (move|proceed|progress|go) (forward |ahead )?with other|other candidates (whose|who)|"
    r"will not be (progressing|proceeding|taking)|not been successful|unsuccessful|"
    r"position has (now )?been filled|no longer (being )?consider|not (been )?selected", re.I)
VIEWED_RE = re.compile(r"application was viewed|viewed your application", re.I)
INVITE_RE = re.compile(
    r"(like|love|pleased|happy|keen) to (invite|schedule|arrange|set up|book|speak|chat|move you forward|progress)|"
    r"invite you to|book (a|some) time|calendly\.com|cal\.com/|your availability|"
    r"when (are|would) you (be )?(free|available)|available for a (quick )?(call|chat)", re.I)
CONFIRM_RE = re.compile(
    r"thank(s| you) for (your )?(applying|application|interest in)|"
    r"application (has been |was )?(received|submitted)|(we've|we have) received your application|"
    r"your application (was sent|to|for|has been)|application confirmation|successfully applied", re.I)
INTERVIEW_RE = re.compile(
    r"\binterview|phone screen|screening call|intro(ductory)? call|next stage|take-home|"
    r"technical (assessment|test)|coding (test|challenge)|hackerrank|codility", re.I)
LINKEDIN_MESSAGE_RE = re.compile(r"sent you a (new )?message|new message from|\binmail\b", re.I)


# ---- parsing ----------------------------------------------------------------

def parse_message(uid, raw, with_body=True):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    try:
        sent = email.utils.parsedate_to_datetime(str(msg["Date"])).date().isoformat()
    except (TypeError, ValueError):
        sent = job_tool.today_str()
    return {
        "uid": uid,
        "msg_id": str(msg["Message-ID"] or f"<uid-{uid}>").strip(),
        "date": sent,
        "sender": " ".join(str(msg["From"] or "").split()),
        "subject": " ".join(str(msg["Subject"] or "").split()),
        "body": message_text(msg)[:BODY_CHARS] if with_body else "",
    }


def message_text(msg):
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        text = part.get_content()
        return job_tool.clean_text(text) if part.get_content_subtype() == "html" else text
    except (KeyError, LookupError, ValueError):
        return ""


# ---- classify + match -------------------------------------------------------

def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _contains(words, seq):
    n = len(seq)
    return n > 0 and any(words[i:i + n] == seq for i in range(len(words) - n + 1))


def is_candidate(head, company_words):
    """Cheap header-only filter deciding which messages are worth downloading in full."""
    if NOISE_SUBJECT_RE.search(head["subject"]):
        return False
    if JOB_HINT_RE.search(head["subject"]) or ATS_SENDER_RE.search(head["sender"]):
        return True
    words = _words(f"{head['sender']} {head['subject']}")
    return any(_contains(words, cw) for cw in company_words)


def classify(msg):
    """Order matters: rejections often open with "thank you for applying", and confirmations often
    mention a future interview, so a confirmation only loses to an explicit invitation."""
    text = f"{msg['subject']}\n{msg['body']}"
    if NOISE_SUBJECT_RE.search(msg["subject"]):
        return "noise"
    if REJECTION_RE.search(text):
        return "rejection"
    if VIEWED_RE.search(text):
        return "viewed"
    if INVITE_RE.search(text):
        return "interview"
    if CONFIRM_RE.search(text):
        return "confirmation"
    if INTERVIEW_RE.search(text):
        return "interview"
    if LINKEDIN_MESSAGE_RE.search(msg["subject"]) or not NOREPLY_RE.search(msg["sender"]):
        return "reply"
    return "other"


def _by_role(rows, words):
    present = set(words)

    def score(r):
        role = [w for w in _words(r["role"]) if w not in ROLE_STOPWORDS]
        return sum(w in present for w in role) / len(role) if role else 0

    scored = sorted(((score(r), r) for r in rows), key=lambda x: -x[0])
    if scored[0][0] >= 0.6 and scored[0][0] > scored[1][0]:
        return [scored[0][1]]
    return rows


def match(msg, rows):
    """'strong' = the company is named by the sender or subject and exactly one row fits; 'weak' =
    named only in the body, or several rows fit. Only strong matches ever change the tracker."""
    head = _words(f"{msg['sender']} {msg['subject']}")
    body = _words(msg["body"])
    strong, weak = [], []
    for r in rows:
        if r.get("status") == "Withdrawn":
            continue
        cw = job_tool.normalize_company(r["company"])
        if _contains(head, cw):
            strong.append(r)
        elif _contains(body, cw):
            weak.append(r)
    if len(strong) > 1:
        strong = _by_role(strong, head + body)
    if len(strong) == 1:
        return strong[0], "strong", [strong[0]["id"]]
    candidates = strong or weak
    if candidates:
        return None, "weak", [r["id"] for r in candidates]
    return None, None, []


def next_status(kind, current):
    if kind == "confirmation" and current == "Shortlisted":
        return "Applied"
    if kind == "rejection" and current not in ("Rejected", "Withdrawn", "Offer"):
        return "Rejected"
    if kind in ACTION_KINDS and current in ("Shortlisted", "Applied", "Ghosted"):
        return "Responded"
    return None


def decide(msg, kind, rows):
    if kind in ("noise", "other"):
        return {"type": "skip"}
    found, strength, candidates = match(msg, rows)
    if strength == "strong":
        return {"type": "apply", "row_id": found["id"], "status": next_status(kind, found["status"]),
                "action": kind in ACTION_KINDS}
    if candidates or kind in REVIEW_KINDS:
        return {"type": "review", "candidates": candidates}
    return {"type": "skip"}
```

- [ ] **Step 4: Run** `python3 -m unittest test_inbox -q` — Expected: OK. Fix regexes (not tests) on any failure.
- [ ] **Step 5: Commit** — `git add scripts/inbox.py scripts/test_inbox.py && git commit -m "job-search: inbox email classifier and tracker matcher"`

---

### Task 5: `inbox.py` — sync engine, state, review/actions

**Files:** Modify `inbox.py`, `test_inbox.py`.

**Interfaces:**
- Consumes: Task 1–2 `upsert_tracker_row(patch, source, event, when)`, `mark_ghosted(today)`, `load_rows()`.
- Produces: `state_path()`, `load_state() -> {"uidvalidity", "last_uid", "last_sync", "review": [], "actions": []}`;
  `sync(conn, today=None, days=None, dry_run=False) -> {"scanned", "candidates", "applied": [...], "review": [...], "actions": [...], "ghosted": [ids]}`;
  `apply_to_row(row_id, item, kind, status) -> (row, err)`; `resolve(msg_id, row_id=None) -> (result, err)`; `mark_done(msg_id) -> (item, err)`.
  `conn` needs only `.response(code)` and `.uid("SEARCH"|"FETCH", ...)`.

- [ ] **Step 1: Failing tests**

```python
import os
import tempfile
from datetime import date
from unittest.mock import patch

import job_tool


class FakeIMAP:
    """Stands in for an already-selected imaplib connection. Any mutating command fails the test."""

    def __init__(self, messages, uidvalidity=1):
        self.messages, self.uidvalidity, self.calls = dict(messages), uidvalidity, []

    def response(self, code):
        return code, [str(self.uidvalidity).encode()]

    def uid(self, command, *args):
        self.calls.append((command,) + args)
        if command == "SEARCH":
            if args[1] == "UID":
                lo = int(args[2].split(":")[0])
                found = [u for u in self.messages if u >= lo] or [max(self.messages)]
            else:
                found = list(self.messages)
            return "OK", [" ".join(map(str, sorted(found))).encode()]
        if command == "FETCH":
            assert "PEEK" in args[1], args[1]
            data = []
            for u in map(int, args[0].split(",")):
                raw = self.messages[u]
                payload = raw.split(b"\n\n", 1)[0] + b"\n\n" if "HEADER" in args[1] else raw
                data += [(f"{u} (UID {u} BODY[] {{{len(payload)}}}".encode(), payload), b")"]
            return "OK", data
        raise AssertionError(f"unexpected UID {command}")

    def store(self, *a): raise AssertionError("store")
    def copy(self, *a): raise AssertionError("copy")
    def expunge(self, *a): raise AssertionError("expunge")
    def append(self, *a): raise AssertionError("append")


TODAY = date(2026, 10, 9)


class TestSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        for company, role, status, applied in [("Freetrade", "Platform Engineer", "Applied", "2026-10-08"),
                                               ("Neo4j", "Software Engineer", "Shortlisted", None),
                                               ("Global", "Python Developer", "Applied", "2026-10-08"),
                                               ("Client Server", "AI Engineer", "Applied", "2026-09-15")]:
            job_tool.upsert_tracker_row({"company": company, "role": role, "status": status,
                                         "applied_date": applied})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def rows(self):
        return {r["company"]: r for r in job_tool.load_rows()["rows"]}

    def mailbox(self):
        return FakeIMAP({
            101: make_raw("Your application to Freetrade", "Freetrade <no-reply@ashbyhq.com>",
                          "Unfortunately we have decided to move forward with other candidates.", msg_id="<r@x>"),
            102: make_raw("Thank you for applying to Neo4j", "Neo4j Careers <no-reply@greenhouse.io>",
                          "We have received your application.", date="Tue, 07 Oct 2026 09:00:00 +0000",
                          msg_id="<c@x>"),
            103: make_raw("Job alert: 25 new jobs for you", "LinkedIn <jobalerts-noreply@linkedin.com>",
                          "Freetrade is hiring", msg_id="<n@x>"),
            104: make_raw("Your application", "Talent <talent@agency.co>",
                          "Unfortunately the global client has paused hiring.", msg_id="<w@x>"),
            105: make_raw("Your Ocado order", "orders@ocado.com", "Delivered", msg_id="<o@x>"),
        })

    def test_sync_applies_strong_matches_and_queues_the_rest(self):
        summary = inbox.sync(self.mailbox(), today=TODAY)
        rows = self.rows()
        self.assertEqual(rows["Freetrade"]["status"], "Rejected")
        self.assertEqual(rows["Freetrade"]["events"][-1]["msg_id"], "<r@x>")
        self.assertEqual((rows["Neo4j"]["status"], rows["Neo4j"]["applied_date"]), ("Applied", "2026-10-07"))
        self.assertEqual(rows["Global"]["status"], "Applied")
        self.assertEqual([i["msg_id"] for i in inbox.load_state()["review"]], ["<w@x>"])
        self.assertEqual(summary["scanned"], 5)
        self.assertEqual(summary["candidates"], 3)
        self.assertEqual(inbox.load_state()["last_uid"], 105)

    def test_sync_only_peeks_and_never_mutates(self):
        box = self.mailbox()
        inbox.sync(box, today=TODAY)
        self.assertTrue(all(c[0] in ("SEARCH", "FETCH") for c in box.calls))
        self.assertTrue(all("BODY.PEEK" in c[2] for c in box.calls if c[0] == "FETCH"))

    def test_interview_creates_action_and_responded(self):
        box = FakeIMAP({201: make_raw("Global - next steps", "Sam at Global <sam@global.com>",
                                      "We'd love to invite you to an interview.", msg_id="<i@x>")})
        inbox.sync(box, today=TODAY)
        self.assertEqual(self.rows()["Global"]["status"], "Responded")
        self.assertEqual([(a["msg_id"], a["done"]) for a in inbox.load_state()["actions"]], [("<i@x>", False)])

    def test_second_sync_only_reads_new_uids(self):
        inbox.sync(self.mailbox(), today=TODAY)
        box = self.mailbox()
        summary = inbox.sync(box, today=TODAY)
        self.assertEqual(box.calls[0][1:], (None, "UID", "106:*"))
        self.assertEqual(summary["scanned"], 0)

    def test_resync_with_days_does_not_duplicate(self):
        inbox.sync(self.mailbox(), today=TODAY)
        inbox.sync(self.mailbox(), today=TODAY, days=30)
        rows = self.rows()
        self.assertEqual(sum(e.get("msg_id") == "<r@x>" for e in rows["Freetrade"]["events"]), 1)
        self.assertEqual(len(inbox.load_state()["review"]), 1)

    def test_uidvalidity_change_rescans_window(self):
        inbox.sync(self.mailbox(), today=TODAY)
        box = FakeIMAP({1: make_raw("Hello", "a@b.com", "", msg_id="<z@x>")}, uidvalidity=2)
        inbox.sync(box, today=TODAY)
        self.assertEqual(box.calls[0][1:], (None, "SINCE", "09-Sep-2026"))

    def test_dry_run_writes_nothing(self):
        before = job_tool.load_rows()
        summary = inbox.sync(self.mailbox(), today=TODAY, dry_run=True)
        self.assertEqual(job_tool.load_rows(), before)
        self.assertFalse(inbox.state_path().exists())
        self.assertEqual(len(summary["applied"]), 2)

    def test_ghosting_runs_after_successful_sync(self):
        summary = inbox.sync(FakeIMAP({1: make_raw("Hello", "a@b.com", "", msg_id="<z@x>")}), today=TODAY)
        self.assertEqual(self.rows()["Client Server"]["status"], "Ghosted")
        self.assertEqual(len(summary["ghosted"]), 1)

    def test_resolve_attaches_review_item_to_row(self):
        inbox.sync(self.mailbox(), today=TODAY)
        global_id = self.rows()["Global"]["id"]
        _, err = inbox.resolve("<w@x>", global_id)
        self.assertIsNone(err)
        self.assertEqual(self.rows()["Global"]["status"], "Rejected")
        self.assertEqual(inbox.load_state()["review"], [])

    def test_resolve_ignore_and_unknown(self):
        inbox.sync(self.mailbox(), today=TODAY)
        self.assertEqual(inbox.resolve("<w@x>")[0], {"dropped": "<w@x>"})
        self.assertEqual(inbox.resolve("<nope@x>"), (None, "no review item <nope@x>"))

    def test_mark_done(self):
        box = FakeIMAP({201: make_raw("Global - next steps", "Sam at Global <sam@global.com>",
                                      "Could you share your availability?", msg_id="<i@x>")})
        inbox.sync(box, today=TODAY)
        item, err = inbox.mark_done("<i@x>")
        self.assertTrue(item["done"])
```

- [ ] **Step 2: Run** `python3 -m unittest test_inbox.TestSync -q` — Expected: AttributeError (`sync`).

- [ ] **Step 3: Implement (append to `inbox.py`)**

```python
# ---- state ------------------------------------------------------------------

def state_path():
    return job_tool.state_dir() / "inbox_state.json"


def load_state():
    state = job_tool.load_json(state_path(), {})
    for key, default in (("uidvalidity", None), ("last_uid", 0), ("last_sync", None),
                         ("review", []), ("actions", [])):
        state.setdefault(key, default)
    return state


def _known_msg_ids(rows, state):
    known = {e.get("msg_id") for r in rows for e in r.get("events") or []}
    known |= {i["msg_id"] for i in state["review"] + state["actions"]}
    known.discard(None)
    return known


# ---- IMAP -------------------------------------------------------------------

def _check(typ, data, what):
    if typ != "OK":
        raise RuntimeError(f"IMAP {what} failed: {data!r}")


def _uidvalidity(conn):
    _, data = conn.response("UIDVALIDITY")
    return int(data[0]) if data and data[0] else None


def search_uids(conn, state, days, today):
    validity = _uidvalidity(conn)
    if validity != state["uidvalidity"]:
        state["uidvalidity"], state["last_uid"] = validity, 0
    incremental = bool(state["last_uid"]) and days is None
    if incremental:
        typ, data = conn.uid("SEARCH", None, "UID", f"{state['last_uid'] + 1}:*")
    else:
        since = (today - timedelta(days=days or FIRST_SYNC_DAYS)).strftime("%d-%b-%Y")
        typ, data = conn.uid("SEARCH", None, "SINCE", since)
    _check(typ, data, "SEARCH")
    uids = sorted(int(u) for u in (data[0] or b"").split())
    # "UID n:*" always returns the newest message even when it is older than n.
    return [u for u in uids if u > state["last_uid"]] if incremental else uids


def fetch(conn, uids, part):
    """UID FETCH in batches, yielding (uid, raw bytes) in UID order. `part` is always a BODY.PEEK
    item so the \\Seen flag is never set."""
    out = []
    for i in range(0, len(uids), FETCH_BATCH):
        batch = uids[i:i + FETCH_BATCH]
        typ, data = conn.uid("FETCH", ",".join(map(str, batch)), f"(UID {part})")
        _check(typ, data, "FETCH")
        for item in data:
            if isinstance(item, tuple):
                m = re.search(rb"UID (\d+)", item[0])
                if m:
                    out.append((int(m.group(1)), item[1]))
    return sorted(out)


# ---- sync -------------------------------------------------------------------

def apply_to_row(row_id, item, kind, status):
    patch = {"id": row_id}
    if status:
        patch["status"] = status
        if status == "Applied":
            patch["applied_date"] = item["date"]
    event = {"date": item["date"], "type": "email", "kind": kind, "subject": item["subject"][:140],
             "msg_id": item["msg_id"], "source": "inbox"}
    return job_tool.upsert_tracker_row(patch, source="inbox", event=event, when=item["date"])


def sync(conn, today=None, days=None, dry_run=False):
    today = today or date.today()
    state = load_state()
    rows = job_tool.load_rows()["rows"]
    uids = search_uids(conn, state, days, today)
    company_words = [job_tool.normalize_company(r["company"]) for r in rows]
    heads = [parse_message(uid, raw, with_body=False) for uid, raw in fetch(conn, uids, HEADER_PART)]
    wanted = [h["uid"] for h in heads if is_candidate(h, company_words)]
    summary = {"scanned": len(heads), "candidates": len(wanted), "applied": [], "review": [],
               "actions": [], "ghosted": []}
    known = _known_msg_ids(rows, state)

    for uid, raw in fetch(conn, wanted, FULL_PART):
        msg = parse_message(uid, raw)
        if msg["msg_id"] in known:
            continue
        known.add(msg["msg_id"])
        kind = classify(msg)
        decision = decide(msg, kind, rows)
        record = {k: msg[k] for k in ("msg_id", "date", "sender", "subject")}
        record["kind"] = kind
        if decision["type"] == "apply":
            summary["applied"].append(dict(record, row_id=decision["row_id"], status=decision["status"]))
            if decision["action"]:
                summary["actions"].append(dict(record, row_id=decision["row_id"], done=False))
            if not dry_run:
                apply_to_row(decision["row_id"], msg, kind, decision["status"])
                rows = job_tool.load_rows()["rows"]
        elif decision["type"] == "review":
            summary["review"].append(dict(record, candidates=decision["candidates"],
                                          snippet=" ".join(msg["body"].split())[:300]))

    if dry_run:
        return summary
    if uids:
        state["last_uid"] = max(state["last_uid"], uids[-1])
    state["last_sync"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["review"] += summary["review"]
    state["actions"] += summary["actions"]
    job_tool.save_json(state_path(), state)
    summary["ghosted"] = [r["id"] for r in job_tool.mark_ghosted(today)]
    return summary


def resolve(msg_id, row_id=None):
    """Settle a review item: attach it to tracker row `row_id`, or drop it when row_id is None."""
    state = load_state()
    item = next((i for i in state["review"] if i["msg_id"] == msg_id), None)
    if item is None:
        return None, f"no review item {msg_id}"
    result = {"dropped": msg_id}
    if row_id is not None:
        found = next((r for r in job_tool.load_rows()["rows"] if r["id"] == row_id), None)
        if found is None:
            return None, f"no tracker row {row_id}"
        result, err = apply_to_row(row_id, item, item["kind"], next_status(item["kind"], found["status"]))
        if err:
            return None, err
        if item["kind"] in ACTION_KINDS:
            action = {k: item[k] for k in ("msg_id", "date", "sender", "subject", "kind")}
            state["actions"].append(dict(action, row_id=row_id, done=False))
    state["review"].remove(item)
    job_tool.save_json(state_path(), state)
    return result, None


def mark_done(msg_id):
    state = load_state()
    item = next((a for a in state["actions"] if a["msg_id"] == msg_id), None)
    if item is None:
        return None, f"no action {msg_id}"
    item["done"] = True
    job_tool.save_json(state_path(), state)
    return item, None
```

- [ ] **Step 4: Run** `python3 -m unittest -q` — Expected: OK.
- [ ] **Step 5: Commit** — `git commit -am "job-search: inbox sync engine with review queue and actions"`

---

### Task 6: Credentials, CLI, `radar.py daily`, launchd, docs

**Files:** Modify `inbox.py`, `test_inbox.py`, `radar.py` (`import inbox`, `cmd_daily`, argparse), `test_radar.py`, `manifest.json`, `SKILL.md` (status list ~L685, new "Inbox sync" section), `references/scheduled-runs.md`; `~/Library/LaunchAgents/com.yoavsborovsky.jobradar.plist` (outside repo).

**Interfaces:**
- Produces: `get_credentials() -> ((user, password) | None, err | None)`; `open_mailbox(user, password)` (selects `MAILBOX` with `readonly=True`);
  `run_sync(days=None, dry_run=False) -> summary` (raises `RuntimeError` on missing credentials); `format_summary(summary) -> str`; `radar.py daily`.

- [ ] **Step 1: Failing tests**

`test_inbox.py`:

```python
from unittest.mock import MagicMock


class TestCredentialsAndConnect(unittest.TestCase):
    def test_reads_keychain(self):
        meta = MagicMock(stdout='keychain: "x"\n    "acct"<blob>="me@gmail.com"\n')
        secret = MagicMock(stdout="abcd efgh ijkl mnop\n")
        with patch("inbox.subprocess.run", side_effect=[meta, secret]):
            self.assertEqual(inbox.get_credentials(), (("me@gmail.com", "abcd efgh ijkl mnop"), None))

    def test_missing_keychain_item(self):
        with patch("inbox.subprocess.run", side_effect=subprocess.CalledProcessError(44, "security")):
            creds, err = inbox.get_credentials()
        self.assertIsNone(creds)
        self.assertIn("inbox.py setup", err)

    def test_open_mailbox_is_read_only(self):
        fake = MagicMock()
        fake.select.return_value = ("OK", [b"12"])
        with patch("inbox.imaplib.IMAP4_SSL", return_value=fake):
            inbox.open_mailbox("me@gmail.com", "pw")
        fake.select.assert_called_once_with(inbox.MAILBOX, readonly=True)

    def test_format_summary(self):
        text = inbox.format_summary({"scanned": 5, "candidates": 3, "ghosted": [4],
                                     "applied": [{"subject": "Re", "kind": "rejection", "row_id": 1, "status": "Rejected"}],
                                     "review": [{"subject": "Hm", "kind": "rejection", "msg_id": "<w@x>"}],
                                     "actions": []})
        self.assertIn("1 tracker update", text)
        self.assertIn("1 to review", text)
```

(Add `import subprocess` to test imports.)

`test_radar.py`:

```python
class TestDaily(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        radar.job_tool.upsert_tracker_row({"company": "Old", "role": "SWE", "status": "Applied",
                                           "applied_date": "2026-01-01"})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_daily_survives_inbox_failure_without_ghosting(self):
        args = radar.argparse.Namespace(no_linkedin=True, max_details=0)
        with patch("radar.cmd_refresh") as refresh, \
             patch("radar.inbox.get_credentials", return_value=(None, "no Keychain item")):
            radar.cmd_daily(args)
        refresh.assert_called_once()
        self.assertEqual(radar.job_tool.load_rows()["rows"][0]["status"], "Applied")

    def test_daily_runs_inbox_even_if_refresh_fails(self):
        args = radar.argparse.Namespace(no_linkedin=True, max_details=0)
        with patch("radar.cmd_refresh", side_effect=RuntimeError("boom")), \
             patch("radar.inbox.run_sync", return_value={"scanned": 0, "candidates": 0, "applied": [],
                                                          "review": [], "actions": [], "ghosted": []}) as sync:
            radar.cmd_daily(args)
        sync.assert_called_once()
```

- [ ] **Step 2: Run** `python3 -m unittest -q` — Expected: failures for the new tests.

- [ ] **Step 3: Implement**

`inbox.py`:

```python
SETUP_HELP = f"""One-off setup (2 minutes):
  1. Google Account > Security > 2-Step Verification must be on.
  2. https://myaccount.google.com/apppasswords > create one called "job-search".
  3. Store it in the Keychain (it prompts for the password, nothing lands in shell history):
       security add-generic-password -U -s {KEYCHAIN_SERVICE} -a <you>@gmail.com -w
  4. Check it: python3 inbox.py setup"""


def get_credentials():
    try:
        meta = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                              capture_output=True, text=True, check=True).stdout
        password = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                                  capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, f"no Keychain item '{KEYCHAIN_SERVICE}' — run `inbox.py setup` for instructions"
    m = re.search(r'"acct"<blob>="([^"]*)"', meta)
    if not m or not password:
        return None, f"Keychain item '{KEYCHAIN_SERVICE}' has no account or password"
    return (m.group(1), password), None


def open_mailbox(user, password):
    conn = imaplib.IMAP4_SSL(IMAP_HOST, timeout=60)
    conn.login(user, password)
    typ, data = conn.select(MAILBOX, readonly=True)
    _check(typ, data, "SELECT")
    return conn


def run_sync(days=None, dry_run=False):
    creds, err = get_credentials()
    if err:
        raise RuntimeError(err)
    conn = open_mailbox(*creds)
    try:
        return sync(conn, days=days, dry_run=dry_run)
    finally:
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def format_summary(s):
    lines = [f"Inbox: scanned {s['scanned']}, {s['candidates']} job-related, "
             f"{len(s['applied'])} tracker update(s), {len(s['review'])} to review, "
             f"{len(s['actions'])} need a reply, {len(s['ghosted'])} ghosted"]
    for a in s["applied"]:
        change = f" → {a['status']}" if a["status"] else ""
        lines.append(f"  row {a['row_id']}{change}  [{a['kind']}] {a['subject']}")
    for r in s["review"]:
        lines.append(f"  review {r['msg_id']}  [{r['kind']}] {r['subject']}")
    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------

def _print_items(items, empty):
    if not items:
        print(empty)
    for i in items:
        extra = f" candidates={i['candidates']}" if "candidates" in i else f" row={i.get('row_id')}"
        print(f"{i['date']}  [{i['kind']}] {i['subject']}\n    from {i['sender']}  {i['msg_id']}{extra}")


def _exit_on(result, err):
    if err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
    print(result)


def cmd_setup(_args):
    creds, err = get_credentials()
    if err:
        print(f"{err}\n\n{SETUP_HELP}")
        return 1
    open_mailbox(*creds).logout()
    print(f"OK: logged in to {IMAP_HOST} as {creds[0]} (read-only)")


def cmd_sync(args):
    print(format_summary(run_sync(days=args.days, dry_run=args.dry_run)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--days", type=int)
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.set_defaults(func=cmd_sync)
    sub.add_parser("review").set_defaults(
        func=lambda a: _print_items(load_state()["review"], "Review queue is empty."))
    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("msg_id")
    group = p_resolve.add_mutually_exclusive_group(required=True)
    group.add_argument("--row", type=int)
    group.add_argument("--ignore", action="store_true")
    p_resolve.set_defaults(func=lambda a: _exit_on(*resolve(a.msg_id, a.row)))
    p_actions = sub.add_parser("actions")
    p_actions.add_argument("--all", action="store_true")
    p_actions.set_defaults(func=lambda a: _print_items(
        [i for i in load_state()["actions"] if a.all or not i["done"]], "Nothing needs a reply."))
    p_done = sub.add_parser("done")
    p_done.add_argument("msg_id")
    p_done.set_defaults(func=lambda a: _exit_on(*mark_done(a.msg_id)))
    p_undo = sub.add_parser("undo")
    p_undo.add_argument("row_id", type=int)
    p_undo.set_defaults(func=lambda a: _exit_on(*job_tool.undo_last_status(a.row_id)))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

`radar.py` — `import inbox` beside `import job_tool`, then:

```python
def cmd_daily(args):
    """The 07:00 launchd entry point. Each step's failure is logged without stopping the other;
    ghosting only happens inside a successful inbox sync."""
    try:
        cmd_refresh(args)
    except Exception as e:  # noqa: BLE001 — keep going to the inbox sync
        print(f"radar refresh failed: {e}")
    try:
        print(inbox.format_summary(inbox.run_sync()))
    except Exception as e:  # noqa: BLE001
        print(f"inbox sync failed: {e}")
    snapshot_state(f"daily run {date.today().isoformat()}")


def snapshot_state(message):
    """Commit the state dir (it is a local git repo since 2026-10-09) so every automatic tracker change
    is reviewable and revertable: `git -C ~/job-search-data log -p tracker.json`. No-op without a repo
    or when nothing changed; never pushes."""
    d = job_tool.state_dir()
    if not (d / ".git").exists():
        return
    subprocess.run(["git", "-C", str(d), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", message], capture_output=True)
```

(`import subprocess` in `radar.py`.) Test in `TestDaily`:

```python
    def test_daily_commits_state_repo(self):
        subprocess.run(["git", "init", "-q", self.tmp.name], check=True)
        subprocess.run(["git", "-C", self.tmp.name, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", self.tmp.name, "config", "user.name", "t"], check=True)
        args = radar.argparse.Namespace(no_linkedin=True, max_details=0)
        with patch("radar.cmd_refresh"), \
             patch("radar.inbox.get_credentials", return_value=(None, "no Keychain item")):
            radar.cmd_daily(args)
        log = subprocess.run(["git", "-C", self.tmp.name, "log", "--oneline"], capture_output=True, text=True)
        self.assertIn("daily run", log.stdout)
```

argparse: `p_daily = sub.add_parser("daily")` with the same `--no-linkedin` / `--max-details` arguments as `refresh`, `set_defaults(func=cmd_daily)`. Add `radar.py daily` to the module docstring usage.

`manifest.json`: version `1.19.0`; add `scripts/inbox.py` and `scripts/test_inbox.py` install entries (same dest pattern); tags += `"imap"`, `"gmail"`, `"inbox-sync"`; `requirements.env_vars` unchanged (Keychain, not env).

`SKILL.md`: status list at ~L685 becomes `Shortlisted → Applied → Responded → Phone Screen → Interviewing → Offer`, plus `Rejected`, `Ghosted`, `Withdrawn`; document `channel`/`tier`/`positioning` on upsert; add an "Inbox sync" section: what it does, the read-only guarantee, `inbox.py review/resolve/actions/done/undo`, and that a status update request ("I got rejected by X") should still use `tracker upsert`.

`references/scheduled-runs.md`: the agent now runs `radar.py daily` (refresh, then inbox sync; ghosting only after a successful sync).

- [ ] **Step 4: Run** `python3 -m unittest -q` and `cd ~/GitHub/claude-code-tools && npm run validate` — Expected: OK / manifest valid.
- [ ] **Step 5: Commit** — `git commit -am "job-search: inbox CLI, Keychain credentials, radar.py daily entry point"`

---

### Task 7: Real-inbox checkpoint (with Yoav)

**Files:** `inbox.py` regexes, `test_inbox.py` (one regression case per misclassification), the launchd plist.

- [ ] **Step 1: Yoav creates the app password and stores it** — he runs in the session:
  `! security add-generic-password -U -s job-search-imap -a yoavsb25@gmail.com -w`
- [ ] **Step 2:** `python3 inbox.py setup` → `OK: logged in ... (read-only)`.
- [ ] **Step 3: Dry run over the window covering all 41 applications:** `python3 inbox.py sync --dry-run --days 30`.
  Walk the output with Yoav. For each wrong classification or match: add the email (anonymised subject/body) as a test case in `TestClassify`/`TestMatch`, watch it fail, fix the regex, re-run all tests.
- [ ] **Step 4: Real sync:** `python3 inbox.py sync --days 30`, then `inbox.py review` and `inbox.py actions` with Yoav; resolve each item.
- [ ] **Step 5: Switch launchd to the daily entry point**

Edit the plist's third `ProgramArguments` string from `refresh` to `daily`, then:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.yoavsborovsky.jobradar.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yoavsborovsky.jobradar.plist
launchctl kickstart -k gui/$(id -u)/com.yoavsborovsky.jobradar   # one run now
tail -20 ~/job-search-data/logs/radar.log
```
Expected: radar summary followed by an `Inbox: scanned …` line (no Keychain prompt — if macOS shows one, click "Always Allow").

- [ ] **Step 6: Commit** — `git commit -am "job-search: inbox rules tuned against real mail"`

---

## Next plan (not in scope here)
Cockpit page: Today tab (actions, review queue with resolve buttons, follow-ups, `/api/inbox/*` endpoints), Pipeline tab (inline edit of tier/channel/positioning/status, confirm inferred positioning; retire `london-role-tracker.html`), Insights tab (funnel + response rates by channel/positioning/tier, 3/2/1 KPIs), Tier-1 helpers (connections inline, copy `/resume-tailor` command). Written after Task 7 so it builds on real event data.
