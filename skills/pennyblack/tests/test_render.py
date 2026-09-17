"""Tests for the markdown-to-HTML letter renderer.

The bar here is not "renders markdown correctly". It is "never silently loses
a sentence from a letter that is about to be printed and posted to a person".
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import render  # noqa: E402


class TestStructure(unittest.TestCase):
    def test_paragraphs(self):
        out = render.markdown_to_html("One.\n\nTwo.")
        self.assertIn("<p>One.</p>", out)
        self.assertIn("<p>Two.</p>", out)

    def test_single_newline_is_a_line_break_not_a_new_paragraph(self):
        """A sign-off block relies on this - the same rule the DBHQ email
        convention uses <br> for."""
        out = render.markdown_to_html("Kind Regards,\nDaniel Grimes")
        self.assertIn("Kind Regards,<br>", out)
        self.assertEqual(out.count("<p>"), 1)

    def test_headings(self):
        out = render.markdown_to_html("# One\n## Two\n### Three")
        for tag in ("h1", "h2", "h3"):
            self.assertIn(f"<{tag}>", out)

    def test_bullet_list(self):
        out = render.markdown_to_html("- a\n- b")
        self.assertIn("<ul>", out)
        self.assertEqual(out.count("<li>"), 2)

    def test_numbered_list(self):
        out = render.markdown_to_html("1. a\n2. b")
        self.assertIn("<ol>", out)
        self.assertEqual(out.count("<li>"), 2)

    def test_lists_are_closed(self):
        out = render.markdown_to_html("- a\n\nAfter.")
        self.assertIn("</ul>", out)
        self.assertLess(out.index("</ul>"), out.index("After."))

    def test_horizontal_rule(self):
        self.assertIn("<hr>", render.markdown_to_html("a\n\n---\n\nb"))


class TestInline(unittest.TestCase):
    def test_bold_and_italic(self):
        out = render.markdown_to_html("**bold** and *italic*")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>italic</em>", out)

    def test_link_keeps_the_url_visible(self):
        """A printed letter cannot be clicked, so a bare anchor loses the
        destination entirely."""
        out = render.markdown_to_html("See [our terms](https://dbhq.uk/terms).")
        self.assertIn("https://dbhq.uk/terms", out)


class TestSafety(unittest.TestCase):
    def test_html_in_the_source_is_escaped(self):
        out = render.markdown_to_html("5 < 6 and 7 > 6")
        self.assertIn("&lt;", out)
        self.assertIn("&gt;", out)

    def test_ampersand_survives(self):
        out = render.markdown_to_html("Marks & Spencer")
        self.assertIn("Marks &amp; Spencer", out)

    def test_no_content_is_dropped(self):
        source = (
            "# Notice of termination\n\nDear Ms Smith,\n\n"
            "Contract **DB-2026-04** refers. The position:\n\n"
            "- Notice is 30 days\n- The final invoice follows\n\n"
            "Please confirm receipt.\n\nKind Regards,\nDaniel Grimes\n"
        )
        out = render.markdown_to_html(source)
        for fragment in ("Notice of termination", "Dear Ms Smith", "DB-2026-04",
                         "Notice is 30 days", "final invoice follows",
                         "Please confirm receipt", "Daniel Grimes"):
            self.assertIn(fragment, out, f"lost from the letter: {fragment}")

    def test_windows_line_endings(self):
        out = render.markdown_to_html("One.\r\n\r\nTwo.")
        self.assertIn("<p>One.</p>", out)
        self.assertIn("<p>Two.</p>", out)

    def test_output_is_a_whole_document(self):
        out = render.markdown_to_html("hi")
        self.assertTrue(out.startswith("<!DOCTYPE html>"))
        self.assertTrue(out.rstrip().endswith("</html>"))

    def test_a4_page_size_is_set(self):
        self.assertIn("size: A4", render.markdown_to_html("hi"))


class TestPassthrough(unittest.TestCase):
    def test_existing_html_is_left_alone(self):
        doc = "<!DOCTYPE html><html><body><p>Already HTML</p></body></html>"
        self.assertEqual(render.prepare(doc), doc)

    def test_markdown_is_converted(self):
        out = render.prepare("# Hello")
        self.assertIn("<h1>Hello</h1>", out)

    def test_detects_html_with_leading_whitespace(self):
        self.assertTrue(render.looks_like_html("\n  <!DOCTYPE html><html>"))

    def test_plain_text_is_not_mistaken_for_html(self):
        self.assertFalse(render.looks_like_html("Dear Sir, <see attached>"))


if __name__ == "__main__":
    unittest.main()
