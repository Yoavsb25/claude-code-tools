import email.message
import os
import subprocess
import tempfile
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import inbox
import job_tool


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
        body = inbox.parse_message(1, mm.as_bytes())["body"]
        self.assertIn("We regret to inform you", body)
        self.assertNotIn("<p>", body)


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
        self.assertIsNone(err)
        self.assertTrue(item["done"])


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
        fake.list.return_value = ("OK", [])
        fake.select.return_value = ("OK", [b"12"])
        with patch("inbox.imaplib.IMAP4_SSL", return_value=fake):
            inbox.open_mailbox("me@gmail.com", "pw")
        fake.select.assert_called_once_with(inbox.MAILBOX, readonly=True)

    def test_format_summary(self):
        text = inbox.format_summary({"scanned": 5, "candidates": 3, "ghosted": [4],
                                     "applied": [{"subject": "Re", "kind": "rejection", "row_id": 1,
                                                  "status": "Rejected"}],
                                     "review": [{"subject": "Hm", "kind": "rejection", "msg_id": "<w@x>"}],
                                     "actions": []})
        self.assertIn("1 tracker update", text)
        self.assertIn("1 to review", text)


class TestReviewFixes(unittest.TestCase):
    """Regressions for the 2026-10-09 whole-branch review findings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        for company, role in [("Acme", "Platform Engineer"), ("Global", "Python Developer"),
                              ("Old Co", "AI Engineer")]:
            job_tool.upsert_tracker_row({"company": company, "role": role, "status": "Applied",
                                         "applied_date": "2026-10-01" if company != "Old Co" else "2026-09-01"})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def rows(self):
        return {r["company"]: r for r in job_tool.load_rows()["rows"]}

    # 1 — own sent mail
    def test_own_sent_mail_is_ignored(self):
        box = FakeIMAP({1: make_raw("Following up on my Acme application", "Yoav <me@gmail.com>",
                                    "Unfortunately I need to reschedule.", msg_id="<s@x>")})
        inbox.sync(box, today=TODAY, own_address="me@gmail.com")
        self.assertEqual(self.rows()["Acme"]["status"], "Applied")
        self.assertEqual(inbox.load_state()["actions"], [])

    # 2 — boilerplate
    def test_unfortunately_boilerplate_in_confirmation(self):
        body = ("We have received your application. Unfortunately, due to the high volume of applications, "
                "we are unable to respond to every candidate individually.")
        self.assertEqual(inbox.classify(msg("Application received", body=body)), "confirmation")

    def test_conditional_invite_in_confirmation(self):
        body = "Thanks for your application. If shortlisted, we'd love to schedule a call."
        self.assertEqual(inbox.classify(msg("Thanks for applying", body=body)), "confirmation")

    def test_real_invite_after_thanks_is_still_interview(self):
        body = "Thank you for your application. We'd like to invite you to a first interview."
        self.assertEqual(inbox.classify(msg("Next steps", body=body)), "interview")

    # 3 — short / generic / contained names
    def test_generic_name_inside_longer_company_is_weak(self):
        r, strength, _ = inbox.match(msg("Update from Cboe Global Markets", "noreply@myworkday.com"),
                                     [row(1, "Global", "Python Developer")])
        self.assertEqual((r, strength), (None, "weak"))

    def test_contained_company_loses_to_longer_match(self):
        rows = [row(1, "Cboe", "Python Developer"), row(2, "Global", "Platform Engineer")]
        r, strength, _ = inbox.match(msg("Cboe Global Markets: Platform Engineer application",
                                         "noreply@myworkday.com"), rows)
        self.assertEqual((r["id"], strength), (1, "strong"))

    def test_generic_name_from_own_sender_is_strong(self):
        r, strength, _ = inbox.match(msg("Your application", "Global Recruitment <jobs@global.com>"),
                                     [row(1, "Global", "Python Developer")])
        self.assertEqual((r["id"], strength), (1, "strong"))

    def test_platform_vendor_company_not_matched_by_its_notifications(self):
        r, strength, _ = inbox.match(msg("You appeared in 5 searches", "LinkedIn <notifications@linkedin.com>"),
                                     [row(1, "LinkedIn", "Software Engineer")])
        self.assertIsNone(r)

    # 4 — ignore is durable
    def test_ignored_item_does_not_return_on_resync(self):
        box = lambda: FakeIMAP({1: make_raw("Your application", "Talent <talent@agency.co>",
                                            "Unfortunately the global client paused hiring.", msg_id="<w@x>")})
        inbox.sync(box(), today=TODAY)
        inbox.resolve("<w@x>")
        inbox.sync(box(), today=TODAY, days=30)
        self.assertEqual(inbox.load_state()["review"], [])

    # 5 — actions survive a crash mid-sync
    def test_action_saved_even_if_sync_crashes_later(self):
        box = FakeIMAP({1: make_raw("Acme - next steps", "Sam at Acme <sam@acme.com>",
                                    "Could you share your availability?", msg_id="<i@x>")})
        real_apply = inbox.apply_to_row

        def apply_then_crash(*a, **k):
            real_apply(*a, **k)
            raise OSError("connection reset")

        with patch("inbox.apply_to_row", side_effect=apply_then_crash):
            with self.assertRaises(OSError):
                inbox.sync(box, today=TODAY)
        self.assertEqual([a["msg_id"] for a in inbox.load_state()["actions"]], ["<i@x>"])

    # 6 — no ghosting while a reply waits in review
    def test_row_with_pending_review_is_not_ghosted(self):
        old_id = self.rows()["Old Co"]["id"]
        box = FakeIMAP({1: make_raw("Re: your application", "Dana <dana@gmail.com>",
                                    "Old Co would like to invite you to interview.", msg_id="<p@x>")})
        inbox.sync(box, today=TODAY)
        self.assertEqual([i["candidates"] for i in inbox.load_state()["review"]], [[old_id]])
        self.assertEqual(self.rows()["Old Co"]["status"], "Applied")

    # 7 — All Mail folder discovered, not hard-coded
    def test_open_mailbox_finds_all_mail_folder(self):
        fake = MagicMock()
        fake.list.return_value = ("OK", [b'(\\HasNoChildren) "/" "INBOX"',
                                         b'(\\All \\HasNoChildren) "/" "[Google Mail]/All Mail"'])
        fake.select.return_value = ("OK", [b"12"])
        with patch("inbox.imaplib.IMAP4_SSL", return_value=fake):
            inbox.open_mailbox("me@gmail.com", "pw")
        fake.select.assert_called_once_with('"[Google Mail]/All Mail"', readonly=True)

    # 8 — UID in the trailing element of a FETCH response
    def test_fetch_reads_uid_from_trailing_element(self):
        class Trailing(FakeIMAP):
            def uid(self, command, *args):
                typ, data = super().uid(command, *args)
                if command != "FETCH":
                    return typ, data
                out = []
                for item in data:
                    if isinstance(item, tuple):
                        seq = item[0].split(b" ")[0]
                        out += [(seq + b" (BODY[] {%d}" % len(item[1]), item[1]),
                                b" UID " + item[0].split(b"UID ")[1].split(b" ")[0] + b")"]
                return typ, out

        box = Trailing({7: make_raw("Your application to Acme", "Acme <jobs@acme.com>", "Unfortunately we "
                                    "have decided to move forward with other candidates.", msg_id="<t@x>")})
        self.assertEqual([u for u, _ in inbox.fetch(box, [7], inbox.FULL_PART)], [7])


class TestRealInboxCases(unittest.TestCase):
    """Cases from the 2026-10-09 dry run over Yoav's real inbox (bodies shortened)."""

    def kind(self, subject, sender, body, bulk=False):
        return inbox.classify(dict(msg(subject, sender, body), bulk=bulk))

    def test_rejection_phrasings(self):
        cases = [
            ("Attio Application Update", "Attio <careers@mail.attio.com>",
             "Thank you for you application the Product Engineer role at Attio. The team has taken the time to "
             "review your profile and has decided not to move forward at this time."),
            ("Update on your application for Solutions Engineer", "Aveni Hiring Team <no-reply@ashbyhq.com>",
             "Thank you for applying for the Solutions Engineer role at Aveni. After reviewing your CV we’ve "
             "decided not to progress your application to the next stage on this occasion."),
            ("Thank you from JFrog!", "no-reply@jfrog.com",
             "Thank you for your interest in joining our swamp! Unfortunately, at this moment in time we don’t "
             "have any relevant opportunities that fit your skills and experience."),
            ("Your application to Forward Deployed Engineer at Findrs", "LinkedIn <jobs-noreply@linkedin.com>",
             "Your update from Findrs https://www.linkedin.com/help?lipi=urn%3Ali%3Apage%3Aemail_email_jobs_"
             "application_rejected_01"),
        ]
        for subject, sender, body in cases:
            with self.subTest(subject=subject):
                self.assertEqual(self.kind(subject, sender, body), "rejection")

    def test_bulk_mail_is_never_a_reply(self):
        self.assertEqual(self.kind("Help us match you with the right jobs", "La Fosse <data.admin@lafosse.com>",
                                   "Thanks for your recent application. Could you update your details?", bulk=True),
                         "other")
        self.assertEqual(self.kind("You're invited to London Office", "Unity <info@gable.to>",
                                   "You're invited to visit London Office. Your host is Emma.", bulk=True), "other")

    def test_linkedin_inmail_is_still_a_reply_despite_bulk_headers(self):
        self.assertEqual(self.kind("Career Opportunity with a UK Series A Insurtech",
                                   "Adam Tully <inmail-hit-reply@linkedin.com>", "Hello Yoav, is timing right?",
                                   bulk=True), "reply")

    def test_receipts_and_job_alerts_are_noise(self):
        self.assertEqual(self.kind("Your receipt from Anthropic, PBC #2851", '"Anthropic, PBC" <invoice@mail.anthropic.com>',
                                   "Receipt £18.00 Paid"), "noise")
        self.assertEqual(self.kind("Staff Engineer (IT Automation) at SoSafe",
                                   "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
                                   "Your job alert. Book a time to chat"), "noise")
        self.assertFalse(inbox.is_candidate(msg("Staff Engineer at SoSafe", "jobalerts-noreply@linkedin.com"), []))

    def test_bulk_flag_parsed_from_list_unsubscribe(self):
        m = email.message.EmailMessage()
        m["Subject"], m["From"], m["Date"] = "Hi", "a@b.com", "Wed, 08 Oct 2026 10:00:00 +0000"
        m["List-Unsubscribe"] = "<mailto:u@b.com>"
        m.set_content("x")
        self.assertTrue(inbox.parse_message(1, m.as_bytes())["bulk"])
        self.assertFalse(inbox.parse_message(1, make_raw("Hi", "a@b.com", "x"))["bulk"])

    def test_linkedin_subject_names_generic_company_exactly(self):
        r, strength, _ = inbox.match(msg("Yoav, your application was sent to Byte", "LinkedIn <jobs-noreply@linkedin.com>"),
                                     [row(1, "Byte", "Artificial Intelligence Engineer")])
        self.assertEqual((r["id"], strength), (1, "strong"))
        r, strength, _ = inbox.match(msg("Your application to AI Engineer at Global", "LinkedIn <jobs-noreply@linkedin.com>"),
                                     [row(1, "Global", "AI Engineer")])
        self.assertEqual((r["id"], strength), (1, "strong"))


class TestBodyText(unittest.TestCase):
    def test_html_body_drops_style_blocks_and_decodes_entities(self):
        mm = email.message.EmailMessage()
        mm["Subject"], mm["From"], mm["Date"] = "Hi", "a@b.com", "Wed, 08 Oct 2026 10:00:00 +0000"
        mm.set_content("<html><head><style>#outlook a { padding:0; }</style></head>"
                       "<body><p>Thanks for applying &ndash; we&rsquo;re excited</p></body></html>", subtype="html")
        body = inbox.parse_message(1, mm.as_bytes())["body"]
        self.assertNotIn("padding", body)
        self.assertIn("Thanks for applying – we’re excited", body)

    def test_plain_body_entities_decoded(self):
        self.assertIn("we’re", inbox.parse_message(1, make_raw("Hi", "a@b.com", "we&rsquo;re here"))["body"])


class TestConcurrentStateEdits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        job_tool.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})
        job_tool.save_json(inbox.state_path(), {
            "uidvalidity": 1, "last_uid": 0, "last_sync": None, "ignored": [],
            "actions": [{"msg_id": "<old>", "row_id": 1, "done": False, "subject": "s", "sender": "x",
                         "date": "2026-10-01", "kind": "reply"}],
            "review": [{"msg_id": "<rv>", "candidates": [], "subject": "s", "sender": "x",
                        "date": "2026-10-01", "kind": "confirmation"}]})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_page_edits_during_sync_survive(self):
        box = FakeIMAP({5: make_raw("Acme - next steps", "Sam at Acme <sam@acme.com>",
                                    "Could you share your availability?", msg_id="<i@x>")})
        real_apply = inbox.apply_to_row

        def apply_while_user_clicks(*a, **k):
            result = real_apply(*a, **k)
            inbox.mark_done("<old>")
            inbox.resolve("<rv>")
            return result

        with patch("inbox.apply_to_row", side_effect=apply_while_user_clicks):
            inbox.sync(box, today=TODAY)
        state = inbox.load_state()
        self.assertEqual({a["msg_id"]: a["done"] for a in state["actions"]}, {"<old>": True, "<i@x>": False})
        self.assertEqual(state["review"], [])
        self.assertIn("<rv>", state["ignored"])
