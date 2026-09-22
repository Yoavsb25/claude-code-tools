import argparse
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import job_tool


class TestDecodeHtmlEntities(unittest.TestCase):
    def test_named_entities(self):
        self.assertEqual(job_tool.decode_html_entities("Tom &amp; Jerry"), "Tom & Jerry")
        self.assertEqual(job_tool.decode_html_entities("&lt;b&gt;hi&lt;/b&gt;"), "<b>hi</b>")
        self.assertEqual(job_tool.decode_html_entities("say &quot;hi&quot;"), 'say "hi"')
        self.assertEqual(job_tool.decode_html_entities("it&#39;s"), "it's")
        self.assertEqual(job_tool.decode_html_entities("it&apos;s"), "it's")

    def test_numeric_entities(self):
        self.assertEqual(job_tool.decode_html_entities("caf&#233;"), "café")
        self.assertEqual(job_tool.decode_html_entities("caf&#xE9;"), "café")

    def test_nbsp(self):
        self.assertEqual(job_tool.decode_html_entities("a&nbsp;b"), "a b")

    def test_none_passthrough(self):
        self.assertIsNone(job_tool.decode_html_entities(None))


class TestCleanText(unittest.TestCase):
    def test_strips_tags_and_decodes_entities(self):
        self.assertEqual(
            job_tool.clean_text('<span>Acme &amp; Co</span>'), "Acme & Co"
        )

    def test_none_passthrough(self):
        self.assertIsNone(job_tool.clean_text(None))


class TestJobageToTpr(unittest.TestCase):
    def test_valid_days(self):
        self.assertEqual(job_tool.jobage_to_tpr(7), "r604800")
        self.assertEqual(job_tool.jobage_to_tpr(1), "r86400")
        self.assertEqual(job_tool.jobage_to_tpr(30), "r2592000")

    def test_none_for_invalid(self):
        self.assertIsNone(job_tool.jobage_to_tpr(0))
        self.assertIsNone(job_tool.jobage_to_tpr(-5))
        self.assertIsNone(job_tool.jobage_to_tpr(None))
        self.assertIsNone(job_tool.jobage_to_tpr(9999))


class TestLinkedinWorkTypeFlag(unittest.TestCase):
    def test_known_modes(self):
        self.assertEqual(job_tool.linkedin_work_type_flag("remote"), "2")
        self.assertEqual(job_tool.linkedin_work_type_flag("hybrid"), "3")
        self.assertEqual(job_tool.linkedin_work_type_flag("onsite"), "1")
        self.assertEqual(job_tool.linkedin_work_type_flag("REMOTE"), "2")

    def test_none_for_unknown(self):
        self.assertIsNone(job_tool.linkedin_work_type_flag(None))
        self.assertIsNone(job_tool.linkedin_work_type_flag(""))
        self.assertIsNone(job_tool.linkedin_work_type_flag("bogus"))


class TestNormalizeLinkedinJobId(unittest.TestCase):
    def test_raw_id(self):
        self.assertEqual(job_tool.normalize_linkedin_job_id("4426311357"), "4426311357")

    def test_view_url(self):
        self.assertEqual(
            job_tool.normalize_linkedin_job_id(
                "https://www.linkedin.com/jobs/view/staff-engineer-at-acme-4426311357"
            ),
            "4426311357",
        )

    def test_urn(self):
        self.assertEqual(
            job_tool.normalize_linkedin_job_id("urn:li:jobPosting:4426311357"), "4426311357"
        )

    def test_invalid(self):
        self.assertIsNone(job_tool.normalize_linkedin_job_id("not-a-job"))
        self.assertIsNone(job_tool.normalize_linkedin_job_id(None))


LINKEDIN_SEARCH_HTML_FIXTURE = """
<ul>
<li>
<div class="base-card" data-entity-urn="urn:li:jobPosting:4426311357" data-search-id="abc">
  <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/staff-backend-engineer-at-acme-4426311357?refId=xyz">
    <span class="sr-only">Staff Backend Engineer</span>
  </a>
  <h3 class="base-search-card__title">Staff Backend Engineer</h3>
  <h4 class="base-search-card__subtitle">
    <a class="hidden-nested-link" href="https://www.linkedin.com/company/acme?trk=public_jobs">Acme &amp; Co</a>
  </h4>
  <span class="job-search-card__location">Remote</span>
  <time class="job-search-card__listdate" datetime="2026-06-30">3 days ago</time>
</li>
<li>
<div class="base-card" data-entity-urn="urn:li:jobPosting:4400000002">
  <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/platform-engineer-at-widgets-4400000002">
    <span class="sr-only">Platform Engineer</span>
  </a>
  <h4 class="base-search-card__subtitle">Widgets Inc</h4>
  <span class="job-search-card__location">Berlin, Germany</span>
</li>
</ul>
"""


class TestParseLinkedinCards(unittest.TestCase):
    def test_parses_full_and_partial_cards(self):
        cards = job_tool.parse_linkedin_cards(LINKEDIN_SEARCH_HTML_FIXTURE)
        self.assertEqual(len(cards), 2)

        first = cards[0]
        self.assertEqual(first["id"], "4426311357")
        self.assertEqual(first["title"], "Staff Backend Engineer")
        self.assertEqual(first["company"], "Acme & Co")
        self.assertEqual(first["location"], "Remote")
        self.assertEqual(first["posted_date"], "2026-06-30")
        self.assertEqual(
            first["url"],
            "https://www.linkedin.com/jobs/view/staff-backend-engineer-at-acme-4426311357",
        )

        second = cards[1]
        self.assertEqual(second["id"], "4400000002")
        self.assertEqual(second["title"], "Platform Engineer")
        self.assertEqual(second["company"], "Widgets Inc")
        self.assertIsNone(second["posted_date"])

    def test_skips_malformed_chunk_without_breaking_others(self):
        html = LINKEDIN_SEARCH_HTML_FIXTURE.replace(
            'data-entity-urn="urn:li:jobPosting:4400000002"',
            'data-entity-urn="urn:li:jobPosting:not-a-number"',
        )
        cards = job_tool.parse_linkedin_cards(html)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "4426311357")

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(job_tool.parse_linkedin_cards("<ul></ul>"), [])


LINKEDIN_DETAIL_HTML_FIXTURE = """
<div class="top-card-layout">
  <h1 class="top-card-layout__title">Staff Backend Engineer</h1>
  <a class="topcard__org-name-link" href="https://www.linkedin.com/company/acme?trk=public_jobs">Acme Corp</a>
  <span class="topcard__flavor topcard__flavor--bullet">Remote</span>
  <a class="topcard__link" href="https://acme.com/careers/staff-backend-engineer?src=linkedin">Apply</a>
</div>
<div class="description__text">
  <div class="show-more-less-html__markup">
    <p>We are looking for a Staff Backend Engineer.</p>
    <p>Responsibilities:</p>
    <ul>
      <li>Design APIs</li>
      <li>Mentor engineers</li>
    </ul>
  </div>
</div>
<h3 class="description__job-criteria-subheader">Seniority level</h3>
<span class="description__job-criteria-text description__job-criteria-text--criteria">Mid-Senior level</span>
<h3 class="description__job-criteria-subheader">Employment type</h3>
<span class="description__job-criteria-text description__job-criteria-text--criteria">Full-time</span>
"""


class TestParseLinkedinDetail(unittest.TestCase):
    def test_parses_full_detail(self):
        detail = job_tool.parse_linkedin_detail(LINKEDIN_DETAIL_HTML_FIXTURE, "4426311357")
        self.assertEqual(detail["id"], "4426311357")
        self.assertEqual(detail["title"], "Staff Backend Engineer")
        self.assertEqual(detail["company"], "Acme Corp")
        self.assertEqual(detail["location"], "Remote")
        self.assertIn("We are looking for a Staff Backend Engineer.", detail["description"])
        self.assertIn("Design APIs", detail["description"])
        self.assertIn("\n", detail["description"])
        self.assertEqual(detail["seniority"], "Mid-Senior level")
        self.assertEqual(detail["employment_type"], "Full-time")
        self.assertIsNone(detail["job_function"])
        self.assertEqual(detail["apply_url"], "https://acme.com/careers/staff-backend-engineer")
        self.assertEqual(detail["url"], "https://www.linkedin.com/jobs/view/4426311357")

    def test_missing_fields_degrade_gracefully(self):
        detail = job_tool.parse_linkedin_detail("<div>no matches here</div>", "999")
        self.assertEqual(detail["title"], "(untitled)")
        self.assertIsNone(detail["company"])
        self.assertIsNone(detail["description"])
        self.assertIsNone(detail["seniority"])


class TestHttpGetHtmlBackoff(unittest.TestCase):
    @patch("job_tool.urllib.request.urlopen")
    def test_success_returns_html(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>ok</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        html, err = job_tool.http_get_html_backoff("https://example.com/search")
        self.assertEqual(html, "<html>ok</html>")
        self.assertIsNone(err)
        mock_urlopen.assert_called_once()

    @patch("job_tool.urllib.request.urlopen")
    def test_404_returns_empty_string_no_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 404, "Not Found", None, None)
        html, err = job_tool.http_get_html_backoff("https://example.com/detail/999")
        self.assertEqual(html, "")
        self.assertIsNone(err)

    @patch("job_tool.time.sleep")
    @patch("job_tool.urllib.request.urlopen")
    def test_retries_on_429_then_succeeds(self, mock_urlopen, mock_sleep):
        ok_resp = MagicMock()
        ok_resp.read.return_value = b"<html>recovered</html>"
        ok_resp.__enter__.return_value = ok_resp
        mock_urlopen.side_effect = [
            urllib.error.HTTPError("url", 429, "Too Many Requests", None, None),
            ok_resp,
        ]
        html, err = job_tool.http_get_html_backoff("https://example.com/search")
        self.assertEqual(html, "<html>recovered</html>")
        self.assertIsNone(err)
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("job_tool.time.sleep")
    @patch("job_tool.urllib.request.urlopen")
    def test_gives_up_after_max_retries(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 500, "Server Error", None, None)
        html, err = job_tool.http_get_html_backoff("https://example.com/search")
        self.assertIsNone(html)
        self.assertIn("500", err)
        self.assertEqual(mock_urlopen.call_count, job_tool.LINKEDIN_MAX_RETRIES + 1)


class TestCmdSearchLinkedin(unittest.TestCase):
    def _run(self, **overrides):
        args = argparse.Namespace(
            query="backend engineer", location="Remote", jobage=None, remote=None, page=1, limit=25
        )
        for key, value in overrides.items():
            setattr(args, key, value)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_linkedin(args)
        return json.loads(buf.getvalue())

    @patch("job_tool.http_get_html_backoff")
    def test_maps_cards_into_posting_shape(self, mock_fetch):
        mock_fetch.return_value = (LINKEDIN_SEARCH_HTML_FIXTURE, None)
        out = self._run()
        self.assertEqual(out["source"], "linkedin")
        self.assertIsNone(out["error"])
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(out["results"][0]["source"], "linkedin")
        self.assertEqual(out["results"][0]["title"], "Staff Backend Engineer")
        self.assertIsNone(out["results"][0]["description"])

        called_url = mock_fetch.call_args[0][0]
        self.assertIn("keywords=backend", called_url)
        self.assertIn("location=Remote", called_url)

    @patch("job_tool.http_get_html_backoff")
    def test_error_returns_empty_results(self, mock_fetch):
        mock_fetch.return_value = (None, "HTTP 500 from linkedin")
        out = self._run()
        self.assertEqual(out["results"], [])
        self.assertEqual(out["error"], "HTTP 500 from linkedin")

    @patch("job_tool.http_get_html_backoff")
    def test_jobage_and_remote_flags_mapped(self, mock_fetch):
        mock_fetch.return_value = ("", None)
        self._run(jobage=7, remote="remote")
        called_url = mock_fetch.call_args[0][0]
        self.assertIn("f_TPR=r604800", called_url)
        self.assertIn("f_WT=2", called_url)


class TestCmdSearchLinkedinDetail(unittest.TestCase):
    def _run(self, id_value):
        args = argparse.Namespace(id=id_value)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_linkedin_detail(args)
        return json.loads(buf.getvalue())

    def test_invalid_id_returns_error_without_network_call(self):
        out = self._run("not-a-job")
        self.assertIsNone(out["result"])
        self.assertIn("could not parse a job id", out["error"])

    @patch("job_tool.http_get_html_backoff")
    def test_not_found_returns_error(self, mock_fetch):
        mock_fetch.return_value = ("", None)
        out = self._run("4426311357")
        self.assertIsNone(out["result"])
        self.assertEqual(out["error"], "job not found")

    @patch("job_tool.http_get_html_backoff")
    def test_parses_detail_on_success(self, mock_fetch):
        mock_fetch.return_value = (LINKEDIN_DETAIL_HTML_FIXTURE, None)
        out = self._run("https://www.linkedin.com/jobs/view/staff-backend-engineer-at-acme-4426311357")
        self.assertIsNone(out["error"])
        self.assertEqual(out["result"]["id"], "4426311357")
        self.assertEqual(out["result"]["title"], "Staff Backend Engineer")


class TestSaveJson(unittest.TestCase):
    def test_writes_valid_content_and_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            job_tool.save_json(path, {"a": 1})

            self.assertEqual(json.loads(path.read_text()), {"a": 1})
            self.assertFalse((Path(tmp) / "state.json.tmp").exists())

    def test_preserves_original_file_if_write_fails_partway(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"a": 1}\n', encoding="utf-8")

            with patch("job_tool.json.dump", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    job_tool.save_json(path, {"a": 2})

            self.assertEqual(json.loads(path.read_text()), {"a": 1})


class TempStateDirTestCase(unittest.TestCase):
    """Isolates job_tool's file-backed commands (profile/tracker/network) from the real
    ~/Desktop/Job-Search directory by pointing state_dir() at a temp directory for the test."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(
            job_tool, "state_dir", return_value=Path(self._tmpdir.name)
        )
        self._state_patcher.start()

    def tearDown(self):
        self._state_patcher.stop()
        self._tmpdir.cleanup()

    def _run_json(self, func, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            func(args)
        return json.loads(buf.getvalue())


class TestCmdTrackerUpsertDedup(TempStateDirTestCase):
    def test_dedupes_company_name_variants_via_normalization(self):
        self._run_json(
            job_tool.cmd_tracker_upsert,
            argparse.Namespace(row=json.dumps({"company": "Google", "role": "Staff Backend Engineer"})),
        )
        out = self._run_json(
            job_tool.cmd_tracker_upsert,
            argparse.Namespace(row=json.dumps({
                "company": "Google Inc",
                "role": "Staff Backend Engineer",
                "notes": "found on greenhouse",
            })),
        )
        data = job_tool.load_rows()
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(out["notes"], "found on greenhouse")
        self.assertEqual(out["company"], "Google Inc")


class TestCmdTrackerUpsertBehavior(TempStateDirTestCase):
    def _upsert(self, row):
        return self._run_json(job_tool.cmd_tracker_upsert, argparse.Namespace(row=json.dumps(row)))

    def test_new_row_gets_shortlisted_defaults(self):
        out = self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer"})
        self.assertEqual(out["id"], 1)
        self.assertEqual(out["status"], "Shortlisted")
        self.assertIsNone(out["fit"])
        self.assertIsNone(out["salary"])
        self.assertEqual(out["found_date"], job_tool.today_str())
        self.assertIsNone(out["applied_date"])

    def test_salary_round_trips_into_rendered_markdown(self):
        self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer", "salary": "£75k"})
        markdown = job_tool.markdown_path().read_text(encoding="utf-8")
        self.assertIn("Salary", markdown)
        self.assertIn("£75k", markdown)

    def test_second_distinct_row_gets_next_id(self):
        first = self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer"})
        second = self._upsert({"company": "Widgets Inc", "role": "Platform Engineer"})
        self.assertEqual(first["id"], 1)
        self.assertEqual(second["id"], 2)
        self.assertEqual(len(job_tool.load_rows()["rows"]), 2)

    def test_matches_by_explicit_id_even_when_company_and_role_change(self):
        created = self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer"})
        updated = self._upsert({"id": created["id"], "company": "Acme Corp", "role": "Principal Engineer"})
        rows = job_tool.load_rows()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(updated["role"], "Principal Engineer")

    def test_followup_date_set_14_days_after_applied_date(self):
        self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer"})
        out = self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer", "status": "Applied"})
        expected = (job_tool.date.today() + job_tool.timedelta(days=job_tool.DEFAULT_FOLLOWUP_DAYS)).isoformat()
        self.assertEqual(out["applied_date"], job_tool.today_str())
        self.assertEqual(out["followup_date"], expected)

    def test_followup_date_resets_to_7_days_on_interviewing(self):
        self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer", "status": "Applied"})
        out = self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer", "status": "Interviewing"})
        expected = (job_tool.date.today() + job_tool.timedelta(days=job_tool.INTERVIEW_FOLLOWUP_DAYS)).isoformat()
        self.assertEqual(out["followup_date"], expected)

    def test_missing_company_or_role_on_new_row_errors(self):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            with self.assertRaises(SystemExit):
                job_tool.cmd_tracker_upsert(argparse.Namespace(row=json.dumps({"role": "Staff Backend Engineer"})))
        self.assertIn("require both 'company' and 'role'", buf_err.getvalue())


class TestCmdProfileSet(TempStateDirTestCase):
    def _set(self, patch_dict):
        return self._run_json(job_tool.cmd_profile_set, argparse.Namespace(patch=json.dumps(patch_dict)))

    def test_first_call_creates_profile_with_updated_stamp(self):
        out = self._set({"roles": ["Staff Backend Engineer"], "locations": ["Remote EU"]})
        self.assertEqual(out["roles"], ["Staff Backend Engineer"])
        self.assertEqual(out["locations"], ["Remote EU"])
        self.assertEqual(out["updated"], job_tool.today_str())

    def test_second_call_preserves_untouched_top_level_fields(self):
        self._set({"roles": ["Staff Backend Engineer"], "locations": ["Remote EU"]})
        out = self._set({"seniority": "Staff+"})
        self.assertEqual(out["roles"], ["Staff Backend Engineer"])
        self.assertEqual(out["locations"], ["Remote EU"])
        self.assertEqual(out["seniority"], "Staff+")

    def test_array_field_patch_replaces_rather_than_merges(self):
        self._set({"locations": ["Remote EU", "London"]})
        out = self._set({"locations": ["Berlin"]})
        self.assertEqual(out["locations"], ["Berlin"])


CONNECTIONS_CSV_FIXTURE = """Notes:
"When exporting your connection data, you may notice some columns are absent."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Jane,Doe,https://www.linkedin.com/in/janedoe,,Google,Senior PM,01 Mar 2022
John,Smith,,,Google Inc,Software Engineer,15 Jun 2023
Amy,Lee,https://www.linkedin.com/in/amylee,,Metabase,Founder,10 Jan 2021
"""


class TestCmdNetworkImport(TempStateDirTestCase):
    def _import(self, csv_text):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "Connections.csv"
            csv_path.write_text(csv_text, encoding="utf-8")
            return self._run_json(job_tool.cmd_network_import, argparse.Namespace(csv=str(csv_path)))

    def test_imports_new_connections(self):
        out = self._import(CONNECTIONS_CSV_FIXTURE)
        self.assertEqual(out["added"], 3)
        self.assertEqual(out["updated"], 0)
        self.assertEqual(out["total_connections"], 3)

    def test_rerun_dedupes_by_url_and_updates_changed_fields(self):
        self._import(CONNECTIONS_CSV_FIXTURE)
        updated_csv = CONNECTIONS_CSV_FIXTURE.replace("Senior PM", "Director of Product")
        out = self._import(updated_csv)
        self.assertEqual(out["added"], 0)
        self.assertEqual(out["updated"], 1)
        self.assertEqual(out["unchanged"], 2)
        self.assertEqual(out["total_connections"], 3)

    def test_missing_file_errors(self):
        buf_err = io.StringIO()
        with contextlib.redirect_stderr(buf_err):
            with self.assertRaises(SystemExit):
                job_tool.cmd_network_import(argparse.Namespace(csv="/nonexistent/Connections.csv"))
        self.assertIn("file not found", buf_err.getvalue())


class TestCmdNetworkMatch(TempStateDirTestCase):
    def setUp(self):
        super().setUp()
        csv_path = Path(self._tmpdir.name) / "Connections.csv"
        csv_path.write_text(CONNECTIONS_CSV_FIXTURE, encoding="utf-8")
        self._run_json(job_tool.cmd_network_import, argparse.Namespace(csv=str(csv_path)))

    def test_matches_google_across_legal_suffix_variants(self):
        out = self._run_json(job_tool.cmd_network_match, argparse.Namespace(company="Google"))
        result = out["results"][0]
        self.assertEqual(result["match_count"], 2)
        names = {c["name"] for c in result["connections"]}
        self.assertEqual(names, {"Jane Doe", "John Smith"})

    def test_does_not_false_positive_on_substring(self):
        out = self._run_json(job_tool.cmd_network_match, argparse.Namespace(company="Meta"))
        result = out["results"][0]
        self.assertEqual(result["match_count"], 0)

    def test_uses_target_companies_from_profile_when_no_company_arg(self):
        self._run_json(
            job_tool.cmd_profile_set,
            argparse.Namespace(patch=json.dumps({"target_companies": [{"name": "Google"}, {"name": "Anthropic"}]})),
        )
        out = self._run_json(job_tool.cmd_network_match, argparse.Namespace(company=None))
        self.assertEqual(out["target_companies_checked"], 2)
        self.assertIn("Anthropic", out["no_match_companies"])


NETWORK_COMPANIES_CSV_FIXTURE = """First Name,Last Name,URL,Email Address,Company,Position,Connected On
A,One,https://www.linkedin.com/in/a1,,Google,Engineer,01 Jan 2022
B,Two,https://www.linkedin.com/in/b2,,Google Inc,Engineer,02 Jan 2022
C,Three,https://www.linkedin.com/in/c3,,Google LLC,Engineer,03 Jan 2022
D,Four,https://www.linkedin.com/in/d4,,Amazon Web Services (AWS),Engineer,04 Jan 2022
E,Five,https://www.linkedin.com/in/e5,,Amazon Web Services (AWS) Inc,Engineer,05 Jan 2022
F,Six,https://www.linkedin.com/in/f6,,Cloudflare,Engineer,06 Jan 2022
G,Seven,https://www.linkedin.com/in/g7,,Anthropic,Engineer,07 Jan 2022
H,Eight,https://www.linkedin.com/in/h8,,,Engineer,08 Jan 2022
"""


class TestCmdNetworkCompanies(TempStateDirTestCase):
    def setUp(self):
        super().setUp()
        csv_path = Path(self._tmpdir.name) / "Connections.csv"
        csv_path.write_text(NETWORK_COMPANIES_CSV_FIXTURE, encoding="utf-8")
        self._run_json(job_tool.cmd_network_import, argparse.Namespace(csv=str(csv_path)))
        self.out = self._run_json(job_tool.cmd_network_companies, argparse.Namespace())

    def _bucket(self, label):
        return next(b for b in self.out["buckets"] if b["label"] == label)

    def test_totals(self):
        self.assertEqual(self.out["total_connections"], 8)
        self.assertEqual(self.out["unique_companies"], 4)
        self.assertEqual(self.out["no_company_listed"], 1)

    def test_legal_suffix_variants_collapse_into_one_group_with_shortest_display_name(self):
        bucket = self._bucket("3+ connections")
        self.assertEqual(bucket["companies"], [{"company": "Google", "count": 3}])

    def test_two_connection_bucket_collapses_variants_too(self):
        bucket = self._bucket("2 connections")
        self.assertEqual(bucket["companies"], [{"company": "Amazon Web Services (AWS)", "count": 2}])

    def test_one_connection_bucket_sorted_alphabetically(self):
        bucket = self._bucket("1 connection")
        self.assertEqual(bucket["companies"], [
            {"company": "Anthropic", "count": 1},
            {"company": "Cloudflare", "count": 1},
        ])


class TestParseAtsPayload(unittest.TestCase):
    def test_greenhouse(self):
        data = {"jobs": [{
            "title": "Staff Backend Engineer", "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "departments": [{"name": "Engineering"}], "updated_at": "2026-06-01", "content": "<p>JD</p>",
        }]}
        out = job_tool.parse_ats_payload("greenhouse", "Acme", data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Staff Backend Engineer")
        self.assertEqual(out[0]["location"], "Remote")
        self.assertEqual(out[0]["tags"], ["Engineering"])
        self.assertEqual(out[0]["description"], "JD")

    def test_lever(self):
        data = [{
            "text": "Platform Engineer", "categories": {"location": "Berlin", "allLocations": ["Berlin"]},
            "hostedUrl": "https://jobs.lever.co/acme/1", "createdAt": "2026-06-01",
            "descriptionPlain": "JD text",
        }]
        out = job_tool.parse_ats_payload("lever", "Acme", data)
        self.assertEqual(out[0]["title"], "Platform Engineer")
        self.assertEqual(out[0]["location"], "Berlin")
        self.assertEqual(out[0]["tags"], ["Berlin"])

    def test_ashby(self):
        data = {"jobs": [{
            "title": "Backend Engineer", "location": "Remote", "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/acme/1", "departmentName": "Engineering",
            "publishedAt": "2026-06-01", "descriptionPlain": "JD text",
        }]}
        out = job_tool.parse_ats_payload("ashby", "Acme", data)
        self.assertEqual(out[0]["remote"], True)
        self.assertEqual(out[0]["tags"], ["Engineering"])

    def test_smartrecruiters(self):
        data = {"content": [{
            "name": "Backend Engineer", "id": "123",
            "location": {"city": "London", "country": "UK", "remote": False},
            "postingUrl": "https://jobs.smartrecruiters.com/Acme/123",
            "department": {"label": "Engineering"}, "releasedDate": "2026-06-01",
        }]}
        out = job_tool.parse_ats_payload("smartrecruiters", "Acme", data)
        self.assertEqual(out[0]["location"], "London, UK")
        self.assertEqual(out[0]["tags"], ["Engineering"])

    def test_recruitee(self):
        data = {"offers": [{
            "title": "Backend Engineer", "city": "Amsterdam", "country": "Netherlands", "remote": True,
            "careers_url": "https://acme.recruitee.com/o/backend-engineer",
            "department": "Engineering", "created_at": "2026-06-01", "description": "<p>JD</p>",
        }]}
        out = job_tool.parse_ats_payload("recruitee", "Acme", data)
        self.assertEqual(out[0]["location"], "Amsterdam, Netherlands")
        self.assertEqual(out[0]["tags"], ["Engineering"])
        self.assertEqual(out[0]["description"], "JD")

    def test_workable(self):
        data = {"jobs": [{
            "title": "Backend Engineer", "location": {"location_str": "Remote"}, "telecommute": True,
            "url": "https://apply.workable.com/acme/j/123", "department": "Engineering",
            "published_on": "2026-06-01", "description": "<p>JD</p>",
        }]}
        out = job_tool.parse_ats_payload("workable", "Acme", data)
        self.assertEqual(out[0]["location"], "Remote")
        self.assertEqual(out[0]["remote"], True)
        self.assertEqual(out[0]["tags"], ["Engineering"])


class TestCmdSearchDiscoverAts(unittest.TestCase):
    def _run(self, company, platforms=None):
        args = argparse.Namespace(company=company, slug_hint=None, platforms=platforms, query=None, limit=25)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_discover_ats(args)
        return json.loads(buf.getvalue())

    @patch("job_tool.http_get_json")
    def test_high_confidence_when_postings_found(self, mock_get):
        def fake_get(url):
            if "boards-api.greenhouse.io" in url:
                return {"jobs": [{"title": "Backend Engineer", "absolute_url": "https://x", "departments": []}]}, None
            return None, "HTTP 404"
        mock_get.side_effect = fake_get

        out = self._run("Acme Corp", platforms="greenhouse")
        self.assertEqual(out["confidence"], "high")
        self.assertEqual(out["detected_platform"], "greenhouse")
        self.assertEqual(len(out["results"]), 1)

    @patch("job_tool.http_get_json")
    def test_low_confidence_when_board_resolves_with_zero_postings(self, mock_get):
        mock_get.return_value = ({"jobs": []}, None)

        out = self._run("Acme Corp", platforms="greenhouse")
        self.assertEqual(out["confidence"], "low")
        self.assertEqual(out["detected_platform"], "greenhouse")

    @patch("job_tool.http_get_json")
    def test_none_confidence_when_nothing_resolves(self, mock_get):
        mock_get.return_value = (None, "HTTP 404")

        out = self._run("Acme Corp", platforms="greenhouse")
        self.assertEqual(out["confidence"], "none")
        self.assertIsNone(out["detected_platform"])
        self.assertEqual(out["results"], [])


class TestDetectWorkdayTenant(unittest.TestCase):
    def test_finds_tenant_in_a_bare_url(self):
        info = job_tool.detect_workday_tenant(
            "https://unitytech.wd1.myworkdayjobs.com/Unity/job/London-United-Kingdom/Manager_JOBREQ-1"
        )
        self.assertEqual(info["tenant"], "unitytech")
        self.assertEqual(info["wd_host"], "wd1")
        self.assertEqual(info["site"], "Unity")
        self.assertEqual(info["api_base"], "https://unitytech.wd1.myworkdayjobs.com/wday/cxs/unitytech/Unity")
        self.assertEqual(info["public_base"], "https://unitytech.wd1.myworkdayjobs.com/Unity")

    def test_locale_prefixed_site_resolves_to_the_segment_after_the_locale(self):
        # Real-world case (NVIDIA, verified by hand): the locale segment ("en-US") is NOT part of
        # the CXS API path -- only the site name after it is. Getting this wrong means the API
        # call 404s and a real Workday-hosted company is wrongly reported as confidence: "none".
        html = '<html><body><a href="https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers/job/x">Jobs</a></body></html>'
        info = job_tool.detect_workday_tenant(html)
        self.assertEqual(info["tenant"], "acme")
        self.assertEqual(info["wd_host"], "wd5")
        self.assertEqual(info["site"], "AcmeCareers")
        self.assertEqual(info["api_base"], "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers")

    def test_bare_locale_prefixed_url_with_no_trailing_path(self):
        info = job_tool.detect_workday_tenant("https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers")
        self.assertEqual(info["site"], "AcmeCareers")

    def test_site_without_locale_prefix_is_not_mistaken_for_one(self):
        # "Unity" doesn't look like a locale tag, so it must be treated as the site itself even
        # though a second path segment ("job") is also present in the URL.
        info = job_tool.detect_workday_tenant(
            "https://unitytech.wd1.myworkdayjobs.com/Unity/job/London-United-Kingdom/Manager_JOBREQ-1"
        )
        self.assertEqual(info["site"], "Unity")

    def test_returns_none_when_no_workday_link_present(self):
        self.assertIsNone(job_tool.detect_workday_tenant("<html>no ats links here</html>"))


class TestIsRemoteLocation(unittest.TestCase):
    def test_matches_remote_variants(self):
        self.assertTrue(job_tool.is_remote_location("Remote, United Kingdom"))
        self.assertTrue(job_tool.is_remote_location("GBR-Remote(England & Wales)"))

    def test_non_remote_and_empty(self):
        self.assertFalse(job_tool.is_remote_location("London, United Kingdom"))
        self.assertFalse(job_tool.is_remote_location(None))
        self.assertFalse(job_tool.is_remote_location(""))


TENANT_INFO_FIXTURE = {
    "tenant": "acme", "wd_host": "wd1", "site": "Acme", "company": "Acme Corp",
    "api_base": "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Acme",
    "public_base": "https://acme.wd1.myworkdayjobs.com/Acme",
}


class TestFetchWorkdayPostings(unittest.TestCase):
    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_paginates_then_fetches_detail_for_every_posting(self, mock_post, mock_get):
        # Two pages of one posting each, since WORKDAY_PAGE_SIZE is fixed at 20 and this test
        # only needs to prove the offset loop runs until it reaches `total`.
        mock_post.side_effect = [
            ({"total": 2, "jobPostings": [{"title": "A", "externalPath": "/job/A", "locationsText": "X", "postedOn": "Posted Today"}]}, None),
            ({"total": 2, "jobPostings": [{"title": "B", "externalPath": "/job/B", "locationsText": "Y", "postedOn": "Posted Today"}]}, None),
        ]
        mock_get.side_effect = [
            ({"jobPostingInfo": {"title": "A", "location": "London, United Kingdom", "postedOn": "Posted Today", "externalUrl": "https://x/A"}}, None),
            ({"jobPostingInfo": {"title": "B", "location": "Remote, United Kingdom", "additionalLocations": ["Remote, USA"], "postedOn": "Posted Today", "externalUrl": "https://x/B"}}, None),
        ]

        results, err = job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE, limit=25)
        self.assertIsNone(err)
        self.assertEqual(len(results), 2)
        self.assertEqual(mock_post.call_count, 2)  # offset 0, then offset 20 -> reaches total=2
        by_title = {r["title"]: r for r in results}
        self.assertEqual(by_title["A"]["location"], "London, United Kingdom")
        self.assertFalse(by_title["A"]["remote"])
        self.assertIn("Remote, United Kingdom", by_title["B"]["location"])
        self.assertTrue(by_title["B"]["remote"])  # primary location itself says "Remote"
        self.assertEqual(by_title["A"]["source"], "workday")
        self.assertEqual(by_title["A"]["company"], "Acme Corp")

    @patch("job_tool.http_post_json")
    def test_search_error_propagates_without_detail_fetch(self, mock_post):
        mock_post.return_value = (None, "HTTP 500 from acme")
        results, err = job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE)
        self.assertEqual(results, [])
        self.assertEqual(err, "HTTP 500 from acme")

    @patch("job_tool.http_post_json")
    def test_zero_postings_is_not_an_error(self, mock_post):
        mock_post.return_value = ({"total": 0, "jobPostings": []}, None)
        results, err = job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE)
        self.assertEqual(results, [])
        self.assertIsNone(err)

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_all_detail_fetches_failing_is_reported_as_error(self, mock_post, mock_get):
        mock_post.return_value = (
            {"total": 1, "jobPostings": [{"title": "A", "externalPath": "/job/A", "locationsText": "X", "postedOn": "Posted Today"}]},
            None,
        )
        mock_get.return_value = (None, "HTTP 500 from acme")
        results, err = job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE)
        self.assertEqual(results, [])
        self.assertIn("detail fetch", err)

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_respects_max_scanned_cap(self, mock_post, mock_get):
        page = {
            "total": 100,
            "jobPostings": [
                {"title": f"J{i}", "externalPath": f"/job/{i}", "locationsText": "X", "postedOn": "Posted Today"}
                for i in range(job_tool.WORKDAY_PAGE_SIZE)
            ],
        }
        mock_post.return_value = (page, None)
        mock_get.return_value = ({"jobPostingInfo": {"title": "J", "location": "X"}}, None)

        results, err = job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE, limit=1000, max_scanned=25)
        self.assertIsNone(err)
        self.assertLessEqual(mock_get.call_count, 25)

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_location_hint_paginates_past_max_scanned_but_only_detail_fetches_matches(self, mock_post, mock_get):
        # Simulates a large board (paginates well past max_scanned=25 during the cheap list stage)
        # where only a couple of postings actually mention the hinted location -- the expensive
        # detail-fetch stage should only run for those, not for the whole paginated list.
        pages = []
        for page_num in range(3):  # 3 pages x 20 = 60 postings paginated, only 2 relevant
            postings = []
            for i in range(job_tool.WORKDAY_PAGE_SIZE):
                idx = page_num * job_tool.WORKDAY_PAGE_SIZE + i
                if idx == 5:
                    loc = "London, United Kingdom"
                elif idx == 45:
                    loc = "3 Locations"  # ambiguous multi-location -- should also be treated as a candidate
                else:
                    loc = "Mountain View, CA, USA"
                postings.append({"title": f"J{idx}", "externalPath": f"/job/{idx}", "locationsText": loc, "postedOn": "Posted Today"})
            pages.append({"total": 60, "jobPostings": postings})
        mock_post.side_effect = [(p, None) for p in pages]
        mock_get.return_value = ({"jobPostingInfo": {"title": "J", "location": "London, United Kingdom"}}, None)

        results, err = job_tool.fetch_workday_postings(
            TENANT_INFO_FIXTURE, limit=25, max_scanned=25, location_hint="United Kingdom",
        )
        self.assertIsNone(err)
        self.assertEqual(mock_post.call_count, 3)  # pagination ran past max_scanned=25 to see all 60
        self.assertEqual(mock_get.call_count, 2)   # only the London match + the ambiguous "3 Locations" one

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_no_location_hint_keeps_pagination_and_detail_fetch_on_the_same_small_budget(self, mock_post, mock_get):
        # Without a hint, behavior must be unchanged from before this feature existed: pagination
        # stops at max_scanned just like the detail-fetch stage does.
        page = {
            "total": 1000,
            "jobPostings": [
                {"title": f"J{i}", "externalPath": f"/job/{i}", "locationsText": "X", "postedOn": "Posted Today"}
                for i in range(job_tool.WORKDAY_PAGE_SIZE)
            ],
        }
        mock_post.return_value = (page, None)
        mock_get.return_value = ({"jobPostingInfo": {"title": "J", "location": "X"}}, None)

        job_tool.fetch_workday_postings(TENANT_INFO_FIXTURE, limit=25, max_scanned=20)
        self.assertEqual(mock_post.call_count, 1)  # stopped after the first page since max_scanned=20 < page size


class TestCmdSearchDiscoverWorkday(unittest.TestCase):
    def _run(self, url, company=None, query=None, limit=25, location_hint=None):
        args = argparse.Namespace(url=url, company=company, query=query, limit=limit, location_hint=location_hint)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_discover_workday(args)
        return json.loads(buf.getvalue())

    @patch("job_tool.http_post_json")
    @patch("job_tool.http_get_html")
    def test_detects_tenant_from_career_page_html_and_fetches_postings(self, mock_html, mock_post):
        mock_html.return_value = (
            '<html><a href="https://acme.wd1.myworkdayjobs.com/Acme">Careers</a></html>', None,
        )
        mock_post.return_value = ({"total": 0, "jobPostings": []}, None)

        out = self._run("https://acme.com/careers", company="Acme Corp")
        self.assertEqual(out["detected_platform"], "workday")
        self.assertEqual(out["detected_slug"], "acme/wd1/Acme")
        self.assertEqual(out["confidence"], "low")  # tenant found, zero current postings
        self.assertIsNone(out["error"])
        mock_html.assert_called_once_with("https://acme.com/careers")

    def test_url_that_is_already_a_workday_link_skips_html_fetch(self):
        with patch("job_tool.http_get_html") as mock_html, patch("job_tool.http_post_json") as mock_post:
            mock_post.return_value = ({"total": 0, "jobPostings": []}, None)
            out = self._run("https://acme.wd1.myworkdayjobs.com/Acme/job/some-role_JOBREQ-1", company="Acme Corp")
            mock_html.assert_not_called()
            self.assertEqual(out["detected_slug"], "acme/wd1/Acme")

    @patch("job_tool.http_get_html")
    def test_no_workday_link_in_html_gives_none_confidence_not_error(self, mock_html):
        mock_html.return_value = ("<html>plain marketing content, no ATS link</html>", None)
        out = self._run("https://acme.com/careers", company="Acme Corp")
        self.assertEqual(out["confidence"], "none")
        self.assertIsNone(out["detected_platform"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["results"], [])

    @patch("job_tool.http_get_html")
    def test_career_page_fetch_failure_is_reported_as_error(self, mock_html):
        mock_html.return_value = (None, "HTTP 404 from acme.com")
        out = self._run("https://acme.com/careers", company="Acme Corp")
        self.assertEqual(out["confidence"], "none")
        self.assertEqual(out["error"], "HTTP 404 from acme.com")


class TestCmdSearchWorkdayJobs(unittest.TestCase):
    def _run(self, slug, company=None, query=None, limit=25, location_hint=None):
        args = argparse.Namespace(slug=slug, company=company, query=query, limit=limit, location_hint=location_hint)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_workday_jobs(args)
        return json.loads(buf.getvalue())

    def test_malformed_slug_errors_without_network_call(self):
        with patch("job_tool.http_post_json") as mock_post:
            out = self._run("not-a-valid-slug")
            mock_post.assert_not_called()
            self.assertIn("--slug must be", out["error"])
            self.assertEqual(out["results"], [])

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_post_json")
    def test_valid_slug_fetches_directly_without_html_lookup(self, mock_post, mock_get):
        mock_post.return_value = (
            {"total": 1, "jobPostings": [{"title": "A", "externalPath": "/job/A", "locationsText": "London, United Kingdom", "postedOn": "Posted Today"}]},
            None,
        )
        mock_get.return_value = ({"jobPostingInfo": {"title": "A", "location": "London, United Kingdom"}}, None)

        with patch("job_tool.http_get_html") as mock_html:
            out = self._run("acme/wd1/Acme", company="Acme Corp")
            mock_html.assert_not_called()
        self.assertIsNone(out["error"])
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(out["results"][0]["company"], "Acme Corp")


COMEET_INIT_HTML = """
<script>
window.comeetInit = function() {
    COMEET.init({
        "token":       "39711F3AC5AC539701CB81CB8204FE5C",
        "company-uid": "93.007",
        "company-name": "Acme Sandbox",
        "color":       "278fe6"
    });
};
</script>
"""

COMEET_POSITIONS_FIXTURE = [
    {
        "name": "AI Solution Manager", "department": "Operations",
        "location": {"city": "Ramat-Gan", "state": "Tel Aviv District", "name": "Israel", "is_remote": True},
        "url_active_page": "https://acme.com/career/ai-solution-manager/",
        "url_comeet_hosted_page": "https://www.comeet.com/jobs/acme/93.007/ai-solution-manager/34.C6F",
        "time_updated": "2026-09-13T18:46:23Z", "company_name": "Acme Corp",
    },
]


class TestDetectComeetConfig(unittest.TestCase):
    def test_extracts_token_and_company_uid(self):
        config = job_tool.detect_comeet_config(COMEET_INIT_HTML)
        self.assertEqual(config["token"], "39711F3AC5AC539701CB81CB8204FE5C")
        self.assertEqual(config["company_uid"], "93.007")

    def test_returns_none_when_no_comeet_init_present(self):
        self.assertIsNone(job_tool.detect_comeet_config("<html>no ats widget here</html>"))

    def test_returns_none_when_only_one_of_the_pair_is_present(self):
        self.assertIsNone(job_tool.detect_comeet_config('"token": "39711F3AC5AC539701CB81CB8204FE5C"'))


class TestFetchComeetPostings(unittest.TestCase):
    @patch("job_tool.http_get_json")
    def test_maps_postings_into_posting_shape(self, mock_get):
        mock_get.return_value = (COMEET_POSITIONS_FIXTURE, None)
        results, err = job_tool.fetch_comeet_postings("TOKEN123", "93.007")
        self.assertIsNone(err)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["source"], "comeet")
        self.assertEqual(r["title"], "AI Solution Manager")
        self.assertEqual(r["company"], "Acme Corp")  # falls back to the API's own company_name
        self.assertIn("Ramat-Gan", r["location"])
        self.assertTrue(r["remote"])
        self.assertEqual(r["url"], "https://acme.com/career/ai-solution-manager/")
        self.assertEqual(r["tags"], ["Operations"])

        called_url = mock_get.call_args[0][0]
        self.assertIn("company/93.007/positions", called_url)
        self.assertIn("token=TOKEN123", called_url)

    def test_explicit_company_overrides_api_company_name(self):
        with patch("job_tool.http_get_json", return_value=(COMEET_POSITIONS_FIXTURE, None)):
            results, _ = job_tool.fetch_comeet_postings("T", "U", company="Acme Sandbox")
        self.assertEqual(results[0]["company"], "Acme Sandbox")

    @patch("job_tool.http_get_json")
    def test_error_propagates(self, mock_get):
        mock_get.return_value = (None, "HTTP 500 from comeet")
        results, err = job_tool.fetch_comeet_postings("T", "U")
        self.assertEqual(results, [])
        self.assertEqual(err, "HTTP 500 from comeet")

    @patch("job_tool.http_get_json")
    def test_zero_postings_is_not_an_error(self, mock_get):
        mock_get.return_value = ([], None)
        results, err = job_tool.fetch_comeet_postings("T", "U")
        self.assertEqual(results, [])
        self.assertIsNone(err)

    @patch("job_tool.http_get_json")
    def test_query_filters_by_title(self, mock_get):
        mock_get.return_value = (COMEET_POSITIONS_FIXTURE, None)
        results, _ = job_tool.fetch_comeet_postings("T", "U", query="solution")
        self.assertEqual(len(results), 1)
        results, _ = job_tool.fetch_comeet_postings("T", "U", query="nonexistent role")
        self.assertEqual(results, [])

    @patch("job_tool.http_get_json")
    def test_unexpected_response_shape_is_an_error_not_a_crash(self, mock_get):
        mock_get.return_value = ({"not": "a list"}, None)
        results, err = job_tool.fetch_comeet_postings("T", "U")
        self.assertEqual(results, [])
        self.assertIn("unexpected response shape", err)


class TestCmdSearchDiscoverComeet(unittest.TestCase):
    def _run(self, url, company=None, query=None, limit=25):
        args = argparse.Namespace(url=url, company=company, query=query, limit=limit)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_discover_comeet(args)
        return json.loads(buf.getvalue())

    @patch("job_tool.http_get_json")
    @patch("job_tool.http_get_html")
    def test_detects_config_and_fetches_postings(self, mock_html, mock_get):
        mock_html.return_value = (COMEET_INIT_HTML, None)
        mock_get.return_value = (COMEET_POSITIONS_FIXTURE, None)

        out = self._run("https://acme.com/careers", company="Acme Corp")
        self.assertEqual(out["detected_platform"], "comeet")
        self.assertEqual(out["detected_slug"], "39711F3AC5AC539701CB81CB8204FE5C:93.007")
        self.assertEqual(out["confidence"], "high")
        self.assertIsNone(out["error"])
        self.assertEqual(len(out["results"]), 1)

    @patch("job_tool.http_get_html")
    def test_no_comeet_widget_gives_none_confidence_not_error(self, mock_html):
        mock_html.return_value = ("<html>plain marketing content</html>", None)
        out = self._run("https://acme.com/careers", company="Acme Corp")
        self.assertEqual(out["confidence"], "none")
        self.assertIsNone(out["detected_platform"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["results"], [])

    @patch("job_tool.http_get_html")
    def test_career_page_fetch_failure_is_reported_as_error(self, mock_html):
        mock_html.return_value = (None, "HTTP 404 from acme.com")
        out = self._run("https://acme.com/careers", company="Acme Corp")
        self.assertEqual(out["confidence"], "none")
        self.assertEqual(out["error"], "HTTP 404 from acme.com")


class TestCmdSearchComeetJobs(unittest.TestCase):
    def _run(self, slug, company=None, query=None, limit=25):
        args = argparse.Namespace(slug=slug, company=company, query=query, limit=limit)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_comeet_jobs(args)
        return json.loads(buf.getvalue())

    def test_malformed_slug_errors_without_network_call(self):
        with patch("job_tool.http_get_json") as mock_get:
            out = self._run("not-a-valid-slug")
            mock_get.assert_not_called()
        self.assertIn("--slug must be", out["error"])
        self.assertEqual(out["results"], [])

    @patch("job_tool.http_get_json")
    def test_valid_slug_fetches_directly_without_html_lookup(self, mock_get):
        mock_get.return_value = (COMEET_POSITIONS_FIXTURE, None)
        with patch("job_tool.http_get_html") as mock_html:
            out = self._run("TOKEN123:93.007", company="Acme Corp")
            mock_html.assert_not_called()
        self.assertIsNone(out["error"])
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(out["results"][0]["company"], "Acme Corp")


class TestFormatJobsIndexSalary(unittest.TestCase):
    def test_range(self):
        item = {"ai_salary_min_value": 80000, "ai_salary_max_value": 100000, "ai_salary_currency": "GBP", "ai_salary_unit_text": "per year"}
        self.assertEqual(job_tool._format_jobs_index_salary(item), "80000-100000 GBP per year")

    def test_single_value_when_min_equals_max(self):
        item = {"ai_salary_min_value": 90000, "ai_salary_max_value": 90000, "ai_salary_currency": "GBP", "ai_salary_unit_text": None}
        self.assertEqual(job_tool._format_jobs_index_salary(item), "90000 GBP")

    def test_none_when_no_salary_data(self):
        self.assertIsNone(job_tool._format_jobs_index_salary({}))


class TestCmdSearchJobsIndex(unittest.TestCase):
    def _run(self, **overrides):
        args = argparse.Namespace(
            company=None, domain=None, query=None, location=None, ats=None,
            work_arrangement=None, time_range="6m", limit=25,
        )
        for key, value in overrides.items():
            setattr(args, key, value)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            job_tool.cmd_search_jobs_index(args)
        return json.loads(buf.getvalue())

    def test_no_token_errors_without_network_call(self):
        with patch.dict("os.environ", {}, clear=True), patch("job_tool.http_post_json") as mock_post:
            out = self._run()
            mock_post.assert_not_called()
        self.assertIn("APIFY_TOKEN not set", out["error"])
        self.assertEqual(out["results"], [])

    @patch("job_tool.http_post_json")
    def test_builds_payload_from_all_filters_and_maps_results(self, mock_post):
        mock_post.return_value = (
            [{
                "title": "Staff Backend Engineer", "organization": "Acme Corp",
                "url": "https://acme.com/jobs/1", "date_posted": "2026-09-01",
                "description_text": "JD text", "locations_derived": ["London, England, United Kingdom"],
                "ai_work_arrangement": "Remote OK", "ai_taxonomies_a": ["Technology"],
                "ai_salary_min_value": 80000, "ai_salary_max_value": 100000,
                "ai_salary_currency": "GBP", "ai_salary_unit_text": "per year",
            }],
            None,
        )
        with patch.dict("os.environ", {"APIFY_TOKEN": "secret"}, clear=True):
            out = self._run(
                company="Acme Corp", domain="acme.com", query="Backend Engineer",
                location="London, England, United Kingdom", ats="workday,oraclecloud",
                work_arrangement="Remote OK", time_range="6m", limit=25,
            )

        payload = mock_post.call_args[0][1]
        self.assertEqual(payload["organizationSearch"], ["Acme Corp"])
        self.assertEqual(payload["domainFilter"], ["acme.com"])
        self.assertEqual(payload["titleSearch"], ["Backend Engineer"])
        self.assertEqual(payload["locationSearch"], ["London, England, United Kingdom"])
        self.assertEqual(payload["ats"], ["workday", "oraclecloud"])
        self.assertEqual(payload["aiWorkArrangementFilter"], ["Remote OK"])
        self.assertEqual(payload["timeRange"], "6m")
        self.assertEqual(payload["limit"], 25)

        headers = mock_post.call_args[1]["extra_headers"]
        self.assertEqual(headers["Authorization"], "Bearer secret")

        self.assertIsNone(out["error"])
        result = out["results"][0]
        self.assertEqual(result["title"], "Staff Backend Engineer")
        self.assertEqual(result["company"], "Acme Corp")
        self.assertEqual(result["location"], "London, England, United Kingdom")
        self.assertTrue(result["remote"])
        self.assertEqual(result["tags"], ["Technology"])
        self.assertEqual(result["salary"], "80000-100000 GBP per year")

    @patch("job_tool.http_post_json")
    def test_apify_error_propagates(self, mock_post):
        mock_post.return_value = (None, "HTTP 401 from apify.com")
        with patch.dict("os.environ", {"APIFY_TOKEN": "secret"}, clear=True):
            out = self._run()
        self.assertEqual(out["results"], [])
        self.assertEqual(out["error"], "HTTP 401 from apify.com")

    @patch("job_tool.http_post_json")
    def test_no_filters_still_sends_time_range_and_limit_only(self, mock_post):
        mock_post.return_value = ([], None)
        with patch.dict("os.environ", {"APIFY_TOKEN": "secret"}, clear=True):
            self._run()
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload, {"timeRange": "6m", "limit": 25})

    @patch("job_tool.http_post_json")
    def test_limit_below_actor_minimum_is_clamped_to_10(self, mock_post):
        # Verified directly against the live Actor: it 400s on limit < 10. A caller passing a
        # smaller --limit (e.g. trying to be cost-conscious) must not hit that raw error.
        mock_post.return_value = ([], None)
        with patch.dict("os.environ", {"APIFY_TOKEN": "secret"}, clear=True):
            self._run(limit=3)
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload["limit"], 10)


if __name__ == "__main__":
    unittest.main()
