import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

import cockpit
import job_tool

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
