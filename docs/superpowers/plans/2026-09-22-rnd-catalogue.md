# R&D Catalogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new sibling skill, `rnd-catalogue`, that inventories every open Engineering/Product/Data role in London/remote-UK at Yoav's watchlisted companies (`job-search`'s `target_companies`), with diffing across runs — no scoring, no tracker writes.

**Architecture:** Two-mode skill (setup / catalogue) with no HTTP code of its own — all fetching reuses `job-search`'s `scripts/job_tool.py` as a subprocess, exactly as `job-search`'s own SKILL.md already does. One new small stdlib script, `catalogue_store.py`, owns the one piece of state `job_tool.py` doesn't already model: the open/closed posting catalogue (mirrors `job_tool.py`'s ownership of `tracker.json`).

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `pathlib`, `datetime`, `unittest` — no `pytest` in this environment), Markdown for the skill files.

**Spec:** `docs/superpowers/specs/2026-09-22-rnd-catalogue-design.md`

## Global Constraints

- Reuse `job_tool.py` for every fetch — never add new HTTP/scraping code to this skill.
- Never hand-edit `catalogue.json` — only `catalogue_store.py` writes it.
- `target_companies` array-field writes always read-splice-write-back the full array — never patch with just a delta (`profile set` performs a shallow merge; array fields overwrite wholesale).
- No scoring, no salary, no `tracker.json` writes, no automatic handoff to `job-search`/`resume-tailor` — pure inventory only.
- No WebFetch/Playwright scraping fallback for companies with no structured API — excluded and reported instead.
- `catalogue_store.py` and its tests use only the Python standard library, matching `job_tool.py`/`test_job_tool.py`'s convention. Run tests with `python3 -m unittest` (no `pytest` installed in this environment).
- This environment's `git` is currently broken (unresolved Xcode license agreement, confirmed during brainstorming). If a `git commit` step fails for that reason, skip it, leave the changes on disk, and note it to the user — this is an environment issue, not a task failure.

---

## File Structure

```
~/.claude/skills/rnd-catalogue/
  SKILL.md
  README.md
  references/
    rnd-titles.md              # Engineering/Product/Data include+exclude keyword list
  scripts/
    catalogue_store.py         # stdlib-only; owns catalogue.json
    test_catalogue_store.py

~/Desktop/Job-Search/rnd-catalogue/
  catalogue.json                # created at runtime by catalogue_store.py, not by this plan
  <date>-catalogue.md            # created at runtime by the skill, not by this plan
```

This plan does not touch anything under `~/.claude/skills/job-search/` — `rnd-catalogue` only *reads* `job-search`'s `job_tool.py` and `references/search-fallbacks.md` by path.

---

### Task 1: `catalogue_store.py` — state ownership, diffing, CLI

**Files:**
- Create: `~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py`
- Create: `~/.claude/skills/rnd-catalogue/scripts/test_catalogue_store.py`

**Interfaces:**
- Consumes: nothing from other tasks (this is the foundation).
- Produces (used by Task 3/4's SKILL.md instructions, as CLI commands — not imported directly):
  - `python3 catalogue_store.py diff-and-save '<JSON array>' --companies "<comma-separated names>"` → prints `{"new": [...], "closed": [...], "unchanged_count": N, "pruned_count": N}`, persists `catalogue.json`. Each posting object in the input array needs `company`, `title`, `location`, `url` (others ignored).
  - `python3 catalogue_store.py list [--company "<name>"]` → prints a JSON array of currently-open postings (each with `company`, `title`, `location`, `link`, `first_seen`, `last_seen`, `closed_date`, `key`), sorted by company then title.

- [ ] **Step 1: Scaffold the directory and write the failing `posting_key` tests**

```bash
mkdir -p ~/.claude/skills/rnd-catalogue/scripts ~/.claude/skills/rnd-catalogue/references
```

Create `~/.claude/skills/rnd-catalogue/scripts/test_catalogue_store.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/.claude/skills/rnd-catalogue/scripts && python3 -m unittest test_catalogue_store -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'catalogue_store'`.

- [ ] **Step 3: Write the minimal implementation — state helpers and `posting_key`**

Create `~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py`:

```python
#!/usr/bin/env python3
"""stdlib-only script that owns rnd-catalogue's catalogue.json -- the running inventory of open
and recently-closed R&D postings at Yoav's watchlisted companies. Never hand-edit catalogue.json;
this script (and only this script) writes it, mirroring how job-search's job_tool.py is the only
thing that writes tracker.json/profile.json.

This script does no HTTP fetching of its own -- every posting it stores comes from job-search's
job_tool.py, called as a subprocess by the agent per rnd-catalogue's SKILL.md. This script's only
job is diffing this run's fetched-and-filtered postings against the last run's, and persisting
the result.
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

CLOSED_PRUNE_DAYS = 30


def state_dir():
    d = Path(os.environ.get("JOB_SEARCH_DIR", "~/Desktop/Job-Search")).expanduser() / "rnd-catalogue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def catalogue_path():
    return state_dir() / "catalogue.json"


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, path)


def load_catalogue():
    return load_json(catalogue_path(), {"postings": {}})


def save_catalogue(data):
    save_json(catalogue_path(), data)


def today_str():
    return date.today().isoformat()


def parse_date(s):
    if not s:
        return None
    return date.fromisoformat(s)


def read_json_arg(arg):
    raw = sys.stdin.read() if arg == "-" else arg
    return json.loads(raw)


def posting_key(p):
    """Stable identity for a posting across runs. A posting's apply URL is normally unique and
    stable, so it's the preferred key; fall back to company+title+location for the rare case a
    source doesn't supply one."""
    url = (p.get("url") or "").strip()
    if url:
        return url
    return f"{p.get('company', '')}||{p.get('title', '')}||{p.get('location', '')}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/.claude/skills/rnd-catalogue/scripts && python3 -m unittest test_catalogue_store -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing test for first-run new-posting detection**

Add to `test_catalogue_store.py` (before the `if __name__` line):

```python
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
```

- [ ] **Step 6: Run to verify it fails**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: FAIL — `AttributeError: module 'catalogue_store' has no attribute 'cmd_diff_and_save'`.

- [ ] **Step 7: Implement `cmd_diff_and_save` — new-posting detection**

Append to `catalogue_store.py`:

```python
def cmd_diff_and_save(args):
    run_postings = read_json_arg(args.postings)
    queried_companies = (
        {c.strip() for c in args.companies.split(",") if c.strip()} if args.companies else set()
    )

    data = load_catalogue()
    stored = data["postings"]
    today = today_str()

    seen_keys = set()
    new_out = []
    unchanged_count = 0

    for p in run_postings:
        key = posting_key(p)
        seen_keys.add(key)
        existing = stored.get(key)
        if existing is None or existing.get("closed_date"):
            first_seen = existing["first_seen"] if existing else today
            record = {
                "company": p.get("company"), "title": p.get("title"), "location": p.get("location"),
                "link": p.get("url"), "first_seen": first_seen, "last_seen": today, "closed_date": None,
            }
            stored[key] = record
            new_out.append({**record, "key": key})
        else:
            existing["last_seen"] = today
            existing["company"] = p.get("company")
            existing["title"] = p.get("title")
            existing["location"] = p.get("location")
            existing["link"] = p.get("url")
            unchanged_count += 1

    closed_out = []

    save_catalogue(data)
    print(json.dumps(
        {"new": new_out, "closed": closed_out, "unchanged_count": unchanged_count, "pruned_count": 0},
        indent=2,
    ))
```

- [ ] **Step 8: Run to verify it passes**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: PASS (3 tests).

- [ ] **Step 9: Write the failing test for unchanged postings and `last_seen` bumping**

Add:

```python
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
```

- [ ] **Step 10: Run to verify it fails**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: FAIL — `AttributeError: module 'catalogue_store' has no attribute 'cmd_list'` (the unchanged-detection logic from Step 7 already passes; `cmd_list` doesn't exist yet).

- [ ] **Step 11: Implement `cmd_list`**

Append to `catalogue_store.py`:

```python
def cmd_list(args):
    data = load_catalogue()
    rows = [
        {**record, "key": key}
        for key, record in data["postings"].items()
        if not record.get("closed_date")
    ]
    if args.company:
        wanted = args.company.strip().lower()
        rows = [r for r in rows if (r.get("company") or "").strip().lower() == wanted]
    rows.sort(key=lambda r: (r.get("company") or "", r.get("title") or ""))
    print(json.dumps(rows, indent=2))
```

- [ ] **Step 12: Run to verify it passes**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: PASS (4 tests).

- [ ] **Step 13: Write the failing tests for closed-posting detection**

Add:

```python
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
```

- [ ] **Step 14: Run to verify they fail**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: FAIL — `test_posting_missing_for_queried_company_is_marked_closed` fails (`result["closed"]` is `[]`, expected length 1); the unqueried-company test passes already since nothing marks anything closed yet.

- [ ] **Step 15: Implement closed-posting detection in `cmd_diff_and_save`**

In `catalogue_store.py`, replace the line `closed_out = []` (just before `save_catalogue(data)`) with:

```python
    closed_out = []
    for key, record in stored.items():
        if key in seen_keys:
            continue
        company = record.get("company")
        if company not in queried_companies:
            continue  # this company wasn't (successfully) queried this run -- leave it alone
        if record.get("closed_date"):
            continue  # already marked closed
        record["closed_date"] = today
        closed_out.append({**record, "key": key})
```

- [ ] **Step 16: Run to verify they pass**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: PASS (6 tests).

- [ ] **Step 17: Write the failing test for a closed posting reappearing**

Add:

```python
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
```

- [ ] **Step 18: Run to verify it passes without further changes**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: PASS (7 tests) — Step 7's `existing is None or existing.get("closed_date")` branch already covers this case; no implementation change needed here.

- [ ] **Step 19: Write the failing tests for 30-day pruning**

Add:

```python
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
```

- [ ] **Step 20: Run to verify they fail**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: FAIL — `test_posting_closed_30_plus_days_ago_is_pruned` fails (the key is still present; nothing prunes yet). The under-30-days test passes already (nothing removes it).

- [ ] **Step 21: Implement pruning**

In `catalogue_store.py`, replace `save_catalogue(data)` (the line just before the final `print(json.dumps(...))` in `cmd_diff_and_save`) with:

```python
    cutoff = date.today() - timedelta(days=CLOSED_PRUNE_DAYS)
    pruned_keys = [
        key for key, record in stored.items()
        if record.get("closed_date") and parse_date(record["closed_date"]) <= cutoff
    ]
    for key in pruned_keys:
        del stored[key]

    save_catalogue(data)
```

And update the final `print(json.dumps(...))` call's dict literal to use `len(pruned_keys)` instead of the hardcoded `0` for `"pruned_count"`.

- [ ] **Step 22: Run to verify they pass**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: PASS (9 tests).

- [ ] **Step 23: Write the failing test for `list`'s sort order and company filter**

Add:

```python
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
```

- [ ] **Step 24: Run to verify it passes without further changes**

Run: `python3 -m unittest test_catalogue_store -v`
Expected: PASS (10 tests) — Step 11's `cmd_list` already sorts and filters correctly; this step only adds coverage.

- [ ] **Step 25: Wire up the CLI (`argparse`)**

Append to `catalogue_store.py`:

```python
def build_parser():
    parser = argparse.ArgumentParser(prog="catalogue_store.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_diff = sub.add_parser("diff-and-save")
    p_diff.add_argument("postings", help="JSON array of this run's filtered postings, or '-' to read from stdin")
    p_diff.add_argument(
        "--companies", required=True,
        help="Comma-separated names of companies actually queried (successfully) this run",
    )
    p_diff.set_defaults(func=cmd_diff_and_save)

    p_list = sub.add_parser("list")
    p_list.add_argument("--company", help="Filter to one company (case-insensitive exact match)")
    p_list.set_defaults(func=cmd_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 26: Run the full test suite**

Run: `cd ~/.claude/skills/rnd-catalogue/scripts && python3 -m unittest test_catalogue_store -v`
Expected: PASS (10 tests, 0 failures).

- [ ] **Step 27: Manual CLI smoke test**

```bash
cd ~/.claude/skills/rnd-catalogue/scripts
SMOKE_DIR=$(mktemp -d)
JOB_SEARCH_DIR="$SMOKE_DIR" python3 catalogue_store.py diff-and-save \
  '[{"company":"Acme","title":"Staff Engineer","location":"London","url":"https://acme.example/1"}]' \
  --companies "Acme"
JOB_SEARCH_DIR="$SMOKE_DIR" python3 catalogue_store.py list
rm -rf "$SMOKE_DIR"
```
Expected: the `diff-and-save` call prints JSON with one entry in `"new"` and `"unchanged_count": 0`; the `list` call prints a JSON array with that one posting.

- [ ] **Step 28: Commit**

```bash
cd ~/.claude/skills/rnd-catalogue
git init -q 2>/dev/null || true
git add scripts/catalogue_store.py scripts/test_catalogue_store.py
git commit -m "feat(rnd-catalogue): add catalogue_store.py — diffing and persistence for the R&D posting catalogue"
```
If this fails because `git` is unusable in this environment (see Global Constraints), skip it and note that to the user — the files are already on disk.

---

### Task 2: R&D title taxonomy reference

**Files:**
- Create: `~/.claude/skills/rnd-catalogue/references/rnd-titles.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a reference file Task 4's SKILL.md Stage 2 points to by path (`references/rnd-titles.md`, relative to the skill directory) — no code interface, just content the agent reads at run time.

- [ ] **Step 1: Write the reference file**

Create `~/.claude/skills/rnd-catalogue/references/rnd-titles.md`:

```markdown
# R&D title taxonomy — Engineering / Product / Data

Used by catalogue mode's Stage 2 (see `../SKILL.md`) to decide whether a posting counts as
"R&D" for the inventory. Match against the posting's **title** first; where a `tags`/department
field is available (Greenhouse and Lever both expose one), use it as a corroborating veto, not
the primary signal — see "Department-tag veto" below.

## Include — title contains any of

**Engineering**
Software Engineer, Software Developer, Backend Engineer, Front End / Frontend Engineer, Full
Stack Engineer, Platform Engineer, Infrastructure Engineer, DevOps Engineer, Site Reliability
Engineer / SRE, Systems Engineer, Cloud Engineer, Security Engineer, QA Engineer, Test Engineer,
Automation Engineer, Embedded Engineer, Firmware Engineer, Mobile Engineer, iOS Engineer, Android
Engineer, ML Engineer, Machine Learning Engineer, AI Engineer, Data Engineer, Release Engineer,
Build Engineer, Tools Engineer, Developer Experience Engineer, Internal Tools Engineer,
Engineering Manager, Head of Engineering, VP Engineering, Director of Engineering, Staff
Engineer, Principal Engineer.

**Product**
Product Manager, Technical Product Manager, Senior/Staff/Principal Product Manager, Technical
Program Manager, Technical Project Manager, Group Product Manager, Head of Product, VP Product,
Director of Product.

**Data**
Data Scientist, Data Analyst, Data Engineer (also listed under Engineering — same role, matches
either way), Analytics Engineer, Research Scientist, Applied Scientist, Research Engineer, ML
Scientist.

## Exclude — title contains any of, even if it also matches an include term above

Sales Engineer, Solutions Engineer (pre-sales flavor — check the JD if ambiguous; a posting
reporting into a Sales/Customer Success org is pre-sales even with "Engineer" in the title),
Sales Development, Customer Success Engineer, Support Engineer (unless clearly an internal
platform/tools role, not customer-facing support), Field Engineer (construction/industrial
sense), Recruiting/Talent, Marketing, Business Development, Account Manager/Executive, Finance,
Legal, HR/People, Office/Facilities.

## Department-tag veto (when available)

If the posting's `tags` list includes any of: Sales, Marketing, Business Development, Customer
Success, Finance, Legal, People/HR, G&A — exclude it regardless of title match. Greenhouse/Lever
populate `tags` from the board's own department field; treat it as more reliable than the title
alone when present.

## Ambiguous — use judgment, don't auto-exclude

- "Analyst" alone (could be Data Analyst, Business Analyst, Security Analyst) — check the JD.
- "Automation Engineer" (could be software test automation, or industrial/PLC automation) — the
  same ambiguity `job-search`'s own SKILL.md documents; check the JD before deciding.
- "Program Manager" without "Technical" — often non-R&D (e.g. a marketing/ops program manager);
  only include if the JD is clearly engineering/product-scoped.
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -c '^## ' ~/.claude/skills/rnd-catalogue/references/rnd-titles.md`
Expected: `4` (Include, Exclude, Department-tag veto, Ambiguous).

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/rnd-catalogue
git add references/rnd-titles.md
git commit -m "docs(rnd-catalogue): add R&D title taxonomy reference"
```
Skip if `git` is unusable in this environment (see Global Constraints) — note it to the user.

---

### Task 3: `SKILL.md` — frontmatter and Setup mode

**Files:**
- Create: `~/.claude/skills/rnd-catalogue/SKILL.md`

**Interfaces:**
- Consumes: `~/.claude/skills/job-search/scripts/job_tool.py`'s `profile show`/`profile set`/`search discover-ats`/`search discover-workday`/`search discover-comeet`/`search jobs-index` commands (existing, unmodified); `~/.claude/skills/job-search/references/search-fallbacks.md` (read by path).
- Produces: the `name`/`description` frontmatter that makes this skill discoverable, and the Setup mode instructions Task 4 continues after.

- [ ] **Step 1: Write the frontmatter and Setup mode section**

Create `~/.claude/skills/rnd-catalogue/SKILL.md`:

```markdown
---
name: rnd-catalogue
description: >
  Builds and maintains a running inventory of every open R&D role (Engineering, Product, Data) at
  Yoav's watchlisted companies (profile.json's target_companies, shared with job-search) in London
  or remote-UK — grouped by company, flagged for what's new or closed since the last run. Pure
  inventory: no fit scoring, no tracker writes. Use this whenever Yoav wants to see what a company
  he likes actually has open right now, rather than searching by keyword — e.g. "what's open at my
  target companies", "check my watchlist for R&D roles", "catalogue my companies", "what does
  NVIDIA have open", "resolve the ATS platforms for my watchlist" (setup mode), or "run the R&D
  catalogue". If he wants roles scored against his profile or wants to apply, hand the ones he
  likes to job-search or resume-tailor directly — this skill only inventories, it never scores or
  tracks.
---

# R&D Catalogue

You are building a browsable inventory of what Yoav's watchlisted companies (`target_companies`
in `profile.json`, shared with `job-search`) currently have open in Engineering, Product, and
Data — filtered to London/remote-UK, with no fit scoring and no tracker writes. That boundary is
deliberate: this skill answers "what does this company have open", `job-search` answers "what
should I apply to."

All fetching reuses `job-search`'s `scripts/job_tool.py` directly — this skill has no HTTP code
of its own. It owns exactly one small piece of state `job_tool.py` doesn't already model: the
open/closed posting catalogue, via `scripts/catalogue_store.py`. **Never hand-edit
`catalogue.json`** — same rule as `job-search`'s tracker/profile files.

This skill has two modes. Which one runs is decided by what the user asked for:

- **Setup mode** — resolves ATS platforms for watchlist companies that don't have one yet. Run
  it once, and again whenever new companies are added to the watchlist. Triggers: "resolve the
  ATS platforms", "set up the catalogue", "add X to my watchlist" (if X has no platform), or
  automatically the first time catalogue mode finds unresolved companies (see Catalogue mode
  Stage 0).
- **Catalogue mode** — the recurring inventory run. Triggers: "what's open at my target
  companies", "catalogue my companies", "run the R&D catalogue", "what does [watchlisted
  company] have open".

---

## Setup mode

### Stage 0 — Partition the watchlist

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile show
```

Read `target_companies`. Partition into:
- **Resolved** — has both `platform` and `slug`.
- **Unresolved** — has neither.
- **`other`** — `platform: "other"` (a known custom career site, confirmed not on any of the six
  ATS platforms or Workday/Comeet).

If everything is already resolved, say so and stop — nothing to do.

### Stage 1 — Find each unresolved company's career-page URL

`discover-workday` and `discover-comeet` both require a `--url` to scan (they read that page's
HTML for an embedded tenant link or widget config — `discover-ats` doesn't need this, it guesses
slugs directly from the company name). For each unresolved company, in order:

1. If the profile entry already has a `careers_url` (saved from a prior setup run), use it.
2. Otherwise try the obvious pattern first — `https://www.<company-domain-guess>.com/careers` —
   by just passing it straight to Stage 2's `discover-workday`/`discover-comeet` calls below; a
   wrong guess degrades to `confidence: "none"`/no error, it doesn't cost anything extra to try.
3. If the guess is clearly wrong (e.g. you don't know the company's domain at all) or both
   Stage 2 calls come back empty for it, run one `WebSearch` for `"<Company Name>" careers page`
   and take the top result's URL.

**This is the one WebSearch this mode allows, and it's finding a URL, not reading job listings**
— it never substitutes for the structured API calls in Stage 2, and this skill never falls
through to WebFetch/Playwright scraping of a custom career site the way `job-search`'s Stage 2b
does. That's an intentional, narrower boundary than `job-search` has.

Save whatever URL you end up using back to that company's `target_companies` entry as
`careers_url` (splice into the full array via `profile set`, same as Stage 4 below) even if
discovery ultimately misses — it saves the WebSearch on the next setup run.

### Stage 2 — Run the free structured-discovery sweep

For each unresolved company, run all three in parallel:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-ats --company "<Company Name>"
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-workday --url "<career-page URL from Stage 1>" --company "<Company Name>"
python3 ~/.claude/skills/job-search/scripts/job_tool.py search discover-comeet --url "<career-page URL from Stage 1>" --company "<Company Name>"
```
Read `~/.claude/skills/job-search/references/search-fallbacks.md` (in `job-search`'s directory —
read it from there, don't copy it) for the `confidence` contract: `"high"` means trust it,
`"low"` means a real board with zero current postings (not a miss), `"none"` means try the next
source.

### Stage 3 — One paid fallback, with confirmation

If all three of Stage 2 come back `confidence: "none"` for a company, **ask the user before
spending anything further**: `"[Company] isn't on any free source — want me to check the paid
jobs-index for it? (see job-search's README for cost)"`. If yes:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search jobs-index --company "<Company Name>" --limit 25
```
This is still a structured API, not scraping — it's `job-search`'s own paid fallback, reused
here rather than reimplemented. If the user declines, or this also misses, the company is
excluded from the catalogue (see Stage 5) — don't fall through to WebFetch/Playwright.

### Stage 4 — Persist every hit

For every company Stage 2 or 3 resolved, read the current `target_companies` fresh, splice in
`platform`/`slug` (and `careers_url` from Stage 1) by matching `name` case-insensitively, and
write back the **full array** — `profile set` replaces `target_companies` wholesale, it does not
merge:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile set '{"target_companies": [ ...existing entries unchanged..., {"name": "<Company>", "platform": "<platform>", "slug": "<slug>", "careers_url": "<url>"} ]}'
```

### Stage 5 — Report coverage

```
## 🔧 R&D Catalogue — setup
Resolved this run: N — [Company (platform)], ...
Already resolved: M
Excluded — no API found: K — [Company], ... (career page: <url> if found, for manual reference)
```
End with: **"Run the catalogue now?"** if any companies are resolved and this wasn't triggered
automatically from catalogue mode's Stage 0.
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -n '^## \|^### ' ~/.claude/skills/rnd-catalogue/SKILL.md`
Expected output includes, in order: `## Setup mode`, `### Stage 0 — Partition the watchlist`,
`### Stage 1 — Find each unresolved company's career-page URL`, `### Stage 2 — Run the free
structured-discovery sweep`, `### Stage 3 — One paid fallback, with confirmation`, `### Stage 4 —
Persist every hit`, `### Stage 5 — Report coverage`.

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/rnd-catalogue
git add SKILL.md
git commit -m "docs(rnd-catalogue): add SKILL.md frontmatter and Setup mode"
```
Skip if `git` is unusable in this environment (see Global Constraints) — note it to the user.

---

### Task 4: `SKILL.md` — Catalogue mode and Key rules

**Files:**
- Modify: `~/.claude/skills/rnd-catalogue/SKILL.md` (append after Task 3's content)

**Interfaces:**
- Consumes: `job_tool.py`'s `search ats`/`search workday-jobs`/`search comeet-jobs` commands (existing, unmodified); Task 1's `catalogue_store.py diff-and-save`/`list` commands (`{"new": [...], "closed": [...], "unchanged_count": N, "pruned_count": N}` return shape from `diff-and-save`; array-of-posting-dicts return shape from `list`); Task 2's `references/rnd-titles.md`.
- Produces: nothing further downstream — this is the last content task that defines behavior; Task 5's README just documents what's already built.

- [ ] **Step 1: Append the Catalogue mode and Key rules sections**

Append to `~/.claude/skills/rnd-catalogue/SKILL.md`:

```markdown

---

## Catalogue mode

### Stage 0 — Load state

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py profile show
python3 ~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py list
```
Use only resolved `target_companies` entries (has `platform` + `slug`). If any are unresolved
and setup mode hasn't been run yet, mention it in the closing summary and offer to run setup
mode — but proceed with whatever's already resolved rather than blocking the whole run on it.

### Stage 1 — Fetch every resolved company's full board

No `--query` on any of these — that's what makes it a whole-board fetch instead of a keyword
search. Run all companies in parallel:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search ats --platform <platform> --company <slug> --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search workday-jobs --slug <slug> --company "<name>" --location-hint "United Kingdom" --limit 500
python3 ~/.claude/skills/job-search/scripts/job_tool.py search comeet-jobs --slug <slug> --company "<name>" --limit 500
```
`--location-hint` matters specifically for Workday: detail-fetching is capped at 150 postings
per company regardless of `--limit`, so for a large board (NVIDIA: 2,000+ postings company-wide)
the hint is what makes sure that budget is spent on UK-relevant postings instead of the first
150 encountered. Always pass it for `workday-jobs` — it's harmless on small boards.

A company whose call returns a non-null `error` is skipped for this run, not treated as "zero
postings" — note it in the Stage 4 summary and make sure it's **excluded** from the
`--companies` list passed to Stage 3, so `catalogue_store.py` doesn't wrongly mark its previously
open postings as closed just because this run couldn't reach it.

### Stage 2 — Filter to London/remote-UK, Engineering/Product/Data

For every posting from Stage 1:
- **Location**: keep if it's London, or marked/tagged remote in a way that includes the UK
  (judge from `location`/`remote`/`tags` — same holistic judgment `job-search` already applies,
  no separate script for this).
- **R&D scope**: read `references/rnd-titles.md`. Keep if the title matches an include keyword
  and isn't excluded by the exclude list. Where the posting has a `tags` list (Greenhouse/Lever
  populate this from the board's own department/category field), treat a tag that's obviously
  non-R&D (Sales, Marketing, HR, Finance, Legal, Customer Success) as a veto even if the title
  alone would have matched — this is a real signal, not a guess, when the source provides it.

### Stage 3 — Diff and persist

```bash
python3 ~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py diff-and-save '<JSON array of Stage 2's filtered postings>' --companies "<comma-separated names of companies actually queried successfully in Stage 1>"
```
Each posting object needs at least `company`, `title`, `location`, `url`. The script returns
`{"new": [...], "closed": [...], "unchanged_count": N, "pruned_count": N}` and persists the
merged `catalogue.json` — this is the only thing that writes that file.

### Stage 4 — Present, grouped by company

```bash
python3 ~/.claude/skills/rnd-catalogue/scripts/catalogue_store.py list
```
Build one table per company from this (now-updated) open list, flagging 🆕 next to any row whose
`key` was in Stage 3's `new` output. Below the tables, a short "closed since last run" list from
Stage 3's `closed` output, grouped by company.

```
## 🗂️ R&D Catalogue — [date]

Checked N companies ([list]). Skipped: [unresolved companies, or "none"]. Errors: [companies
whose fetch failed this run, or "none"].

### Acme Corp
| Role | Location | First seen | Link |
|---|---|---|---|
| 🆕 Staff Backend Engineer | London | 2026-09-22 | [Apply →](url) |
| Platform Engineer | Remote UK | 2026-09-01 | [Apply →](url) |

**Closed since last run:** Widgets Inc — Senior Data Engineer
```
No fit score, no salary column, no Skills Fit column — pure inventory.

### Stage 5 — Save the snapshot

Write the exact markdown from Stage 4 to
`~/Desktop/Job-Search/rnd-catalogue/<date>-catalogue.md` (create the `rnd-catalogue/` directory
first if needed). Re-running the same day overwrites that day's file, same convention as
`job-search`'s `searches/` directory.

### Stage 6 — Hand off, don't chain

Close with: **"Want any of these scored or a resume tailored? Hand the ones you like to
job-search or resume-tailor directly."** Never invoke either automatically — the user decides
which rows are worth that next step.

---

## Key rules

- **`catalogue_store.py` owns `catalogue.json`.** Never hand-edit it — same reasoning as
  `job-search`'s tracker/profile files: state can't silently drift or lose rows across runs.
- **`job_tool.py` owns all fetching.** This skill never adds its own HTTP code — every posting
  comes from a `job_tool.py search` call, reused exactly as `job-search` calls it.
- **`target_companies` is shared state.** Setup mode's `profile set` calls follow the same
  splice-the-full-array discipline `job-search` documents — read fresh, splice, write back whole,
  never patch with just the delta.
- **No scraping fallback, ever.** If `discover-ats`/`discover-workday`/`discover-comeet`/
  `jobs-index` all miss, the company is excluded and reported — this skill never falls through to
  WebFetch/Playwright reading of a custom career site. That's `job-search`'s Stage 2b, deliberately
  out of scope here.
- **Pure inventory — no scoring, no tracker writes.** This skill never calls `tracker upsert` and
  never computes a fit score. If the user wants either, point them at `job-search`.
- **A company that errors this run is excluded from Stage 3's `--companies` list**, not treated
  as having zero postings — otherwise its real open postings would get wrongly marked closed.
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -n '^## \|^### ' ~/.claude/skills/rnd-catalogue/SKILL.md`
Expected output now also includes, in order after Task 3's sections: `## Catalogue mode`,
`### Stage 0 — Load state`, `### Stage 1 — Fetch every resolved company's full board`,
`### Stage 2 — Filter to London/remote-UK, Engineering/Product/Data`, `### Stage 3 — Diff and
persist`, `### Stage 4 — Present, grouped by company`, `### Stage 5 — Save the snapshot`,
`### Stage 6 — Hand off, don't chain`, `## Key rules`.

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/rnd-catalogue
git add SKILL.md
git commit -m "docs(rnd-catalogue): add Catalogue mode and Key rules"
```
Skip if `git` is unusable in this environment (see Global Constraints) — note it to the user.

---

### Task 5: `README.md`

**Files:**
- Create: `~/.claude/skills/rnd-catalogue/README.md`

**Interfaces:**
- Consumes: nothing (documents what Tasks 1–4 already built).
- Produces: nothing downstream.

- [ ] **Step 1: Write the README**

Create `~/.claude/skills/rnd-catalogue/README.md`:

```markdown
# rnd-catalogue

Builds a running inventory of every open Engineering/Product/Data role, in London or remote-UK,
at the companies on Yoav's watchlist (`job-search`'s `target_companies`) — grouped by company,
flagged for what's new or closed since the last run. Pure inventory: no fit scoring, no tracker
writes. For scored, trackable results, use `job-search` directly.

## How it works

1. **Setup mode** (run once, and again when companies are added) — resolves an ATS platform for
   every watchlist company that doesn't have one yet, via `job-search`'s own
   `discover-ats`/`discover-workday`/`discover-comeet` (and, with confirmation, the paid
   `jobs-index`), and saves the result back to the shared `target_companies` list.
2. **Catalogue mode** (the recurring run) — fetches every resolved company's *entire* current
   board (no keyword filter), keeps only London/remote-UK postings in Engineering, Product, or
   Data (see `references/rnd-titles.md`), diffs against the last run's snapshot, and presents one
   table per company with new postings flagged and closed ones noted.

## Bookkeeping script

`scripts/catalogue_store.py` is a stdlib-only Python script that owns one JSON file — it's the
only thing that should ever write it:

```bash
python3 scripts/catalogue_store.py diff-and-save '<JSON array of this run's postings>' --companies "Acme Corp,Widgets Inc"
python3 scripts/catalogue_store.py list [--company "Acme Corp"]
```

State lives in `~/Desktop/Job-Search/rnd-catalogue/` by default (override with `JOB_SEARCH_DIR`,
same env var `job-search` uses): `catalogue.json` (source of truth for open/closed postings) and
a dated `<date>-catalogue.md` snapshot per run. Postings missing from a run are marked
`closed_date` rather than deleted, and pruned after 30 days closed.

All fetching is done by `job-search`'s `scripts/job_tool.py` — this skill has no HTTP code of
its own and depends on `job-search` being installed alongside it
(`references/search-fallbacks.md` is read directly from `job-search`'s directory, not copied).

## Design spec

See `~/Desktop/Job-Search/docs/superpowers/specs/2026-09-22-rnd-catalogue-design.md` for the full
design rationale.

## Tests

```bash
cd scripts && python3 -m unittest test_catalogue_store -v
```
```

- [ ] **Step 2: Verify it reads correctly**

Run: `cat ~/.claude/skills/rnd-catalogue/README.md | head -5`
Expected: starts with `# rnd-catalogue` followed by the one-paragraph summary.

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/rnd-catalogue
git add README.md
git commit -m "docs(rnd-catalogue): add README"
```
Skip if `git` is unusable in this environment (see Global Constraints) — note it to the user.

---

## After this plan

The skill is built but not yet run against real data — no task in this plan invokes setup mode
or catalogue mode against Yoav's real `profile.json`, since that mutates shared state
(`target_companies`) and is Yoav's call to trigger, not something to do silently as part of
building the skill. Once this plan is complete, the natural next step is Yoav saying something
like "resolve the ATS platforms for my watchlist" to kick off setup mode for real.
