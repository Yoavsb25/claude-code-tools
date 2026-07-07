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


if __name__ == "__main__":
    unittest.main()
