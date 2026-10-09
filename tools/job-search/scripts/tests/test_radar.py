import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import radar
from jobsearch import radar_enrich
from jobsearch import radar_merge
from jobsearch.sources import common


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
                self.assertEqual(radar_enrich.extract_years(text)[0], expected)

    def test_takes_strictest_requirement(self):
        text = "2+ years of Python. 5+ years of overall software engineering experience."
        years, evidence = radar_enrich.extract_years(text)
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
                self.assertEqual(radar_enrich.extract_years(text), (None, None))

    def test_ignores_nice_to_have(self):
        text = "3+ years of experience required. 6+ years with Go is a plus."
        self.assertEqual(radar_enrich.extract_years(text)[0], 3)

    def test_no_match_or_empty(self):
        self.assertEqual(radar_enrich.extract_years("Great benefits and a friendly team."), (None, None))
        self.assertEqual(radar_enrich.extract_years(None), (None, None))

    def test_ignores_absurd_values(self):
        self.assertEqual(radar_enrich.extract_years("30 years of combined team experience"), (None, None))


class TestDescriptionText(unittest.TestCase):
    def test_keeps_bullets_separate_and_decodes_escaped_html(self):
        from jobsearch.fetchconfig import RADAR
        html = "&lt;ul&gt;&lt;li&gt;3+ years of Python&lt;/li&gt;&lt;li&gt;Founded 10 years ago&lt;/li&gt;&lt;/ul&gt;"
        text = common.description_text(html, config=RADAR)
        self.assertEqual(text.splitlines(), ["3+ years of Python", "Founded 10 years ago"])
        self.assertEqual(radar_enrich.extract_years(text)[0], 3)


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
            "Data Science Manager": "manager",
            "Mgr,  Expert Services Mgmt": "manager",
            "Technical Program Manager": "unknown",
            "Technical Programme Manager, Core Tech": "unknown",
            "Product Manager, Payments": "unknown",
            "Delivery Manager": "unknown",
            "Software Engineer": "unknown",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(radar_enrich.classify_level(title), expected)

    def test_linkedin_seniority_fallback(self):
        self.assertEqual(radar_enrich.classify_level("Software Engineer", "Entry level"), "entry")
        self.assertEqual(radar_enrich.classify_level("Software Engineer", "Mid-Senior level"), "mid/senior")


class TestRoleFamily(unittest.TestCase):
    def test_families(self):
        cases = {
            "Forward Deployed Engineer": "AI/FDE",
            "AI Engineer": "AI/FDE",
            "Platform Engineer": "Infra/DevOps",
            "DevSecOps Engineer": "Infra/DevOps",
            "Cloud/ DevOps Engineer": "Infra/DevOps",
            "Software Engineer - Developer Experience": "DevEx/Tools",
            "Internal Tools Engineer": "DevEx/Tools",
            "Site Reliability Engineer (SRE)": "Infra/DevOps",
            "Forward Deployed Infrastructure Engineer": "AI/FDE",
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
            "Technical Writer": "Non-tech",
            "Enterprise Account Executive, AI Natives": "Non-tech",
            "Martech Specialist, AI Deployment": "Non-tech",
            "Cybersecurity Compliance Analyst": "Non-tech",
            "Research Scientist - Generative Audio": "Data/ML",
            "Fraud Data Scientist": "Data/ML",
            "Android Engineer - Experience": "Mobile",
            "Senior C++/iOS Engineer - User Platform": "Mobile",
            "Audio Engineering (Freelance)": "Non-tech",
            "Claims Validation Handler": "Non-tech",
            "Translator/Linguist (Freelance)": "Non-tech",
            "Growth Engineer": "SWE",
            "Product Manager, Agent Development": "Product",
            "Senior Product Manager - CRM Sales": "Product",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(radar_enrich.role_family(title), expected)


class TestTitleFlags(unittest.TestCase):
    def test_other_language(self):
        for title in ("Software Engineer, Agent (German speaking)", "Solutions Engineer - UK (Italian Speaking)",
                      "Solution Engineer French-speaking", "Account Executive, Fluent Dutch"):
            with self.subTest(title=title):
                self.assertEqual(radar_enrich.title_flags(title), ["other_language"])
        for title in ("Software Engineer, Agent", "Hebrew speaking Solutions Engineer", "Public Speaking Coach"):
            with self.subTest(title=title):
                self.assertEqual(radar_enrich.title_flags(title), [])


class TestSkillFit(unittest.TestCase):
    HAVE = {"Python", "TypeScript", "React", "AWS", "Docker", "SQL"}

    def test_scores_matches_against_missing(self):
        r = radar_enrich.skill_fit("You'll build services in Python and TypeScript on AWS with Docker.", self.HAVE)
        self.assertEqual(r["fit"], 80)  # 4 / (4 + 0 + 1)
        self.assertEqual(r["fit_have"], ["AWS", "Docker", "Python", "TypeScript"])
        self.assertEqual(r["fit_missing"], [])
        self.assertIsNone(r["fit_blocker"])

    def test_single_match_is_not_a_strong_fit(self):
        self.assertEqual(radar_enrich.skill_fit("Experience with SQL.", self.HAVE)["fit"], 50)

    def test_missing_main_language_blocks(self):
        r = radar_enrich.skill_fit("Our backend is written in Go. You know SQL and Docker.", self.HAVE)
        self.assertEqual(r["fit_blocker"], "Go")
        self.assertLessEqual(r["fit"], radar_enrich.BLOCKED_FIT_CAP)

    def test_language_you_have_alongside_one_you_lack_does_not_block(self):
        r = radar_enrich.skill_fit("You write Go or Python every day.", self.HAVE)
        self.assertIsNone(r["fit_blocker"])
        self.assertEqual(r["fit_missing"], ["Go"])

    def test_nice_to_have_skills_are_not_missing(self):
        r = radar_enrich.skill_fit("Strong Python. Rust is a plus.", self.HAVE)
        self.assertEqual(r["fit_missing"], [])

    def test_go_as_a_verb_is_not_the_language(self):
        r = radar_enrich.skill_fit("We go fast. Ready to go live with Python and React.", self.HAVE)
        self.assertNotIn("Go", r["fit_missing"])

    def test_no_tech_named(self):
        self.assertIsNone(radar_enrich.skill_fit("Join our friendly team.", self.HAVE)["fit"])
        self.assertIsNone(radar_enrich.skill_fit("", self.HAVE)["fit"])

    def test_profile_skills_read_from_profile(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"JOB_SEARCH_DIR": tmp}):
            radar.store.save_json(radar.profile_path(),
                                     {"skills": ["Python", "Express", "REST API", "Git/GitHub", "C"]})
            self.assertEqual(radar_enrich.profile_skills(), {"Python", "Node.js", "REST APIs", "Git"})


class TestExtractSalary(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(radar_enrich.extract_salary("£60,000 - £75,000 per annum"), ("£60k–£75k", 60000))
        self.assertEqual(radar_enrich.extract_salary("Salary: £70k–£90k + equity"), ("£70k–£90k", 70000))
        self.assertEqual(radar_enrich.extract_salary("£115,000 GBP"), ("£115k", 115000))
        self.assertEqual(radar_enrich.extract_salary("£85-110k"), ("£85k–£110k", 85000))

    def test_ignores_small_amounts(self):
        self.assertEqual(radar_enrich.extract_salary("£500 learning budget"), (None, None))
        self.assertEqual(radar_enrich.extract_salary(None), (None, None))


class TestLocation(unittest.TestCase):
    def test_target_locations(self):
        self.assertTrue(radar_enrich.is_target_location("London, UK"))
        self.assertTrue(radar_enrich.is_target_location("Cambridge, United Kingdom, London"))
        self.assertTrue(radar_enrich.is_target_location("Remote - United Kingdom"))
        self.assertTrue(radar_enrich.is_target_location("United Kingdom", remote=True))
        self.assertFalse(radar_enrich.is_target_location("United Kingdom"))
        self.assertFalse(radar_enrich.is_target_location("Tel Aviv, Israel"))
        self.assertFalse(radar_enrich.is_target_location("Remote - US"))
        self.assertFalse(radar_enrich.is_target_location(None))


class TestRecruiter(unittest.TestCase):
    def test_agency_names_and_text(self):
        self.assertTrue(radar_enrich.is_recruiter("Hunter Bond"))
        self.assertTrue(radar_enrich.is_recruiter("SR2 | Socially Responsible Recruitment"))
        self.assertTrue(radar_enrich.is_recruiter("Acme", "Our client, a Series B fintech, is hiring."))
        self.assertFalse(radar_enrich.is_recruiter("Monzo", "You'll work with our clients' engineers."))
        self.assertFalse(radar_enrich.is_recruiter("Wayve"))


class TestOnWatchlist(unittest.TestCase):
    def test_prefix_both_directions(self):
        watch = [["amazon", "aws"], ["google"]]
        self.assertTrue(radar_enrich.on_watchlist(["amazon"], watch))
        self.assertTrue(radar_enrich.on_watchlist(["google", "uk"], watch))
        self.assertFalse(radar_enrich.on_watchlist(["wayve"], watch))


class TestPostingKey(unittest.TestCase):
    def test_dedupes_across_sources(self):
        self.assertEqual(
            radar_enrich.posting_key("Neo4j Inc.", "Software Engineer - Developer Experience"),
            radar_enrich.posting_key("neo4j", "Software Engineer – Developer Experience"),
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
        state = radar_merge.merge({"postings": {}}, {"k": _p("greenhouse", "gh")}, "2026-10-01")
        p = state["postings"]["k"]
        self.assertEqual((p["first_seen"], p["last_seen"], p["closed"]), ("2026-10-01", "2026-10-01", False))

    def test_ats_copy_replaces_linkedin_mirror(self):
        state = radar_merge.merge({"postings": {}}, {"k": _p("linkedin", "li", years_min=3)}, "2026-10-01")
        radar_merge.merge(state, {"k": _p("greenhouse", "gh", description="full JD")}, "2026-10-02")
        p = state["postings"]["k"]
        self.assertEqual(p["url"], "gh")
        self.assertIn("li", p["alt_urls"])
        self.assertEqual(p["sources"], ["linkedin", "greenhouse"])
        self.assertEqual(p["first_seen"], "2026-10-01")
        self.assertEqual(p["description"], "full JD")

    def test_linkedin_does_not_overwrite_ats_fields(self):
        state = radar_merge.merge({"postings": {}}, {"k": _p("greenhouse", "gh", years_min=2)}, "2026-10-01")
        radar_merge.merge(state, {"k": _p("linkedin", "li", years_min=None)}, "2026-10-02")
        p = state["postings"]["k"]
        self.assertEqual((p["url"], p["years_min"]), ("gh", 2))
        self.assertIn("li", p["alt_urls"])

    def test_closed_after_unseen_days(self):
        state = radar_merge.merge({"postings": {}}, {"k": _p("greenhouse", "gh")}, "2026-10-01")
        radar_merge.merge(state, {}, "2026-10-03")
        self.assertFalse(state["postings"]["k"]["closed"])
        radar_merge.merge(state, {}, "2026-10-04")
        self.assertTrue(state["postings"]["k"]["closed"])
        radar_merge.merge(state, {"k": _p("greenhouse", "gh")}, "2026-10-05")
        self.assertFalse(state["postings"]["k"]["closed"])


class TestPrune(unittest.TestCase):
    def test_long_closed_postings_are_dropped(self):
        state = radar_merge.merge({"postings": {}}, {"k": _p("greenhouse", "gh")}, "2026-10-01")
        radar_merge.merge(state, {}, "2026-10-30")
        self.assertIn("k", state["postings"])
        radar_merge.merge(state, {}, "2026-10-31")
        self.assertNotIn("k", state["postings"])


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        radar.store.save_json(radar._path("profile.json"), {"target_companies": [
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
        with patch.object(radar.ats, "fetch_ats_postings", return_value=(results, None)):
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
        radar.store.save_json(radar._path("coverage.json"), {
            "linkedin": {"cards": 5}, "discovered": [{"company": "Wayve", "postings": 3}]})
        with patch.object(radar.ats, "fetch_ats_postings", return_value=([], None)):
            _, coverage = radar.refresh(use_linkedin=False, today="2026-10-01")
        self.assertEqual(coverage["discovered"], [{"company": "Wayve", "postings": 3}])

    def test_add_to_watchlist(self):
        board = ("greenhouse", "newco", [{"title": "x"}])
        with patch.object(radar.ats, "discover_ats", return_value=(board, "high", [])):
            entry, err = radar.add_to_watchlist("NewCo", tier="ai")
        self.assertIsNone(err)
        self.assertEqual((entry["platform"], entry["slug"]), ("greenhouse", "newco"))
        with patch.object(radar.ats, "discover_ats", return_value=(None, "none", [])):
            entry, _ = radar.add_to_watchlist("Mystery Ltd")
        self.assertEqual(entry["platform"], "linkedin-only")
        self.assertIn("already", radar.add_to_watchlist("newco")[1])
        names = [c["name"] for c in radar.load_watchlist()]
        self.assertEqual(names[-2:], ["NewCo", "Mystery Ltd"])

    def test_failing_company_is_reported_not_raised(self):
        with patch.object(radar.ats, "fetch_ats_postings", return_value=([], "HTTP 404")), \
                patch.object(radar.time, "sleep"):
            _, coverage = radar.refresh(use_linkedin=False, today="2026-10-01")
        acme = next(c for c in coverage["companies"] if c["name"] == "Acme")
        self.assertEqual((acme["ok"], acme["error"]), (False, "HTTP 404"))


class TestPageServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        state = radar_merge.merge({"postings": {}}, {"acme|platform engineer": _p(
            "greenhouse", "https://acme/jobs/1", salary="£70k", years_min=2, level="mid")}, "2026-10-01")
        state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        radar.store.save_json(radar._path("radar.json"), state)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_save_adds_tracker_row_once(self):
        saved, err = radar.save_posting("acme|platform engineer")
        self.assertIsNone(err)
        radar.save_posting("acme|platform engineer")
        rows = radar.tracker.load_rows()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["company"], rows[0]["role"], rows[0]["status"], rows[0]["link"]),
                         ("Acme", "Platform Engineer", "Shortlisted", "https://acme/jobs/1"))
        self.assertEqual(radar.load_page_state()["saved"]["acme|platform engineer"]["tracker_id"], saved["tracker_id"])

    def test_save_with_tier_infers_positioning(self):
        radar.save_posting("acme|platform engineer", tier=1)
        row = radar.tracker.load_rows()["rows"][0]
        self.assertEqual((row["tier"], row["positioning"], row["positioning_inferred"]), (1, "P2", True))

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

    def test_http_endpoints(self):
        server = radar.ThreadingHTTPServer(("127.0.0.1", 0), radar.make_handler(radar.Runner(lambda: None)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            page = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("<title>Job Cockpit</title>", page)
            data = json.load(urllib.request.urlopen(base + "/api/data"))
            self.assertEqual(data["postings"][0]["key"], "acme|platform engineer")
            req = urllib.request.Request(base + "/api/hide", method="POST",
                                         data=json.dumps({"key": "acme|platform engineer", "reason": "pay"}).encode(),
                                         headers={"Content-Type": "application/json"})
            self.assertEqual(json.load(urllib.request.urlopen(req))["reason"], "pay")
            bad = urllib.request.Request(base + "/api/save", method="POST", data=b'{"key": "nope"}',
                                         headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(bad)
            self.assertEqual(ctx.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()


class TestDaily(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        radar.tracker.upsert_tracker_row({"company": "Old", "role": "SWE", "status": "Applied",
                                           "applied_date": "2026-01-01"})
        self.args = radar.argparse.Namespace(no_linkedin=True, max_details=0)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_daily_survives_inbox_failure_without_ghosting(self):
        with patch("radar.cmd_refresh") as refresh, \
             patch("radar.inbox.get_credentials", return_value=(None, "no Keychain item")):
            radar.cmd_daily(self.args)
        refresh.assert_called_once()
        self.assertEqual(radar.tracker.load_rows()["rows"][0]["status"], "Applied")

    def test_daily_runs_inbox_even_if_refresh_fails(self):
        with patch("radar.cmd_refresh", side_effect=RuntimeError("boom")), \
             patch("radar.inbox.run_sync", return_value={"scanned": 0, "candidates": 0, "applied": [],
                                                          "review": [], "actions": [], "ghosted": []}) as sync:
            radar.cmd_daily(self.args)
        sync.assert_called_once()

    def test_daily_commits_state_repo(self):
        subprocess.run(["git", "init", "-q", self.tmp.name], check=True)
        subprocess.run(["git", "-C", self.tmp.name, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", self.tmp.name, "config", "user.name", "t"], check=True)
        with patch("radar.cmd_refresh"), \
             patch("radar.inbox.get_credentials", return_value=(None, "no Keychain item")):
            radar.cmd_daily(self.args)
        log = subprocess.run(["git", "-C", self.tmp.name, "log", "--oneline"], capture_output=True, text=True)
        self.assertIn("daily run", log.stdout)


class TestRequestGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JOB_SEARCH_DIR": self.tmp.name})
        self.env.start()
        radar.tracker.upsert_tracker_row({"company": "Acme", "role": "SWE", "status": "Applied"})
        server = radar.ThreadingHTTPServer(("127.0.0.1", 0), radar.make_handler(radar.Runner(lambda: None), radar.Runner(lambda: None)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def status(self, req):
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_cross_site_and_non_json_posts_are_refused(self):
        body = json.dumps({"id": 1, "status": "Rejected"}).encode()
        evil = urllib.request.Request(self.base + "/api/tracker", method="POST", data=body,
                                      headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
        plain = urllib.request.Request(self.base + "/api/tracker", method="POST", data=body,
                                       headers={"Content-Type": "text/plain"})
        rebound = urllib.request.Request(self.base + "/api/cockpit", headers={"Host": "evil.example"})
        self.assertEqual((self.status(evil), self.status(plain), self.status(rebound)), (403, 415, 403))
        self.assertEqual(radar.tracker.load_rows()["rows"][0]["status"], "Applied")
        same = urllib.request.Request(self.base + "/api/tracker", method="POST", data=body,
                                      headers={"Content-Type": "application/json", "Origin": self.base})
        self.assertEqual(self.status(same), 200)
