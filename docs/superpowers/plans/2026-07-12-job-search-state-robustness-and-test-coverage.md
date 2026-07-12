# Job Search — State Robustness & Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every gap raised by the skill-reviewer audit of `tools/job-search/` (overall 8.3/10, dated 2026-07-12) that the two prior plans in this directory did not cover: generalize the shallow-merge warning beyond `target_companies`, add unit tests for the state-mutating `job_tool.py` commands (currently untested), make `save_json` crash-safe, and fix a company-name dedupe inconsistency between `tracker upsert` and `network match`.

**Architecture:** Three small, independent code/doc fixes to `tools/job-search/SKILL.md` and `tools/job-search/scripts/job_tool.py`, each landed test-first; five new test-coverage tasks that add missing unit tests without touching production code (except where the test exposes a real bug, per Task 3); one new scenario doc for the audit's remaining "needs a live run, not a code change" finding; and a version bump. No changes to `job_tool.py`'s core search/parsing logic (Remotive, Arbeitnow, LinkedIn, ATS payload shapes) — those were already covered by the prior hardening plan and this audit found no defects there.

**Tech Stack:** Python 3.9+ stdlib (`job_tool.py`), `unittest` + `unittest.mock` (`test_job_tool.py`, the existing convention in this file — not `pytest`), Markdown (`SKILL.md`), JSON (`manifest.json`).

## Global Constraints

- Every new test that touches `profile.json`/`tracker.json`/`connections.json`/`Tracker.md` must isolate itself via the `TempStateDirTestCase` helper introduced in Task 3 — no test may read or write the real `~/Desktop/Job-Search/` directory.
- `job_tool.py`'s existing reliability contract must not change: every `search`/`network`/`tracker` command still degrades to `{"error": ..., "results": []}` (or an explicit `sys.exit(1)` with a stderr message for genuinely invalid input), never a raw traceback.
- Run `python3 -m unittest test_job_tool.py -v` from `tools/job-search/scripts/` after every task that touches `job_tool.py` or `test_job_tool.py`, and confirm the count of `Ran N tests` only ever increases and `OK` is printed — this repo's job-search component uses stdlib `unittest`, not `pytest`.
- Run `npm run validate` (from repo root) after the `manifest.json` edit (Task 9) — the only automated gate that touches these files, and the repo's pre-commit hook already runs it.
- The audit's finding that "Network — warm intros" might deserve its own skill is explicitly **out of scope** for this plan — no split is implemented here. It's a judgment call for the user to make deliberately, not a defect to fix; see the plan's closing note.
- The audit's finding that Stage 2's ~40 interacting conditional rules need live validation, not just closer reading, is **not a prose-editing task** — Task 8 produces a scenario doc for a manual/benchmarked run, it does not rewrite `SKILL.md`.

## File Structure

- **Modify** `tools/job-search/SKILL.md` — one new bullet in "Key rules" generalizing the shallow-merge warning (Task 1).
- **Modify** `tools/job-search/scripts/job_tool.py` — `save_json` becomes atomic (Task 2); `cmd_tracker_upsert`'s company-match key uses `normalize_company` (Task 3).
- **Modify** `tools/job-search/scripts/test_job_tool.py` — new test classes: `TestSaveJson` (Task 2), `TempStateDirTestCase` + `TestCmdTrackerUpsertDedup` (Task 3), `TestCmdTrackerUpsertBehavior` (Task 4), `TestCmdProfileSet` (Task 5), `TestCmdNetworkImport` + `TestCmdNetworkMatch` (Task 6), `TestParseAtsPayload` + `TestCmdSearchDiscoverAts` (Task 7).
- **Create** `docs/superpowers/plans/2026-07-12-job-search-stage2-eval-scenarios.md` — three scripted multi-round scenarios for manually or benchmark-validating Stage 2's interacting conditional rules (Task 8).
- **Modify** `tools/job-search/manifest.json`, `registry.json`, root `README.md` — version bump to 1.10.0 (Task 9).

---

### Task 1: Generalize the shallow-merge warning in SKILL.md

**Files:**
- Modify: `tools/job-search/SKILL.md`

**Interfaces:**
- None (self-contained prose addition).

- [ ] **Step 1: Insert the new Key Rule**

Find this exact text in `tools/job-search/SKILL.md`:

```markdown
- **The script owns the tracker and profile files.** Never hand-edit `Tracker.md`,
  `tracker.json`, or `profile.json` directly — always go through `job_tool.py`, so state can't
  silently drift or lose rows across sessions.
- **No single search source is required.** `search remotive`/`arbeitnow`/`ats` and `WebFetch`
```

Replace it with:

```markdown
- **The script owns the tracker and profile files.** Never hand-edit `Tracker.md`,
  `tracker.json`, or `profile.json` directly — always go through `job_tool.py`, so state can't
  silently drift or lose rows across sessions.
- **Array-valued profile fields overwrite, they don't merge.** `profile set` performs a shallow
  merge (`profile.update(patch)`) — passing `locations`, `skills`, `must_haves`, `deal_breakers`,
  `industries_prefer`/`industries_avoid`, `education`, or `target_companies` replaces that field's
  entire array. Before adding or removing a single item (e.g. "add Berlin as a location," "drop
  the Kubernetes requirement"), read the field's current value from `profile show` first, splice
  the change in, and write back the full array — never patch with just the delta, or the rest of
  the list is silently dropped.
- **No single search source is required.** `search remotive`/`arbeitnow`/`ats` and `WebFetch`
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "overwrite, they don't merge" tools/job-search/SKILL.md`
Expected: one match, inside the "Key rules" section, directly after the "script owns the tracker" bullet.

- [ ] **Step 3: Commit**

```bash
git add tools/job-search/SKILL.md
git commit -m "job-search: generalize shallow-merge warning to all array-valued profile fields"
```

---

### Task 2: Make `save_json` atomic

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py:140-143`
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Produces: `save_json(path, data)` keeps its existing signature and behavior on success; on failure it now leaves the original file at `path` untouched instead of truncating it.

- [ ] **Step 1: Add `tempfile`/`Path` imports to the test file**

Find this exact text in `tools/job-search/scripts/test_job_tool.py`:

```python
import argparse
import contextlib
import io
import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

import job_tool
```

Replace it with:

```python
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
```

- [ ] **Step 2: Write the failing tests**

Find this exact text at the end of `tools/job-search/scripts/test_job_tool.py`:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify the second one fails against current code**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestSaveJson -v`
Expected: `test_writes_valid_content_and_leaves_no_tmp_file` passes; `test_preserves_original_file_if_write_fails_partway` **fails** — the current `save_json` opens `path` directly in `"w"` mode, which truncates it before `json.dump` ever raises, so `path.read_text()` no longer equals `{"a": 1}`.

- [ ] **Step 4: Implement the atomic write**

Find this exact text in `tools/job-search/scripts/job_tool.py`:

```python
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
```

Replace it with:

```python
def save_json(path, data):
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, path)
```

- [ ] **Step 5: Run tests to verify both pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestSaveJson -v`
Expected: both tests pass.

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.py -v 2>&1 | tail -5`
Expected: `OK` — no regressions in the existing 29 tests.

- [ ] **Step 6: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "job-search: make save_json atomic so a mid-write crash can't truncate tracker/profile state"
```

---

### Task 3: Add `TempStateDirTestCase` helper and fix company-name dedupe in `tracker upsert`

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py:229-243` (`cmd_tracker_upsert`)
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Produces: `TempStateDirTestCase` (a `unittest.TestCase` subclass) with a `_run_json(func, args)` helper — every later task in this plan that touches `profile`/`tracker`/`network` commands subclasses this instead of hitting the real state directory.
- Consumes: `job_tool.normalize_company()` (already defined in `job_tool.py` for the `network` commands).

- [ ] **Step 1: Write the failing test and the shared test helper**

Find this exact text at the end of `tools/job-search/scripts/test_job_tool.py`:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails against current code**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdTrackerUpsertDedup -v`
Expected: **fails** — `job_tool.load_rows()["rows"]` has length 2, because `cmd_tracker_upsert` currently matches company names with raw `strip().lower()`, so `"Google"` and `"Google Inc"` are treated as different companies and a second row is created.

- [ ] **Step 3: Fix the dedupe key**

Find this exact text in `tools/job-search/scripts/job_tool.py`:

```python
    match = None
    if patch.get("id"):
        match = next((r for r in rows if r["id"] == patch["id"]), None)
    if match is None and patch.get("company") and patch.get("role"):
        key = (patch["company"].strip().lower(), patch["role"].strip().lower())
        match = next(
            (r for r in rows if (r["company"].strip().lower(), r["role"].strip().lower()) == key),
            None,
        )
```

Replace it with:

```python
    match = None
    if patch.get("id"):
        match = next((r for r in rows if r["id"] == patch["id"]), None)
    if match is None and patch.get("company") and patch.get("role"):
        key = (normalize_company(patch["company"]), patch["role"].strip().lower())
        match = next(
            (
                r for r in rows
                if (normalize_company(r["company"]), r["role"].strip().lower()) == key
            ),
            None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdTrackerUpsertDedup -v`
Expected: passes.

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.py -v 2>&1 | tail -5`
Expected: `OK` — no regressions.

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "job-search: dedupe tracker rows by normalized company name, matching network match's logic"
```

---

### Task 4: Add remaining `tracker upsert` behavior tests

**Files:**
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `TempStateDirTestCase` from Task 3.

This task adds coverage that already passes against current code (no bug found) — it exists because this logic (new-row defaults, id-vs-company/role matching, follow-up date computation) is exactly what protects the "years of accumulated tracker rows" the skill is built around, and it had zero test coverage before this plan.

- [ ] **Step 1: Write the tests**

Find this exact text at the end of `tools/job-search/scripts/test_job_tool.py`:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with:

```python
class TestCmdTrackerUpsertBehavior(TempStateDirTestCase):
    def _upsert(self, row):
        return self._run_json(job_tool.cmd_tracker_upsert, argparse.Namespace(row=json.dumps(row)))

    def test_new_row_gets_shortlisted_defaults(self):
        out = self._upsert({"company": "Acme Corp", "role": "Staff Backend Engineer"})
        self.assertEqual(out["id"], 1)
        self.assertEqual(out["status"], "Shortlisted")
        self.assertIsNone(out["fit"])
        self.assertEqual(out["found_date"], job_tool.today_str())
        self.assertIsNone(out["applied_date"])

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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdTrackerUpsertBehavior -v`
Expected: all 6 tests pass (this is coverage of existing, correct behavior — no production code changes in this task).

- [ ] **Step 3: Commit**

```bash
git add tools/job-search/scripts/test_job_tool.py
git commit -m "job-search: add test coverage for tracker upsert defaults, id-matching, and followup-date rules"
```

---

### Task 5: Add `profile set` tests, including the shallow-merge behavior

**Files:**
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `TempStateDirTestCase` from Task 3.

The third test here locks in the exact behavior Task 1 just documented in `SKILL.md` — if a future change to `cmd_profile_set` ever turns the shallow merge into a deep merge (or vice versa), this test forces `SKILL.md`'s Key Rule to be revisited instead of silently going stale.

- [ ] **Step 1: Write the tests**

Find this exact text at the end of `tools/job-search/scripts/test_job_tool.py`:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdProfileSet -v`
Expected: all 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tools/job-search/scripts/test_job_tool.py
git commit -m "job-search: add profile set test coverage, including the shallow-merge/array-overwrite contract"
```

---

### Task 6: Add `network import`/`match`/`list` tests

**Files:**
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `TempStateDirTestCase` from Task 3.

- [ ] **Step 1: Write the tests**

Find this exact text at the end of `tools/job-search/scripts/test_job_tool.py`:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestCmdNetworkImport test_job_tool.TestCmdNetworkMatch -v`
Expected: all 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tools/job-search/scripts/test_job_tool.py
git commit -m "job-search: add network import/match test coverage, including legal-suffix matching and substring-false-positive guard"
```

---

### Task 7: Add ATS payload parsing and `discover-ats` confidence tests

**Files:**
- Test: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- None (mocks `job_tool.http_get_json`; no dependency on `TempStateDirTestCase` since neither function touches the state directory).

- [ ] **Step 1: Write the tests**

Find this exact text at the end of `tools/job-search/scripts/test_job_tool.py`:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.TestParseAtsPayload test_job_tool.TestCmdSearchDiscoverAts -v`
Expected: all 9 tests pass.

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.py -v 2>&1 | tail -5`
Expected: `OK` — full suite passes (should now report roughly 29 + 2 + 1 + 6 + 3 + 6 + 9 = 56 tests).

- [ ] **Step 3: Commit**

```bash
git add tools/job-search/scripts/test_job_tool.py
git commit -m "job-search: add ATS payload parsing and discover-ats confidence-level test coverage"
```

---

### Task 8: Write Stage 2 rule-interaction eval scenarios

**Files:**
- Create: `docs/superpowers/plans/2026-07-12-job-search-stage2-eval-scenarios.md`

**Interfaces:**
- None. This is a standalone scenario doc, not code — it exists so the audit's "needs a live run, not a code change" finding has a concrete artifact to run (manually, or via `skill-creator`'s benchmarking flow) rather than being closed by assumption.

The audit's concern: Stage 2 of `SKILL.md` has ~40 interacting conditional rules (large-enterprise ATS-skip, `discover-ats` confidence handling, Workday's three-path fallback, the proactive-discovery budget cap, and the large-enterprise baseline check all reference each other's budgets and ordering). Reading the prose confirms each rule is individually well-specified; it cannot confirm a fresh Claude instance sequences all of them correctly in one multi-round conversation. This task produces the scenarios to actually check that.

- [ ] **Step 1: Write the scenario doc**

```markdown
# job-search — Stage 2 Rule-Interaction Eval Scenarios

Companion to the 2026-07-12 skill-reviewer audit of `tools/job-search/`. Static review confirmed
Stage 2's individual rules are each well-specified, but flagged that their sheer number and
interactions (large-enterprise ATS-skip × `discover-ats` × Workday routing × the
proactive-discovery budget cap) can't be verified by reading alone. Run these three scenarios
against a fresh Claude instance with `job-search` installed — either manually, or via
`skill-creator`'s benchmarking flow — and grade the transcript against each scenario's checklist.

## Scenario 1 — Large-enterprise skip vs. `discover-ats` vs. Workday routing

**Setup:** A profile with `roles: ["Staff Backend Engineer"]`, `locations: ["Remote EU"]`, and
`target_companies` containing three entries with no `platform`/`slug` set: `"Microsoft"`,
`"Anthropic"`, `"Acme Corp"` (a fictional small company).

**Turn:** "Find me some jobs."

**Checklist — the transcript must show:**
- [ ] `Microsoft` is **not** probed via `search discover-ats` or `search ats` — SKILL.md's
  large-enterprise skip rule ("Large enterprises go straight to Stage 2b") routes it straight to
  Stage 2b's direct career-page search.
- [ ] `Anthropic` and `Acme Corp` **are** probed via `search discover-ats` first, since neither is
  an obvious large enterprise and neither has a `platform`/`slug` set.
- [ ] If `search discover-ats` for either returns `confidence: "none"`, the transcript falls back
  to Stage 2b's direct career-page search for that company — it does not report "nothing found"
  based on the `discover-ats` miss alone.
- [ ] If a `myworkdayjobs.com` URL surfaces for Microsoft during the Stage 2b career-page search,
  the transcript follows the three-path order from `references/search-fallbacks.md` § "Workday-hosted
  companies" (Apify MCP → `APIFY_TOKEN` → `WebFetch`) and does **not** attempt `search ats` on it.

## Scenario 2 — `discover-ats` low confidence is a guess, not a confirmed miss

**Setup:** Same profile as Scenario 1, but mock/observe a `search discover-ats` call for
`"Acme Corp"` that returns `confidence: "low"` (a platform resolved with zero postings).

**Turn:** "Any luck with Acme Corp?"

**Checklist — the transcript must show:**
- [ ] The low-confidence result is **not** reported to the user as "Acme Corp has no open roles."
- [ ] The transcript notes the result is a guess and either runs the Stage 2b direct career-page
  search for Acme Corp's real domain, or explicitly asks the user for Acme Corp's careers URL.

## Scenario 3 — Proactive-discovery cap is not double-counted against the large-enterprise baseline

**Setup:** A profile with `roles: ["Staff Backend Engineer"]`, `industries_prefer: ["fintech"]`,
and an **empty** `target_companies` list (no large enterprises named yet, none surfaced yet this
session).

**Turn:** "Find me some jobs" (first turn in a fresh conversation).

**Checklist — the transcript must show:**
- [ ] Proactive-discovery `WebSearch` queries run (e.g. `"who is hiring" Staff Backend Engineer
  fintech 2026`) and surface up to ~5 newly-discovered companies.
- [ ] **Separately**, 3–5 well-known large employers relevant to the role/industry are checked via
  Stage 2b's direct career-page search as the large-enterprise baseline — this set is additional
  to, not carved out of, the ~5-company proactive-discovery cap. The transcript should show more
  than 5 total newly-checked companies this round (proactive-discovery's ~5 plus the baseline's
  3–5), not exactly 5.
- [ ] Both the proactive-discovery hits and the baseline-check hits are described in the Stage 4
  summary as separate categories of "how we found this," not merged into one undifferentiated list.

## Recording results

For each scenario, note pass/fail per checklist item and paste the specific transcript excerpt
that confirms or contradicts it. Any unchecked item is a real defect in `SKILL.md`'s Stage 2 —
file it the same way the original audit findings were filed, with the specific rule text that
needs tightening.
```

- [ ] **Step 2: Verify the file**

Run: `grep -c "^## Scenario" docs/superpowers/plans/2026-07-12-job-search-stage2-eval-scenarios.md`
Expected: `3`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-07-12-job-search-stage2-eval-scenarios.md
git commit -m "job-search: add Stage 2 rule-interaction eval scenarios for a follow-up live-run validation"
```

---

### Task 9: Bump manifest version and final verification

**Files:**
- Modify: `tools/job-search/manifest.json`

**Interfaces:**
- None.

- [ ] **Step 1: Bump the version**

Find this exact text in `tools/job-search/manifest.json`:

```json
  "version": "1.9.0",
```

Replace it with:

```json
  "version": "1.10.0",
```

- [ ] **Step 2: Validate the manifest**

Run (from repo root): `npm run validate`
Expected: passes for all `tools/*/manifest.json`, including `tools/job-search/manifest.json`.

- [ ] **Step 3: Regenerate the registry**

Run (from repo root): `npm run generate-registry`
Expected: exits 0; `registry.json` and root `README.md` now reflect `job-search` v1.10.0 (check `git status` shows them modified).

- [ ] **Step 4: Run the full test suite one final time**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool.py -v 2>&1 | tail -5`
Expected: `OK`, with the test count reflecting all tests added in Tasks 2–7.

- [ ] **Step 5: Map every audit finding to a completed task**

| Audit finding | Task |
|---|---|
| Shallow-merge warning documented only for `target_companies`, not the other array fields | Task 1 |
| `cmd_tracker_upsert`, `cmd_profile_set`, `cmd_network_import`/`match`, `parse_ats_payload`, `cmd_search_discover_ats` had zero test coverage | Tasks 3–7 |
| `save_json` isn't atomic — a mid-write crash could truncate `tracker.json`/`profile.json` | Task 2 |
| `cmd_tracker_upsert` dedupes by raw string match; `network match` normalizes company names — inconsistent, causes duplicate tracker rows for name variants | Task 3 |
| "Network — warm intros" scope decision (own skill vs. stay bundled) | Out of scope — surfaced to user, not implemented |
| Stage 2's ~40 interacting conditional rules need live validation | Task 8 (scenario doc; the actual run is a follow-up action) |

If any row's task isn't checked off, stop and finish it before considering this plan complete.

- [ ] **Step 6: Commit**

```bash
git add tools/job-search/manifest.json registry.json README.md
git commit -m "job-search: bump to 1.10.0 for state-robustness and test-coverage fixes"
```

- [ ] **Step 7: Final commit check**

Run: `git log --oneline -9`
Expected: nine commits from Tasks 1–9.

Run: `git status`
Expected: clean working tree — nothing left uncommitted.
