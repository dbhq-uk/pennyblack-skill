"""Tests for the Intelliprint provider.

No network. Every test either checks pure logic or drives _request through a
stub, because a test suite that posts real letters is an expensive test suite.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from providers.base import Address, SERVICES, EVIDENCE_SERVICES  # noqa: E402
from providers.intelliprint import (  # noqa: E402
    COST_DIVISOR,
    Intelliprint,
    IntelliprintError,
    _flatten,
    _money,
)


class TestMoney(unittest.TestCase):
    """The 10^8 divisor is the single most dangerous number in this codebase.

    Treating it as 100 would understate a letter by a factor of a million,
    which is exactly the kind of bug that is invisible in test mode and
    expensive in live mode.
    """

    def test_real_rate_card_values(self):
        # Intelliprint's published 2nd class Signed price is £3.51.
        cost = _money({"amount": 292_500_000, "tax": 58_500_000,
                       "after_tax": 351_000_000, "currency": "GBP"})
        self.assertEqual(cost.total_pence, 351)
        self.assertEqual(cost.amount_pence, 292)
        self.assertEqual(cost.currency, "GBP")

    def test_second_class(self):
        cost = _money({"amount": 70_000_000, "tax": 14_000_000,
                       "after_tax": 84_000_000})
        self.assertEqual(cost.total_pence, 84)

    def test_divisor_is_ten_to_the_eight(self):
        self.assertEqual(COST_DIVISOR, 10 ** 8)

    def test_missing_cost_is_zero_not_a_crash(self):
        self.assertEqual(_money(None).total_pence, 0)
        self.assertEqual(_money({}).total_pence, 0)

    def test_rounds_rather_than_truncates(self):
        # 1.005 pounds -> 100.5 pence -> 100 or 101, never 0
        cost = _money({"after_tax": 100_500_000})
        self.assertIn(cost.total_pence, (100, 101))

    def test_formats_as_sterling(self):
        cost = _money({"amount": 362_000_000, "tax": 72_000_000,
                       "after_tax": 434_000_000, "currency": "GBP"})
        self.assertIn("£4.34", str(cost))


class TestFlatten(unittest.TestCase):
    """The API wants PHP-style bracket keys, per the vendor's own cURL sample."""

    def test_recipient_shape_matches_vendor_sample(self):
        out = _flatten({"recipients": [{"address": {"name": "John Doe"}}]})
        self.assertEqual(out["recipients[0][address][name]"], "John Doe")

    def test_booleans_become_lowercase_strings(self):
        out = _flatten({"confirmed": False, "testmode": True})
        self.assertEqual(out["confirmed"], "false")
        self.assertEqual(out["testmode"], "true")

    def test_none_is_omitted_entirely(self):
        out = _flatten({"reference": None, "type": "letter"})
        self.assertNotIn("reference", out)
        self.assertEqual(out["type"], "letter")

    def test_nested_objects(self):
        out = _flatten({"postage": {"service": "uk_first_class", "ideal_envelope": "c5"}})
        self.assertEqual(out["postage[service]"], "uk_first_class")
        self.assertEqual(out["postage[ideal_envelope]"], "c5")

    def test_multiple_recipients_are_indexed(self):
        out = _flatten({"recipients": [
            {"address": {"name": "A"}}, {"address": {"name": "B"}},
        ]})
        self.assertEqual(out["recipients[0][address][name]"], "A")
        self.assertEqual(out["recipients[1][address][name]"], "B")


class StubbedIntelliprint(Intelliprint):
    """Intelliprint with the network removed."""

    def __init__(self, config, response=None):
        super().__init__(config)
        self.response = response or {}
        self.calls = []

    def _request(self, method, path, *, fields=None, file_path=None, query=None):
        self.calls.append({"method": method, "path": path, "fields": fields,
                           "file_path": file_path})
        return self.response


def _payload(**over):
    base = {
        "id": "prt_test123",
        "testmode": True,
        "confirmed": False,
        "pages": 1,
        "sheets": 1,
        "cost": {"amount": 362_000_000, "tax": 72_000_000,
                 "after_tax": 434_000_000, "currency": "GBP"},
        "postage": {"service": "uk_first_class_signed_for"},
        "letters": [{
            "id": "ltr_1",
            "status": "draft",
            "postage_service": "uk_first_class_signed_for",
            "address": {"name": "Acme Ltd"},
            "pdf": "https://example.invalid/preview.pdf",
        }],
    }
    base.update(over)
    return base


class TestDraft(unittest.TestCase):
    def setUp(self):
        self.prov = StubbedIntelliprint({"api_key": "k"}, _payload())
        self.addr = [Address(name="Acme Ltd", line="1 High St, Leeds", postcode="LS1 1AA")]

    def test_draft_is_never_confirmed(self):
        """A draft that arrives confirmed would post a letter nobody approved."""
        self.prov.draft(source="<p>hi</p>", recipients=self.addr, service="signed")
        self.assertIs(self.prov.calls[0]["fields"]["confirmed"], False)

    def test_draft_defaults_to_test_mode(self):
        self.prov.draft(source="<p>hi</p>", recipients=self.addr, service="signed")
        self.assertIs(self.prov.calls[0]["fields"]["testmode"], True)

    def test_service_is_mapped_to_the_vendor_name(self):
        self.prov.draft(source="<p>hi</p>", recipients=self.addr, service="signed")
        self.assertEqual(
            self.prov.calls[0]["fields"]["postage"]["service"],
            "uk_first_class_signed_for",
        )

    def test_unsupported_service_is_refused_not_downgraded(self):
        """Silently posting 2nd class when Special Delivery was asked for
        would be the worst possible failure mode."""
        with self.assertRaises(IntelliprintError) as ctx:
            self.prov.draft(source="x", recipients=self.addr, service="carrier-pigeon")
        self.assertIn("does not offer", str(ctx.exception))

    def test_no_recipients_is_refused(self):
        with self.assertRaises(IntelliprintError):
            self.prov.draft(source="x", recipients=[], service="second")

    def test_preview_url_is_surfaced(self):
        draft = self.prov.draft(source="x", recipients=self.addr, service="signed")
        self.assertEqual(draft.preview_url, "https://example.invalid/preview.pdf")

    def test_cost_is_converted(self):
        draft = self.prov.draft(source="x", recipients=self.addr, service="signed")
        self.assertEqual(draft.cost.total_pence, 434)

    def test_missing_pdf_file_is_caught_before_the_api_call(self):
        with self.assertRaises(IntelliprintError):
            self.prov.draft(source=Path("/nonexistent/letter.pdf"),
                            recipients=self.addr, service="second")


class TestConfirm(unittest.TestCase):
    def test_confirm_sets_confirmed_true(self):
        prov = StubbedIntelliprint({"api_key": "k"},
                                   _payload(confirmed=True, testmode=False))
        prov.confirm("prt_test123")
        self.assertEqual(prov.calls[0]["method"], "POST")
        self.assertEqual(prov.calls[0]["path"], "/prints/prt_test123")
        self.assertIs(prov.calls[0]["fields"]["confirmed"], True)

    def test_service_is_mapped_back_to_our_vocabulary(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload(confirmed=True))
        draft = prov.confirm("prt_test123")
        self.assertEqual(draft.service, "signed")


class TestRetrieveDraft(unittest.TestCase):
    """cmd_send checks a job before confirming it. That check must work through
    the neutral Provider interface, not by reaching into this provider."""

    def test_reports_unconfirmed(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload())
        self.assertFalse(prov.retrieve_draft("prt_test123").confirmed)

    def test_reports_confirmed(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload(confirmed=True))
        self.assertTrue(prov.retrieve_draft("prt_test123").confirmed)

    def test_carries_cost_and_recipients_for_the_prompt(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload())
        draft = prov.retrieve_draft("prt_test123")
        self.assertEqual(draft.cost.total_pence, 434)
        self.assertEqual(draft.recipients, ["Acme Ltd"])

    def test_is_on_the_neutral_interface(self):
        from providers.base import Provider
        self.assertTrue(hasattr(Provider, "retrieve_draft"))


class TestStatus(unittest.TestCase):
    def test_tracking_number_is_returned(self):
        payload = _payload()
        payload["letters"][0].update({"status": "sent",
                                      "tracking_number": "AB123456789GB"})
        prov = StubbedIntelliprint({"api_key": "k"}, payload)
        mailings = prov.status("prt_test123")
        self.assertEqual(len(mailings), 1)
        self.assertEqual(mailings[0].tracking_number, "AB123456789GB")
        self.assertEqual(mailings[0].status, "sent")

    def test_absent_tracking_number_is_none_not_empty_string(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload())
        self.assertIsNone(prov.status("prt_test123")[0].tracking_number)


class TestServiceVocabulary(unittest.TestCase):
    def test_every_pennyblack_service_maps_to_intelliprint(self):
        """If we advertise a service we cannot actually buy, the skill lies."""
        prov = Intelliprint({"api_key": "k"})
        for name in SERVICES:
            self.assertIn(name, prov.service_map, f"{name} has no Intelliprint mapping")

    def test_mapped_values_are_all_in_the_published_enum(self):
        published = {
            "uk_second_class", "uk_second_class_signed_for", "uk_first_class",
            "uk_first_class_signed_for", "uk_special_delivery_9am",
            "uk_special_delivery", "international", "tracked_24", "tracked_48",
        }
        for ours, theirs in Intelliprint.service_map.items():
            self.assertIn(theirs, published, f"{ours} maps to unknown value {theirs}")

    def test_evidence_services_are_exactly_the_tracked_ones(self):
        """These are the services where the API issues a tracking number.
        Taken verbatim from the OpenAPI description of tracking_number."""
        expected_api_values = {
            "uk_second_class_signed_for", "uk_first_class_signed_for",
            "uk_special_delivery_9am", "uk_special_delivery",
            "tracked_24", "tracked_48",
        }
        mapped = {Intelliprint.service_map[s] for s in EVIDENCE_SERVICES}
        self.assertEqual(mapped, expected_api_values)

    def test_plain_post_is_not_treated_as_evidence(self):
        self.assertNotIn("first", EVIDENCE_SERVICES)
        self.assertNotIn("second", EVIDENCE_SERVICES)


class TestAddress(unittest.TestCase):
    def test_missing_postcode_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            Address(name="A", line="1 High St", postcode="  ").validate()
        self.assertIn("postcode", str(ctx.exception))

    def test_defaults_to_gb(self):
        self.assertEqual(Address(name="A", line="B", postcode="C").country, "GB")


if __name__ == "__main__":
    unittest.main()
