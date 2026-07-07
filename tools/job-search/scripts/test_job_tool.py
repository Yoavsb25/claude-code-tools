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


if __name__ == "__main__":
    unittest.main()
