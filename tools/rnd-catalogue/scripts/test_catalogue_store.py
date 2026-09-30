import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import catalogue_store


class TempStateDirTestCase(unittest.TestCase):
    """Isolates catalogue_store's file-backed commands from the real
    ~/Desktop/Job-Search/rnd-catalogue directory by pointing state_dir() at a temp directory."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(
            catalogue_store, "state_dir", return_value=Path(self._tmpdir.name)
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


def make_args(**kwargs):
    return Namespace(**kwargs)


class TestPostingKey(unittest.TestCase):
    def test_uses_url_when_present(self):
        key = catalogue_store.posting_key(
            {"url": "https://example.com/job/1", "company": "Acme", "title": "X", "location": "London"}
        )
        self.assertEqual(key, "https://example.com/job/1")

    def test_falls_back_to_company_title_location_when_no_url(self):
        key = catalogue_store.posting_key(
            {"company": "Acme", "title": "Staff Engineer", "location": "London"}
        )
        self.assertEqual(key, "Acme||Staff Engineer||London")


class TestDiffAndSaveNewPostings(TempStateDirTestCase):
    def test_first_run_all_postings_are_new(self):
        postings = [
            {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"},
            {"company": "Acme", "title": "Platform Engineer", "location": "Remote UK", "url": "https://acme.example/2"},
        ]
        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps(postings), companies="Acme"),
        )
        self.assertEqual(len(result["new"]), 2)
        self.assertEqual(result["unchanged_count"], 0)
        self.assertEqual(result["closed"], [])
        urls = {p["link"] for p in result["new"]}
        self.assertEqual(urls, {"https://acme.example/1", "https://acme.example/2"})


class TestDiffAndSaveUnchanged(TempStateDirTestCase):
    def test_second_run_same_posting_is_unchanged_and_last_seen_bumps(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )

        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )
        self.assertEqual(result["new"], [])
        self.assertEqual(result["unchanged_count"], 1)

        listed = self._run_json(catalogue_store.cmd_list, make_args(company=None))
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["first_seen"], catalogue_store.today_str())
        self.assertEqual(listed[0]["last_seen"], catalogue_store.today_str())


class TestDiffAndSaveClosed(TempStateDirTestCase):
    def test_posting_missing_for_queried_company_is_marked_closed(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )

        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Acme"),
        )
        self.assertEqual(len(result["closed"]), 1)
        self.assertEqual(result["closed"][0]["link"], "https://acme.example/1")

        listed = self._run_json(catalogue_store.cmd_list, make_args(company=None))
        self.assertEqual(listed, [])  # closed postings never show up in `list`

    def test_posting_missing_for_queried_company_is_marked_closed_case_insensitive(self):
        # Guards against the slug-vs-display-name mismatch: a posting stored under one casing
        # (e.g. the watchlist's display name "Acme") must still be recognized as queried when
        # --companies is passed with different casing (e.g. an ATS slug like "acme").
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )

        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="acme"),
        )
        self.assertEqual(len(result["closed"]), 1)
        self.assertEqual(result["closed"][0]["link"], "https://acme.example/1")

        listed = self._run_json(catalogue_store.cmd_list, make_args(company=None))
        self.assertEqual(listed, [])  # closed postings never show up in `list`

    def test_posting_first_seen_and_closed_same_day_is_flagged_possibly_stale(self):
        # A posting first recorded by this run's diff, and already absent from the very next
        # run's fetch, opened and closed within one calendar day -- that's the signature of two
        # runs having inconsistent fetch coverage, not a real closure.
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )
        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Acme"),
        )
        self.assertEqual(len(result["closed"]), 1)
        self.assertTrue(result["closed"][0]["possibly_stale"])

    def test_posting_closed_after_multiple_days_open_is_not_flagged_stale(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )
        data = catalogue_store.load_catalogue()
        key = catalogue_store.posting_key(posting)
        data["postings"][key]["first_seen"] = (date.today() - timedelta(days=5)).isoformat()
        catalogue_store.save_catalogue(data)

        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Acme"),
        )
        self.assertEqual(len(result["closed"]), 1)
        self.assertFalse(result["closed"][0]["possibly_stale"])

    def test_posting_missing_for_unqueried_company_is_left_untouched(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )

        # Second run: Acme's fetch errored, so it's absent from --companies -- its posting must survive.
        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Widgets Inc"),
        )
        self.assertEqual(result["closed"], [])

        listed = self._run_json(catalogue_store.cmd_list, make_args(company=None))
        self.assertEqual(len(listed), 1)


class TestDiffAndSaveReappearing(TempStateDirTestCase):
    def test_reappearing_closed_posting_counts_as_new_again(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )
        self._run_json(  # closes it
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Acme"),
        )

        result = self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )
        self.assertEqual(len(result["new"]), 1)
        self.assertIsNone(result["new"][0]["closed_date"])

        listed = self._run_json(catalogue_store.cmd_list, make_args(company=None))
        self.assertEqual(len(listed), 1)


class TestDiffAndSavePruning(TempStateDirTestCase):
    def test_posting_closed_30_plus_days_ago_is_pruned(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )

        data = catalogue_store.load_catalogue()
        key = catalogue_store.posting_key(posting)
        data["postings"][key]["closed_date"] = (date.today() - timedelta(days=31)).isoformat()
        catalogue_store.save_catalogue(data)

        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Widgets Inc"),
        )

        data_after = catalogue_store.load_catalogue()
        self.assertNotIn(key, data_after["postings"])

    def test_posting_closed_under_30_days_is_not_pruned(self):
        posting = {"company": "Acme", "title": "Staff Backend Engineer", "location": "London", "url": "https://acme.example/1"}
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([posting]), companies="Acme"),
        )

        data = catalogue_store.load_catalogue()
        key = catalogue_store.posting_key(posting)
        data["postings"][key]["closed_date"] = (date.today() - timedelta(days=10)).isoformat()
        catalogue_store.save_catalogue(data)

        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps([]), companies="Widgets Inc"),
        )

        data_after = catalogue_store.load_catalogue()
        self.assertIn(key, data_after["postings"])


class TestCmdList(TempStateDirTestCase):
    def test_list_sorted_by_company_then_title_and_filters_by_company(self):
        postings = [
            {"company": "Widgets Inc", "title": "Backend Engineer", "location": "London", "url": "https://w.example/1"},
            {"company": "Acme", "title": "Staff Engineer", "location": "London", "url": "https://acme.example/1"},
            {"company": "Acme", "title": "Data Engineer", "location": "London", "url": "https://acme.example/2"},
        ]
        self._run_json(
            catalogue_store.cmd_diff_and_save,
            make_args(postings=json.dumps(postings), companies="Acme,Widgets Inc"),
        )

        listed = self._run_json(catalogue_store.cmd_list, make_args(company=None))
        self.assertEqual([r["company"] for r in listed], ["Acme", "Acme", "Widgets Inc"])
        self.assertEqual([r["title"] for r in listed], ["Data Engineer", "Staff Engineer", "Backend Engineer"])

        filtered = self._run_json(catalogue_store.cmd_list, make_args(company="acme"))
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["company"] == "Acme" for r in filtered))


if __name__ == "__main__":
    unittest.main()
