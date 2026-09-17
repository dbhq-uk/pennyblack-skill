"""Tests for how an address is assembled.

The address is the one field that decides whether a letter arrives at all, and
it is the one the sender cannot check after the envelope is sealed. These tests
exist because a comma-joined address printed as a single long line and wrapped
mid-address in the envelope window - found on a real PO Box address on
17 September 2026, after the letter had gone.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pennyblack  # noqa: E402
from providers.base import Address  # noqa: E402


class TestJoinLines(unittest.TestCase):
    def test_repeated_lines_become_newline_separated(self):
        self.assertEqual(
            pennyblack._join_lines(["PO Box 123", "Riverside House", "Leeds"]),
            "PO Box 123\nRiverside House\nLeeds",
        )

    def test_a_single_string_is_left_alone(self):
        self.assertEqual(pennyblack._join_lines("1 High Street"), "1 High Street")

    def test_one_repeated_line_is_not_wrapped_in_anything(self):
        self.assertEqual(pennyblack._join_lines(["1 High Street"]), "1 High Street")

    def test_never_joins_with_a_comma(self):
        """A comma join is what caused the wrap. It must not come back."""
        out = pennyblack._join_lines(["PO Box 123", "Riverside House"])
        self.assertNotIn(",", out)
        self.assertIn("\n", out)

    def test_blank_lines_are_dropped_not_printed(self):
        out = pennyblack._join_lines(["PO Box 123", "", "  ", "Leeds"])
        self.assertEqual(out, "PO Box 123\nLeeds")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(
            pennyblack._join_lines(["  PO Box 123  ", "\tLeeds "]),
            "PO Box 123\nLeeds",
        )

    def test_none_is_empty_not_a_crash(self):
        self.assertEqual(pennyblack._join_lines(None), "")

    def test_empty_list_is_empty(self):
        self.assertEqual(pennyblack._join_lines([]), "")


class _Args:
    """Stands in for the parsed argparse namespace."""

    def __init__(self, **kw):
        self.to_file = None
        self.name = None
        self.line = None
        self.postcode = None
        self.country = "GB"
        for k, v in kw.items():
            setattr(self, k, v)


class TestParseRecipient(unittest.TestCase):
    def test_repeated_line_flags_reach_the_address(self):
        addr = pennyblack._parse_recipient(_Args(
            name="HMCTS",
            line=["PO Box 123", "Riverside House"],
            postcode="LS1 1AA",
        ))[0]
        self.assertEqual(addr.line, "PO Box 123\nRiverside House")

    def test_to_file_accepts_a_list_for_line(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"name": "HMCTS",
                       "line": ["PO Box 123", "Riverside House"],
                       "postcode": "LS1 1AA"}, fh)
            path = fh.name
        addr = pennyblack._parse_recipient(_Args(to_file=path))[0]
        self.assertEqual(addr.line, "PO Box 123\nRiverside House")

    def test_to_file_still_accepts_a_plain_string(self):
        """The old shape must keep working - people have these files."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"name": "Acme Ltd", "line": "1 High Street",
                       "postcode": "LS1 1AA"}, fh)
            path = fh.name
        addr = pennyblack._parse_recipient(_Args(to_file=path))[0]
        self.assertEqual(addr.line, "1 High Street")

    def test_to_file_accepts_several_recipients(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump([
                {"name": "A", "line": ["1 High Street"], "postcode": "LS1 1AA"},
                {"name": "B", "line": "2 Low Street", "postcode": "LS2 2BB"},
            ], fh)
            path = fh.name
        got = pennyblack._parse_recipient(_Args(to_file=path))
        self.assertEqual([a.name for a in got], ["A", "B"])


class TestAddressValidation(unittest.TestCase):
    def test_a_multiline_address_still_validates(self):
        Address(name="HMCTS", line="PO Box 123\nRiverside House",
                postcode="LS1 1AA").validate()

    def test_an_all_blank_line_list_is_rejected(self):
        """Empty lines are dropped, so this must not slip through as valid."""
        with self.assertRaises(ValueError):
            Address(name="HMCTS", line=pennyblack._join_lines(["", "  "]),
                    postcode="LS1 1AA").validate()


if __name__ == "__main__":
    unittest.main()
