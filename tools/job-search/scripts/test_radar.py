import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import radar


class TestExtractYears(unittest.TestCase):
    CASES = [
        ("You have 3+ years of experience building backend systems.", 3),
        ("3-5 years of professional software engineering experience", 3),
        ("2 to 4 yrs working with Python", 2),
        ("At least three years of experience with Kubernetes.", 3),
        ("Minimum of 5 years in a DevOps role.", 5),
        ("5 plus years of industry experience", 5),
        ("You bring 4+ yrs of hands-on engineering.", 4),
        ("1+ year of experience with cloud platforms", 1),
        ("Two years' experience in a customer-facing role", 2),
        ("7–10 years of experience leading teams", 7),
        ("Proven track record (6+ years) delivering platforms", 6),
    ]

    def test_phrasings(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(radar.extract_years(text)[0], expected)

    def test_takes_strictest_requirement(self):
        text = "2+ years of Python. 5+ years of overall software engineering experience."
        years, evidence = radar.extract_years(text)
        self.assertEqual(years, 5)
        self.assertIn("5+ years", evidence)

    def test_ignores_company_history(self):
        for text in [
            "Founded 12 years ago, we now serve 3,000 customers.",
            "We've grown revenue every year for the past 5 years.",
            "Voted best place to work 3 years in a row.",
            "Our 10 years anniversary is coming up.",
            "Generous parental leave for 2 years.",
            "23 days' holiday, rising to 25 days after 2 years of service.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(radar.extract_years(text), (None, None))

    def test_ignores_nice_to_have(self):
        text = "3+ years of experience required. 6+ years with Go is a plus."
        self.assertEqual(radar.extract_years(text)[0], 3)

    def test_no_match_or_empty(self):
        self.assertEqual(radar.extract_years("Great benefits and a friendly team."), (None, None))
        self.assertEqual(radar.extract_years(None), (None, None))

    def test_ignores_absurd_values(self):
        self.assertEqual(radar.extract_years("30 years of combined team experience"), (None, None))


class TestDescriptionText(unittest.TestCase):
    def test_keeps_bullets_separate_and_decodes_escaped_html(self):
        html = "&lt;ul&gt;&lt;li&gt;3+ years of Python&lt;/li&gt;&lt;li&gt;Founded 10 years ago&lt;/li&gt;&lt;/ul&gt;"
        text = radar.job_tool.description_text(html)
        self.assertEqual(text.splitlines(), ["3+ years of Python", "Founded 10 years ago"])
        self.assertEqual(radar.extract_years(text)[0], 3)


class TestClassifyLevel(unittest.TestCase):
    def test_title_rules(self):
        cases = {
            "Senior Platform Engineer": "senior",
            "Staff Software Engineer": "staff+",
            "Software Engineer Intern": "intern",
            "Graduate Software Engineer": "entry",
            "Junior Developer": "junior",
            "Associate Applied AI": "junior",
            "Software Engineer II": "mid",
            "Backend Engineer III": "senior",
            "Head of Platform": "manager",
            "Manager, Solutions Architecture": "manager",
            "Account Manager, SMB": "unknown",
            "Software Engineer": "unknown",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(radar.classify_level(title), expected)

    def test_linkedin_seniority_fallback(self):
        self.assertEqual(radar.classify_level("Software Engineer", "Entry level"), "entry")
        self.assertEqual(radar.classify_level("Software Engineer", "Mid-Senior level"), "mid/senior")


class TestRoleFamily(unittest.TestCase):
    def test_families(self):
        cases = {
            "Forward Deployed Engineer": "AI/FDE",
            "AI Engineer": "AI/FDE",
            "Platform Engineer": "Platform/DevEx",
            "Software Engineer - Developer Experience": "Platform/DevEx",
            "Site Reliability Engineer (SRE)": "Platform/DevEx",
            "Technical Solutions Engineer": "Solutions",
            "Sales Engineer": "Solutions",
            "Technical Program Manager": "TPM/Program",
            "Data Engineer": "Data/ML",
            "QA Automation Engineer": "QA/Automation",
            "Backend Engineer": "SWE",
            "Account Executive, Enterprise": "Non-tech",
            "Senior Recruiter": "Non-tech",
            "Product Manager": "Product",
            "Growth PM": "Product",
            "Deployment Strategist": "Solutions",
            "Information Security Analyst - SecOps": "Security/IT",
            "Technical Writer": "Security/IT",
            "Claims Validation Handler": "Non-tech",
            "Translator/Linguist (Freelance)": "Non-tech",
            "Growth Engineer": "SWE",
            "Product Manager, Agent Development": "Product",
            "Senior Product Manager - CRM Sales": "Product",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(radar.role_family(title), expected)


class TestExtractSalary(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(radar.extract_salary("£60,000 - £75,000 per annum"), ("£60k–£75k", 60000))
        self.assertEqual(radar.extract_salary("Salary: £70k–£90k + equity"), ("£70k–£90k", 70000))
        self.assertEqual(radar.extract_salary("£115,000 GBP"), ("£115k", 115000))
        self.assertEqual(radar.extract_salary("£85-110k"), ("£85k–£110k", 85000))

    def test_ignores_small_amounts(self):
        self.assertEqual(radar.extract_salary("£500 learning budget"), (None, None))
        self.assertEqual(radar.extract_salary(None), (None, None))


class TestLocation(unittest.TestCase):
    def test_target_locations(self):
        self.assertTrue(radar.is_target_location("London, UK"))
        self.assertTrue(radar.is_target_location("Cambridge, United Kingdom, London"))
        self.assertTrue(radar.is_target_location("Remote - United Kingdom"))
        self.assertTrue(radar.is_target_location("United Kingdom", remote=True))
        self.assertFalse(radar.is_target_location("United Kingdom"))
        self.assertFalse(radar.is_target_location("Tel Aviv, Israel"))
        self.assertFalse(radar.is_target_location("Remote - US"))
        self.assertFalse(radar.is_target_location(None))


class TestRecruiter(unittest.TestCase):
    def test_agency_names_and_text(self):
        self.assertTrue(radar.is_recruiter("Hunter Bond"))
        self.assertTrue(radar.is_recruiter("SR2 | Socially Responsible Recruitment"))
        self.assertTrue(radar.is_recruiter("Acme", "Our client, a Series B fintech, is hiring."))
        self.assertFalse(radar.is_recruiter("Monzo", "You'll work with our clients' engineers."))
        self.assertFalse(radar.is_recruiter("Wayve"))


class TestOnWatchlist(unittest.TestCase):
    def test_prefix_both_directions(self):
        watch = [["amazon", "aws"], ["google"]]
        self.assertTrue(radar.on_watchlist(["amazon"], watch))
        self.assertTrue(radar.on_watchlist(["google", "uk"], watch))
        self.assertFalse(radar.on_watchlist(["wayve"], watch))


class TestPostingKey(unittest.TestCase):
    def test_dedupes_across_sources(self):
        self.assertEqual(
            radar.posting_key("Neo4j Inc.", "Software Engineer - Developer Experience"),
            radar.posting_key("neo4j", "Software Engineer – Developer Experience"),
        )


def _p(source, url, **extra):
    base = {"company": "Acme", "title": "Platform Engineer", "location": "London", "url": url,
            "source": source, "posted_date": None, "years_min": None, "years_evidence": None,
            "level": "unknown", "role_family": "Platform/DevEx", "salary": None, "salary_min": None,
            "flags": [], "description": None}
    base.update(extra)
    return base


class TestMerge(unittest.TestCase):
    def test_new_posting_gets_dates(self):
        state = radar.merge({"postings": {}}, {"k": _p("greenhouse", "gh")}, "2026-10-01")
        p = state["postings"]["k"]
        self.assertEqual((p["first_seen"], p["last_seen"], p["closed"]), ("2026-10-01", "2026-10-01", False))

    def test_ats_copy_replaces_linkedin_mirror(self):
        state = radar.merge({"postings": {}}, {"k": _p("linkedin", "li", years_min=3)}, "2026-10-01")
        radar.merge(state, {"k": _p("greenhouse", "gh", description="full JD")}, "2026-10-02")
        p = state["postings"]["k"]
        self.assertEqual(p["url"], "gh")
        self.assertIn("li", p["alt_urls"])
        self.assertEqual(p["sources"], ["linkedin", "greenhouse"])
        self.assertEqual(p["first_seen"], "2026-10-01")
        self.assertEqual(p["description"], "full JD")

    def test_linkedin_does_not_overwrite_ats_fields(self):
        state = radar.merge({"postings": {}}, {"k": _p("greenhouse", "gh", years_min=2)}, "2026-10-01")
        radar.merge(state, {"k": _p("linkedin", "li", years_min=None)}, "2026-10-02")
        p = state["postings"]["k"]
        self.assertEqual((p["url"], p["years_min"]), ("gh", 2))
        self.assertIn("li", p["alt_urls"])

    def test_closed_after_unseen_days(self):
        state = radar.merge({"postings": {}}, {"k": _p("greenhouse", "gh")}, "2026-10-01")
        radar.merge(state, {}, "2026-10-03")
        self.assertFalse(state["postings"]["k"]["closed"])
        radar.merge(state, {}, "2026-10-04")
        self.assertTrue(state["postings"]["k"]["closed"])
        radar.merge(state, {"k": _p("greenhouse", "gh")}, "2026-10-05")
        self.assertFalse(state["postings"]["k"]["closed"])


class TestPrune(unittest.TestCase):
    def test_long_closed_postings_are_dropped(self):
        state = radar.merge({"postings": {}}, {"k": _p("greenhouse", "gh")}, "2026-10-01")
        radar.merge(state, {}, "2026-10-30")
        self.assertIn("k", state["postings"])
        radar.merge(state, {}, "2026-10-31")
        self.assertNotIn("k", state["postings"])


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        radar.job_tool.save_json(radar._path("profile.json"), {"target_companies": [
            {"name": "Acme", "platform": "greenhouse", "slug": "acme"},
            {"name": "BigCo", "platform": "other"},
        ]})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_refresh_filters_enriches_and_records_coverage(self):
        results = [
            {"source": "greenhouse", "title": "Senior Platform Engineer", "company": "acme",
             "location": "London, UK", "remote": None, "url": "u1", "salary": None, "posted_date": None,
             "description": "You have 5+ years of experience. Salary £90,000 - £110,000."},
            {"source": "greenhouse", "title": "Platform Engineer", "company": "acme",
             "location": "New York", "remote": None, "url": "u2", "salary": None, "posted_date": None,
             "description": None},
        ]
        with patch.object(radar.job_tool, "fetch_ats_postings", return_value=(results, None)):
            state, coverage = radar.refresh(use_linkedin=False, today="2026-10-01")

        self.assertEqual(len(state["postings"]), 1)
        p = next(iter(state["postings"].values()))
        self.assertEqual((p["company"], p["years_min"], p["level"], p["salary_min"]), ("Acme", 5, "senior", 90000))
        acme = next(c for c in coverage["companies"] if c["name"] == "Acme")
        self.assertEqual((acme["ok"], acme["total"], acme["london"]), (True, 2, 1))
        bigco = next(c for c in coverage["companies"] if c["name"] == "BigCo")
        self.assertTrue(bigco["linkedin_only"])
        self.assertTrue(radar._path("companies.json").exists())

    def test_no_linkedin_run_keeps_previous_discoveries(self):
        radar.job_tool.save_json(radar._path("coverage.json"), {
            "linkedin": {"cards": 5}, "discovered": [{"company": "Wayve", "postings": 3}]})
        with patch.object(radar.job_tool, "fetch_ats_postings", return_value=([], None)):
            _, coverage = radar.refresh(use_linkedin=False, today="2026-10-01")
        self.assertEqual(coverage["discovered"], [{"company": "Wayve", "postings": 3}])

    def test_add_to_watchlist(self):
        board = ("greenhouse", "newco", [{"title": "x"}])
        with patch.object(radar.job_tool, "discover_ats", return_value=(board, "high", [])):
            entry, err = radar.add_to_watchlist("NewCo", tier="ai")
        self.assertIsNone(err)
        self.assertEqual((entry["platform"], entry["slug"]), ("greenhouse", "newco"))
        with patch.object(radar.job_tool, "discover_ats", return_value=(None, "none", [])):
            entry, _ = radar.add_to_watchlist("Mystery Ltd")
        self.assertEqual(entry["platform"], "linkedin-only")
        self.assertIn("already", radar.add_to_watchlist("newco")[1])
        names = [c["name"] for c in radar.load_watchlist()]
        self.assertEqual(names[-2:], ["NewCo", "Mystery Ltd"])

    def test_failing_company_is_reported_not_raised(self):
        with patch.object(radar.job_tool, "fetch_ats_postings", return_value=([], "HTTP 404")), \
                patch.object(radar.time, "sleep"):
            _, coverage = radar.refresh(use_linkedin=False, today="2026-10-01")
        acme = next(c for c in coverage["companies"] if c["name"] == "Acme")
        self.assertEqual((acme["ok"], acme["error"]), (False, "HTTP 404"))


class TestPageServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        state = radar.merge({"postings": {}}, {"acme|platform engineer": _p(
            "greenhouse", "https://acme/jobs/1", salary="£70k", years_min=2, level="mid")}, "2026-10-01")
        state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        radar.job_tool.save_json(radar._path("radar.json"), state)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_save_adds_tracker_row_once(self):
        saved, err = radar.save_posting("acme|platform engineer")
        self.assertIsNone(err)
        radar.save_posting("acme|platform engineer")
        rows = radar.job_tool.load_rows()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["company"], rows[0]["role"], rows[0]["status"], rows[0]["link"]),
                         ("Acme", "Platform Engineer", "Shortlisted", "https://acme/jobs/1"))
        self.assertEqual(radar.load_page_state()["saved"]["acme|platform engineer"]["tracker_id"], saved["tracker_id"])

    def test_save_unknown_key_errors(self):
        self.assertEqual(radar.save_posting("nope"), (None, "unknown posting"))

    def test_hide_and_unhide(self):
        radar.hide_posting("acme|platform engineer", "too senior")
        self.assertEqual(radar.load_page_state()["hidden"]["acme|platform engineer"]["reason"], "too senior")
        radar.unhide_posting("acme|platform engineer")
        self.assertEqual(radar.load_page_state()["hidden"], {})
        self.assertIsNotNone(radar.hide_posting("k", "bogus")[1])

    def test_is_stale(self):
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        fresh = {"updated_at": (now - timedelta(hours=2)).isoformat()}
        old = {"updated_at": (now - timedelta(hours=13)).isoformat()}
        self.assertFalse(radar.is_stale(fresh, now))
        self.assertTrue(radar.is_stale(old, now))
        self.assertTrue(radar.is_stale(None, now))

    def test_http_endpoints(self):
        server = radar.ThreadingHTTPServer(("127.0.0.1", 0), radar.make_handler(radar.RefreshRunner()))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            page = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("<title>Job Radar</title>", page)
            data = json.load(urllib.request.urlopen(base + "/api/data"))
            self.assertEqual(data["postings"][0]["key"], "acme|platform engineer")
            req = urllib.request.Request(base + "/api/hide", method="POST",
                                         data=json.dumps({"key": "acme|platform engineer", "reason": "pay"}).encode(),
                                         headers={"Content-Type": "application/json"})
            self.assertEqual(json.load(urllib.request.urlopen(req))["reason"], "pay")
            bad = urllib.request.Request(base + "/api/save", method="POST", data=b'{"key": "nope"}')
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(bad)
            self.assertEqual(ctx.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
