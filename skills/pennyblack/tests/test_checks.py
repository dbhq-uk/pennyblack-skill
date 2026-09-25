"""Tests for the cheap checks `draft` runs before a letter goes anywhere.

Each check has a bad input it must catch and a good input it must let through.
A check that never fires is as useless as one that always does.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import checks  # noqa: E402
from providers.base import Address  # noqa: E402

A4_PT = (595.28, 841.89)
LETTER_PT = (612, 792)  # US Letter


def pdf(*sizes, extra=b""):
    """A minimal PDF with one uncompressed page object per size."""
    body = b"%PDF-1.7\n"
    for n, (w, h) in enumerate(sizes or [A4_PT], start=1):
        body += b"%d 0 obj << /Type /Page /MediaBox [0 0 %s %s] >> endobj\n" % (
            n, str(w).encode(), str(h).encode())
    return body + extra + b"trailer << /Root 1 0 R >>\n%%EOF\n"


def addr(line="1 High Street\nLeeds", postcode="LS1 1AA", country="GB"):
    return Address(name="Acme Ltd", line=line, postcode=postcode, country=country)


class TestPdfMagic(unittest.TestCase):
    def test_non_pdf_bytes_are_refused(self):
        problems = checks.pdf_problems(b"<html><body>Not found</body></html>")
        self.assertEqual(len(problems), 1)
        self.assertIn("not a PDF", problems[0])

    def test_a_word_file_renamed_to_pdf_is_refused(self):
        self.assertTrue(checks.pdf_problems(b"PK\x03\x04word/document.xml"))

    def test_a_pdf_passes(self):
        self.assertEqual(checks.pdf_problems(pdf()), [])

    def test_a_short_preamble_before_the_header_passes(self):
        """Readers accept a header anywhere in the first 1024 bytes."""
        self.assertEqual(checks.pdf_problems(b"\n\n" + pdf()), [])


class TestEncrypted(unittest.TestCase):
    def test_an_encrypted_pdf_is_refused(self):
        data = pdf(extra=b"trailer << /Root 1 0 R /Encrypt 9 0 R >>\n")
        problems = checks.pdf_problems(data)
        self.assertEqual(len(problems), 1)
        self.assertIn("encrypted", problems[0])

    def test_an_inline_encrypt_dictionary_is_refused(self):
        self.assertTrue(checks.pdf_problems(pdf(extra=b"/Encrypt << /Filter /Standard >>")))

    def test_an_unencrypted_pdf_passes(self):
        self.assertEqual(checks.pdf_problems(pdf()), [])

    def test_the_word_alone_is_not_encryption(self):
        """A letter that mentions encryption is not an encrypted letter."""
        self.assertEqual(checks.pdf_problems(pdf(extra=b"(see /Encrypt in the spec)")), [])


class TestPageSize(unittest.TestCase):
    def test_a_non_a4_page_warns(self):
        warnings = checks.pdf_warnings(pdf(A4_PT, LETTER_PT))
        self.assertEqual(len(warnings), 1)
        self.assertIn("216 x 279 mm", warnings[0])
        self.assertIn("not A4", warnings[0])

    def test_landscape_a4_warns(self):
        self.assertTrue(checks.pdf_warnings(pdf((841.89, 595.28))))

    def test_a4_passes(self):
        self.assertEqual(checks.pdf_warnings(pdf(A4_PT, A4_PT)), [])

    def test_a4_with_bleed_passes(self):
        """Intelliprint's own template is 216 x 303 mm with bleed."""
        bleed = (216 / 25.4 * 72, 303 / 25.4 * 72)
        self.assertEqual(checks.pdf_warnings(pdf(bleed)), [])

    def test_an_unreadable_page_size_is_not_a_warning(self):
        """A MediaBox in a compressed stream cannot be read. Say nothing."""
        self.assertEqual(checks.pdf_warnings(b"%PDF-1.7\n1 0 obj <<>> endobj\n"), [])

    def test_sizes_are_read_in_millimetres(self):
        (w, h), = checks.page_sizes_mm(pdf(A4_PT))
        self.assertAlmostEqual(w, 210, places=0)
        self.assertAlmostEqual(h, 297, places=0)


class TestSheets(unittest.TestCase):
    CAPACITY = {"c5": 15, "c4": 50}

    def test_too_many_sheets_for_c5_warns(self):
        warnings = checks.sheet_warnings(16, "c5", self.CAPACITY)
        self.assertEqual(len(warnings), 1)
        self.assertIn("16 sheets", warnings[0])
        self.assertIn("C5", warnings[0])

    def test_fifteen_sheets_fit_c5(self):
        self.assertEqual(checks.sheet_warnings(15, "c5", self.CAPACITY), [])

    def test_sixteen_sheets_fit_c4(self):
        self.assertEqual(checks.sheet_warnings(16, "c4", self.CAPACITY), [])

    def test_unknown_capacity_says_nothing(self):
        self.assertEqual(checks.sheet_warnings(99, "c5", {}), [])


class TestCommaJoinedLine(unittest.TestCase):
    """The comma-joined address that wrapped in the envelope window."""

    def test_a_single_comma_joined_line_is_refused(self):
        problems = checks.address_problems(addr(line="PO Box 123, Riverside House, Leeds"))
        self.assertEqual(len(problems), 1)
        self.assertIn("--line", problems[0])

    def test_separate_lines_pass(self):
        self.assertEqual(checks.address_problems(addr(line="PO Box 123\nLeeds")), [])

    def test_a_comma_inside_one_of_several_lines_passes(self):
        """"Flat 3, 12 High Street" is one address line, written normally."""
        self.assertEqual(
            checks.address_problems(addr(line="Flat 3, 12 High Street\nLeeds")), [])


class TestPostcode(unittest.TestCase):
    def test_malformed_gb_postcodes_are_refused(self):
        for bad in ("LS1 1A", "LS11AAA", "123456", "L S1 1AA", "1LS 1AA", "LS1 AA1"):
            with self.subTest(postcode=bad):
                problems = checks.address_problems(addr(postcode=bad))
                self.assertEqual(len(problems), 1)
                self.assertIn("not a UK postcode", problems[0])

    def test_well_formed_gb_postcodes_pass(self):
        for good in ("LS1 1AA", "ls1 1aa", "LS11AA", "SW1A 1AA", "M1 1AE", "B33 8TH",
                     "CR2 6XH", "DN55 1PT", "EC1A 1BB", "W1A 0AX", " LS1  1AA ",
                     "GIR 0AA", "BFPO 123"):
            with self.subTest(postcode=good):
                self.assertEqual(checks.address_problems(addr(postcode=good)), [])

    def test_uk_as_a_country_code_is_checked_too(self):
        self.assertTrue(checks.address_problems(addr(postcode="12345", country="UK")))

    def test_a_non_uk_address_is_not_held_to_uk_format(self):
        self.assertEqual(checks.address_problems(addr(postcode="75008", country="FR")), [])


if __name__ == "__main__":
    unittest.main()
