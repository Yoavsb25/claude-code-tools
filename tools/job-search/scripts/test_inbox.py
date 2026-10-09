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
