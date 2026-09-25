"""Tests for what the skill tells people about postage and the law.

The CPR point about Signed For is right for court documents and wrong for a
notice under a lease, a contract or a statute that names a delivery method. An
agent that generalised it could talk a user out of the method their clause
requires and cost them a valid notice. These tests hold the limit in place.
"""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[1]

POSTAGE = SKILL / "references" / "postage.md"
SKILL_MD = SKILL / "SKILL.md"
README = REPO / "README.md"
AGENTS = REPO / "AGENTS.md"


def _paragraphs(path):
    return [p for p in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")) if p.strip()]


def _section(path, heading_pattern):
    """The text under the first heading that matches, up to the next heading."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^##+ .*{heading_pattern}.*$", text, re.M | re.I)
    if not match:
        return None
    rest = text[match.end():]
    nxt = re.search(r"^##+ ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


class TestNotLegalAdvice(unittest.TestCase):
    def test_postage_reference_says_it(self):
        self.assertIn("not legal advice", POSTAGE.read_text(encoding="utf-8").lower())

    def test_skill_md_says_it(self):
        self.assertIn("not legal advice", SKILL_MD.read_text(encoding="utf-8").lower())


class TestNamedMethod(unittest.TestCase):
    """If a clause or statute names the method, that clause decides."""

    def setUp(self):
        self.section = _section(POSTAGE, "names the method")
        self.assertIsNotNone(self.section, "postage.md has no section on a named method")
        self.lower = self.section.lower()

    def test_sends_the_user_to_the_clause(self):
        self.assertIn("read the clause", self.lower)

    def test_uses_the_named_method(self):
        self.assertIn("use the method it names", self.lower)

    def test_never_offers_a_substitute(self):
        self.assertIn("never tell the user that another method will do", self.lower)

    def test_special_delivery_for_registered_or_recorded(self):
        self.assertIn("registered post or recorded delivery", self.lower)
        self.assertIn("special delivery", self.lower)

    def test_names_the_statutes(self):
        self.assertIn("recorded delivery service act 1962", self.lower)
        self.assertIn("s.196(4)", self.lower)

    def test_skill_md_points_at_it(self):
        text = SKILL_MD.read_text(encoding="utf-8").lower()
        self.assertIn("use the method it names", text)


class TestCprAdviceIsLimited(unittest.TestCase):
    """Every paragraph that makes the Signed For point must say it is about
    court documents served under the CPR. Naming CPR 6.26 is not enough on its
    own: the old wording cited it and still told the agent to talk everyone
    out of Signed For."""

    TRIGGERS = ("proof of service", "misconception", "does not do that",
                "four times", "say so", "saying so")
    LIMITS = ("court document", "court proceedings")

    def test_every_claim_is_limited_to_court_documents(self):
        for path in (SKILL_MD, POSTAGE, README, AGENTS):
            for para in _paragraphs(path):
                lower = para.lower()
                if any(t in lower for t in self.TRIGGERS) and "signed for" in lower:
                    with self.subTest(file=path.name, paragraph=para[:70]):
                        self.assertIn("CPR", para)
                        self.assertTrue(any(lim in lower for lim in self.LIMITS),
                                        "the claim is not limited to court documents")

    def test_services_footer_is_limited_too(self):
        import contextlib
        import io
        import sys
        from unittest import mock
        sys.path.insert(0, str(SKILL / "scripts"))
        import config as cfg
        import pennyblack

        out = io.StringIO()
        with mock.patch.object(pennyblack.cfg, "load",
                               side_effect=cfg.ConfigError("not set up")), \
                contextlib.redirect_stdout(out):
            pennyblack.main(["services"])
        text = out.getvalue()
        self.assertIn("court documents", text)
        self.assertIn("names a delivery method", text)


class TestPostingEvidence(unittest.TestCase):
    def test_no_certificate_of_posting(self):
        text = POSTAGE.read_text(encoding="utf-8").lower()
        self.assertIn("no certificate of posting", text)

    def test_posting_date_is_shipped_date(self):
        text = POSTAGE.read_text(encoding="utf-8")
        self.assertIn("shipped_date", text)
        self.assertIn("confirmed_at", text)

    def test_no_unsourced_proof_of_posting(self):
        """It used to say "Keep the proof of posting" when pennyblack keeps none."""
        self.assertNotIn("keep the proof of posting",
                         POSTAGE.read_text(encoding="utf-8").lower())

    def test_returned_letter_is_covered(self):
        section = _section(POSTAGE, "returned")
        self.assertIsNotNone(section, "postage.md has no section on a returned letter")
        self.assertIn("s.196(4)", section)
        self.assertIn("pennyblack status", section)


if __name__ == "__main__":
    unittest.main()
