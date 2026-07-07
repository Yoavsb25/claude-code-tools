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
