# LinkedIn Job Search Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `search linkedin` and `search linkedin-detail` subcommands to `job_tool.py`, sourcing postings directly from LinkedIn's public `jobs-guest` endpoints (no auth), to fix the unreliable WebFetch-on-LinkedIn enrichment step documented in the job-search SKILL.md.

**Architecture:** Two new subcommands in `job_tool.py`'s existing `search` subparser group. `linkedin` fetches and regex-parses a list of job cards into the existing `posting()` shape; `linkedin-detail` fetches and regex-parses a single posting's full description/criteria, keyed off the numeric ID embedded in any `linkedin.com/jobs/view/...` URL a search result already returned. A new HTML-fetch helper with retry/backoff sits alongside (not replacing) the existing JSON fetch helper used by the other three sources.

**Tech Stack:** Python 3 stdlib only (`urllib.request`, `re`, `time`, `random`) — no new dependencies. Tests use stdlib `unittest` (no pytest infra exists in this repo for Python skill scripts).

## Global Constraints

- No new runtime dependencies — stdlib only (`urllib`, `re`, `time`, `random`).
- Fetch failures must degrade to an `"error"` string with empty/null results — never an unhandled exception or stack trace, matching the existing `http_get_json` contract.
- Backoff on HTTP 429/5xx: up to 6 retries, starting at 500ms delay, doubling each retry capped at 8000ms, plus 0–500ms random jitter.
- A 404 from LinkedIn's endpoints means "not found," not an error — returns empty content with no error string.
- `search linkedin` results must reuse the existing `posting()` field shape exactly (`source, title, company, location, remote, url, tags, salary, posted_date, description`) — no new field added to `posting()` itself.
- LinkedIn access is personal-use-only per its Terms of Service — both the `job_tool.py` module docstring and SKILL.md must carry this warning; keep query volume low in any live test.
- No pytest baseline applies to this tool (no Python test infra exists anywhere in this repo). Tests use stdlib `unittest`, run directly with `python3 -m unittest` — no new test framework dependency.

---

### Task 1: HTML entity decoding + clean-text helper

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add functions after the existing `strip_html` function, currently at lines 261–266)
- Create: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: existing `strip_html(text)` function (unchanged, already in the file).
- Produces: `decode_html_entities(text: str | None) -> str | None` and `clean_text(html: str | None) -> str | None` — both used by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests**

Create `tools/job-search/scripts/test_job_tool.py`:

```python
import unittest

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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'decode_html_entities'`

- [ ] **Step 3: Add the implementation**

In `tools/job-search/scripts/job_tool.py`, immediately after the existing `strip_html` function (the one ending `return text` around line 266), add:

```python
def decode_html_entities(text):
    if not text:
        return text

    def numeric_entity(code_point):
        return chr(code_point) if 0 <= code_point <= 0x10FFFF else ""

    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    text = re.sub(r"&#(\d+);", lambda m: numeric_entity(int(m.group(1))), text)
    text = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: numeric_entity(int(m.group(1), 16)), text)
    text = text.replace("&nbsp;", " ")
    return text


def clean_text(html):
    if not html:
        return html
    return decode_html_entities(strip_html(html))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (5 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add HTML entity decoding for LinkedIn text parsing"
```

---

### Task 2: LinkedIn parameter-mapping helpers

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add functions after Task 1's `clean_text`)
- Modify: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `jobage_to_tpr(days: int | None) -> str | None`, `linkedin_work_type_flag(mode: str | None) -> str | None`, `normalize_linkedin_job_id(value: str | None) -> str | None` — all used by Tasks 6 and 7.

- [ ] **Step 1: Write the failing tests**

Append to `tools/job-search/scripts/test_job_tool.py` (above the `if __name__ == "__main__":` line):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'jobage_to_tpr'`

- [ ] **Step 3: Add the implementation**

Immediately after `clean_text` in `job_tool.py`, add:

```python
def jobage_to_tpr(days):
    if not days or days <= 0 or days >= 9999:
        return None
    return f"r{days * 86400}"


def linkedin_work_type_flag(mode):
    return {"remote": "2", "hybrid": "3", "onsite": "1"}.get((mode or "").lower())


def normalize_linkedin_job_id(value):
    if not value:
        return None
    urn_match = re.search(r"urn:li:jobPosting:(\d+)", value)
    if urn_match:
        return urn_match.group(1)
    url_match = re.search(r"-(\d{6,})(?:\?|$)", value) or re.search(r"/(\d{6,})(?:\?|$)", value)
    if url_match:
        return url_match.group(1)
    if re.fullmatch(r"\d{6,}", value):
        return value
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (13 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add LinkedIn query-parameter mapping helpers"
```

---

### Task 3: Parse LinkedIn search-result cards

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add function + regex constants after Task 2's helpers)
- Modify: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `clean_text`, `decode_html_entities` (Task 1).
- Produces: `parse_linkedin_cards(html: str) -> list[dict]`, where each dict has keys `id, title, company, company_url, location, posted_date, url`. Used by Task 6.

- [ ] **Step 1: Write the failing tests**

Append to `tools/job-search/scripts/test_job_tool.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'parse_linkedin_cards'`

- [ ] **Step 3: Add the implementation**

Immediately after `normalize_linkedin_job_id` in `job_tool.py`, add:

```python
LINKEDIN_CARD_SPLIT_RE = re.compile(r'data-entity-urn="urn:li:jobPosting:')
LINKEDIN_ID_PREFIX_RE = re.compile(r"^(\d+)")
LINKEDIN_FULL_LINK_RE = re.compile(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', re.IGNORECASE)
LINKEDIN_TITLE_H3_RE = re.compile(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', re.IGNORECASE)
LINKEDIN_TITLE_SR_RE = re.compile(r'class="sr-only"[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
LINKEDIN_SUBTITLE_RE = re.compile(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', re.IGNORECASE)
LINKEDIN_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
LINKEDIN_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
LINKEDIN_LISTDATE_RE = re.compile(
    r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', re.IGNORECASE
)


def parse_linkedin_cards(html):
    results = []
    chunks = LINKEDIN_CARD_SPLIT_RE.split(html)[1:]

    for chunk in chunks:
        id_match = LINKEDIN_ID_PREFIX_RE.match(chunk)
        if not id_match:
            continue
        job_id = id_match.group(1)

        link_match = LINKEDIN_FULL_LINK_RE.search(chunk)
        url = decode_html_entities(link_match.group(1)).split("?")[0] if link_match else ""

        title = None
        h3_match = LINKEDIN_TITLE_H3_RE.search(chunk)
        if h3_match:
            title = clean_text(h3_match.group(1)) or None
        if not title:
            sr_match = LINKEDIN_TITLE_SR_RE.search(chunk)
            if sr_match:
                title = clean_text(sr_match.group(1)) or None
        if not title:
            continue

        company = None
        sub_match = LINKEDIN_SUBTITLE_RE.search(chunk)
        if sub_match:
            company_link = LINKEDIN_HREF_RE.search(sub_match.group(1))
            company_url = (
                decode_html_entities(company_link.group(1)).split("?")[0] if company_link else None
            )
            company = clean_text(sub_match.group(1)) or None
        else:
            company_url = None

        loc_match = LINKEDIN_LOCATION_RE.search(chunk)
        location = clean_text(loc_match.group(1)) if loc_match else None
        location = location or None

        date_match = LINKEDIN_LISTDATE_RE.search(chunk)
        posted_date = date_match.group(1) if date_match else None

        results.append({
            "id": job_id,
            "title": title,
            "company": company,
            "company_url": company_url,
            "location": location,
            "posted_date": posted_date,
            "url": url or f"https://www.linkedin.com/jobs/view/{job_id}",
        })

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (16 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add LinkedIn search-card HTML parser"
```

---

### Task 4: Parse a single LinkedIn job's detail page

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add function + regex constants after Task 3's parser)
- Modify: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `clean_text`, `decode_html_entities` (Task 1), `strip_html` (existing).
- Produces: `parse_linkedin_detail(html: str, job_id: str) -> dict` with keys `id, title, company, company_url, location, url, description, seniority, employment_type, job_function, industries, apply_url`. Used by Task 7.

- [ ] **Step 1: Write the failing tests**

Append to `tools/job-search/scripts/test_job_tool.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'parse_linkedin_detail'`

- [ ] **Step 3: Add the implementation**

Immediately after `parse_linkedin_cards` in `job_tool.py`, add:

```python
LINKEDIN_TOPCARD_TITLE_RE = re.compile(
    r'class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)</h[12]>', re.IGNORECASE
)
LINKEDIN_ORG_RE = re.compile(
    r'class="topcard__org-name-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', re.IGNORECASE
)
LINKEDIN_LOC_DETAIL_RE = re.compile(
    r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', re.IGNORECASE
)
LINKEDIN_DESC_RE = re.compile(
    r'class="(?:show-more-less-html__markup|description__text[^"]*)"[^>]*>([\s\S]*?)</div>',
    re.IGNORECASE,
)
LINKEDIN_BR_RE = re.compile(r"<\s*br\s*/?>", re.IGNORECASE)
LINKEDIN_BLOCK_CLOSE_RE = re.compile(r"</(p|li|ul|ol|div|h\d)>", re.IGNORECASE)
LINKEDIN_CRITERIA_RE = re.compile(
    r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?'
    r'class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>',
    re.IGNORECASE,
)
LINKEDIN_APPLY_RE = re.compile(r'class="topcard__link[^"]*"[^>]*href="([^"]+)"', re.IGNORECASE)


def _strip_tags_keep_newlines(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def parse_linkedin_detail(html, job_id):
    title_match = LINKEDIN_TOPCARD_TITLE_RE.search(html)
    title = clean_text(title_match.group(1)) if title_match else None

    org_match = LINKEDIN_ORG_RE.search(html)
    company = clean_text(org_match.group(2)) or None if org_match else None
    company_url = decode_html_entities(org_match.group(1)).split("?")[0] if org_match else None

    loc_match = LINKEDIN_LOC_DETAIL_RE.search(html)
    location = (clean_text(loc_match.group(1)) or None) if loc_match else None

    description = None
    desc_match = LINKEDIN_DESC_RE.search(html)
    if desc_match:
        with_breaks = LINKEDIN_BR_RE.sub("\n", desc_match.group(1))
        with_breaks = LINKEDIN_BLOCK_CLOSE_RE.sub("\n", with_breaks)
        text = decode_html_entities(_strip_tags_keep_newlines(with_breaks))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        description = text or None

    criteria = {}
    for match in LINKEDIN_CRITERIA_RE.finditer(html):
        key = clean_text(match.group(1)).lower()
        criteria[key] = clean_text(match.group(2))

    apply_match = LINKEDIN_APPLY_RE.search(html)
    apply_url = decode_html_entities(apply_match.group(1)).split("?")[0] if apply_match else None

    return {
        "id": job_id,
        "title": title or "(untitled)",
        "company": company,
        "company_url": company_url,
        "location": location,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "description": description,
        "seniority": criteria.get("seniority level"),
        "employment_type": criteria.get("employment type"),
        "job_function": criteria.get("job function"),
        "industries": criteria.get("industries"),
        "apply_url": apply_url,
    }
```

Note: `_strip_tags_keep_newlines` collapses horizontal whitespace only (not `\n`), so the paragraph
breaks inserted by the `<br>`/block-tag conversion above it survive — this is a deliberate
correction versus the reference implementation, which collapses all whitespace including the
newlines it just inserted, silently flattening every description to one line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (18 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add LinkedIn job-detail HTML parser"
```

---

### Task 5: HTML fetch with retry/backoff

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add import lines, constants, and function)
- Modify: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `http_get_html_backoff(url: str) -> tuple[str | None, str | None]` — `(html, None)` on success (including `("", None)` for a 404), `(None, error_message)` on failure. Used by Tasks 6 and 7.

- [ ] **Step 1: Write the failing tests**

Append to `tools/job-search/scripts/test_job_tool.py` (add `from unittest.mock import patch, MagicMock` and `import urllib.error` to the imports at the top of the file):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'http_get_html_backoff'`

- [ ] **Step 3: Add the implementation**

In `job_tool.py`, add `import random` and `import time` to the existing import block (near the top, alongside the existing `import re`, `import sys` lines). Then add these constants near the existing `ATS_ENDPOINTS` dict, and the function immediately after `parse_linkedin_detail`:

```python
LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
LINKEDIN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
LINKEDIN_MAX_RETRIES = 6
LINKEDIN_BACKOFF_BASE_MS = 500
LINKEDIN_BACKOFF_CAP_MS = 8000


def http_get_html_backoff(url):
    delay_ms = LINKEDIN_BACKOFF_BASE_MS
    for attempt in range(LINKEDIN_MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": LINKEDIN_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.read().decode("utf-8"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "", None
            if e.code == 429 or e.code >= 500:
                if attempt == LINKEDIN_MAX_RETRIES:
                    return None, f"HTTP {e.code} from {url} after {attempt + 1} attempts"
                jitter_ms = random.randint(0, 500)
                time.sleep((delay_ms + jitter_ms) / 1000)
                delay_ms = min(delay_ms * 2, LINKEDIN_BACKOFF_CAP_MS)
                continue
            return None, f"HTTP {e.code} from {url}"
        except urllib.error.URLError as e:
            return None, f"network error reaching {url}: {e.reason}"
        except Exception as e:
            return None, f"unexpected error fetching {url}: {e}"
    return None, f"request to {url} failed after max retries"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (22 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add HTML fetch helper with 429/5xx backoff for LinkedIn"
```

---

### Task 6: `search linkedin` command

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add `cmd_search_linkedin`, wire into `main()`)
- Modify: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `jobage_to_tpr`, `linkedin_work_type_flag` (Task 2), `parse_linkedin_cards` (Task 3), `http_get_html_backoff` (Task 5), existing `posting()` and `print_search_result()` helpers.
- Produces: `cmd_search_linkedin(args)`, wired to `job_tool.py search linkedin`.

- [ ] **Step 1: Write the failing tests**

Append to `tools/job-search/scripts/test_job_tool.py` (add `import argparse`, `import contextlib`, `import io` to the top imports):

```python
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
```

Also add `import json` to the top of the test file if not already present (it will be needed here).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'cmd_search_linkedin'`

- [ ] **Step 3: Add the implementation**

Immediately after `http_get_html_backoff` in `job_tool.py`, add:

```python
def cmd_search_linkedin(args):
    params = {"location": args.location}
    if args.query:
        params["keywords"] = args.query
    tpr = jobage_to_tpr(args.jobage)
    if tpr:
        params["f_TPR"] = tpr
    work_type = linkedin_work_type_flag(args.remote)
    if work_type:
        params["f_WT"] = work_type
    params["start"] = str((args.page - 1) * 10)

    url = LINKEDIN_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    html, err = http_get_html_backoff(url)
    if err:
        print_search_result("linkedin", [], err)
        return

    cards = parse_linkedin_cards(html)[: args.limit]
    results = [
        posting(
            "linkedin", card["title"], card["company"], card["location"], None,
            card["url"], [], None, card["posted_date"], None,
        )
        for card in cards
    ]
    print_search_result("linkedin", results, None)
```

Then in `main()`, immediately after the existing `p_ats` block (right before `args = parser.parse_args()`), add:

```python
    p_linkedin = search_sub.add_parser("linkedin")
    p_linkedin.add_argument("--query")
    p_linkedin.add_argument("--location", required=True)
    p_linkedin.add_argument("--jobage", type=int)
    p_linkedin.add_argument("--remote", choices=["remote", "hybrid", "onsite"])
    p_linkedin.add_argument("--page", type=int, default=1)
    p_linkedin.add_argument("--limit", type=int, default=25)
    p_linkedin.set_defaults(func=cmd_search_linkedin)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (25 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add search linkedin subcommand"
```

---

### Task 7: `search linkedin-detail` command + docstring update

**Files:**
- Modify: `tools/job-search/scripts/job_tool.py` (add `print_detail_result`, `cmd_search_linkedin_detail`, wire into `main()`, update module docstring)
- Modify: `tools/job-search/scripts/test_job_tool.py`

**Interfaces:**
- Consumes: `normalize_linkedin_job_id` (Task 2), `parse_linkedin_detail` (Task 4), `http_get_html_backoff` (Task 5).
- Produces: `print_detail_result(source, result, error)`, `cmd_search_linkedin_detail(args)`, wired to `job_tool.py search linkedin-detail`.

- [ ] **Step 1: Write the failing tests**

Append to `tools/job-search/scripts/test_job_tool.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `FAIL` / `AttributeError: module 'job_tool' has no attribute 'cmd_search_linkedin_detail'`

- [ ] **Step 3: Add the implementation**

Immediately after `cmd_search_linkedin` in `job_tool.py`, add:

```python
def print_detail_result(source, result, error):
    print(json.dumps({"source": source, "error": error, "result": result}, indent=2))


def cmd_search_linkedin_detail(args):
    job_id = normalize_linkedin_job_id(args.id)
    if not job_id:
        print_detail_result("linkedin", None, f"could not parse a job id from '{args.id}'")
        return

    html, err = http_get_html_backoff(f"{LINKEDIN_DETAIL_URL}/{job_id}")
    if err:
        print_detail_result("linkedin", None, err)
        return
    if not html:
        print_detail_result("linkedin", None, "job not found")
        return

    detail = parse_linkedin_detail(html, job_id)
    print_detail_result("linkedin", detail, None)
```

Then in `main()`, immediately after the `p_linkedin` block added in Task 6, add:

```python
    p_linkedin_detail = search_sub.add_parser("linkedin-detail")
    p_linkedin_detail.add_argument("--id", required=True)
    p_linkedin_detail.set_defaults(func=cmd_search_linkedin_detail)
```

Finally, update the module docstring at the top of `job_tool.py`. In the `Usage:` block, immediately
after the existing `job_tool.py search ats ...` line, add:

```
  job_tool.py search linkedin --query "backend" --location "Remote" [--jobage 7] [--remote remote|hybrid|onsite] [--limit 25]
  job_tool.py search linkedin-detail --id <job-id|job-url>
```

And in the closing paragraph of the docstring (after the sentence ending "...never a stack trace,
so a caller can fall back to another source without the whole run failing."), add a new paragraph:

```
The `linkedin` and `linkedin-detail` sources hit LinkedIn's public jobs-guest endpoints directly
(no auth, no API key). Automated access to these pages is against LinkedIn's Terms of Service —
personal use only, keep query volume low, never bulk or commercial use.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/job-search/scripts && python3 -m unittest test_job_tool -v`
Expected: `OK` (28 tests)

- [ ] **Step 5: Manual live smoke test (mandatory, low volume)**

```bash
cd tools/job-search/scripts
python3 job_tool.py search linkedin --query "backend engineer" --location "Remote" --limit 5
```
Verify: `results` is non-empty, each entry has a non-null `title`, `company`, and `url`.

```bash
python3 job_tool.py search linkedin-detail --id "$(python3 -c "
import json, subprocess
out = json.loads(subprocess.run(
    ['python3', 'job_tool.py', 'search', 'linkedin', '--query', 'backend engineer', '--location', 'Remote', '--limit', '1'],
    capture_output=True, text=True,
).stdout)
print(out['results'][0]['url'])
")"
```
Verify: `result.description` is present and reads as clean text (no leftover HTML tags or `&amp;`-style entities).

- [ ] **Step 6: Commit**

```bash
git add tools/job-search/scripts/job_tool.py tools/job-search/scripts/test_job_tool.py
git commit -m "Add search linkedin-detail subcommand and personal-use notice"
```

---

### Task 8: SKILL.md integration

**Files:**
- Modify: `tools/job-search/SKILL.md`

**Interfaces:**
- Consumes: `search linkedin` / `search linkedin-detail` CLI contract from Tasks 6–7.
- Produces: updated skill documentation — no code.

- [ ] **Step 1: Add the Stage 2a call**

In `tools/job-search/SKILL.md`, in the "2a — Structured search via `job_tool.py`" section, immediately
after the existing `search ats` code block and its explanatory paragraph, add:

```markdown
Also run, once per (role × location) pair from the resolved criteria, in parallel with the calls
above:
```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py search linkedin --query "<role keyword>" --location "<location>" --limit 25
```
This hits LinkedIn's public job-search endpoint directly — more reliable than the `WebSearch`-based
LinkedIn queries in Stage 2b below, since it returns structured fields instead of snippets.
**Personal use only** per LinkedIn's Terms of Service — keep query volume low, never bulk or
commercial use.
```

- [ ] **Step 2: Update the Stage 2b enrichment guidance**

In the "2b — WebSearch / WebFetch" section, find the paragraph starting "**If `WebFetch` fails on a
posting:**" and the one before it starting "`WebSearch` results include a title, company, URL...".
Immediately before those, insert:

```markdown
**For a LinkedIn result** (any `linkedin.com/jobs/view/...` URL, whether it came from Stage 2a's
native search or a WebSearch hit below): use
`search linkedin-detail --id <the-url>` instead of `WebFetch` for enrichment. This replaces the
step that previously 403'd on LinkedIn specifically with the same native endpoint Stage 2a uses.
```

- [ ] **Step 3: Update the Stage 4 summary line**

In the Stage 4 output template, change:
```
Searched: Remotive, Arbeitnow, [ATS companies checked], LinkedIn (WebSearch) — [N] postings found,
```
to:
```
Searched: Remotive, Arbeitnow, [ATS companies checked], LinkedIn (native), LinkedIn (WebSearch) —
[N] postings found,
```

- [ ] **Step 4: Add a Key rules bullet**

In the "## Key rules" section at the bottom, add:

```markdown
- **LinkedIn access is personal-use-only** per its Terms of Service — keep query volume low on
  both `search linkedin` and `search linkedin-detail`, never bulk or commercial use.
```

- [ ] **Step 5: Commit**

```bash
git add tools/job-search/SKILL.md
git commit -m "Document native LinkedIn search source in job-search SKILL.md"
```

---

## Self-Review Notes

- **Spec coverage:** `search linkedin` (Task 6), `search linkedin-detail` (Task 7), backoff/retry
  contract (Task 5), `posting()` shape reuse (Task 6), personal-use notice in both docstring
  (Task 7) and SKILL.md (Task 8), Stage 2a/2b/4/Key-rules updates (Task 8) — all spec sections have
  a corresponding task.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code.
- **Type consistency:** `parse_linkedin_cards` card dict keys (`id, title, company, company_url,
  location, posted_date, url`) match what Task 6's `cmd_search_linkedin` reads; `parse_linkedin_detail`'s
  return keys match what Task 7's tests assert against.
