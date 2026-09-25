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

    # The rate card prices are EXCLUDING VAT (references/postage.md), so they
    # go in `amount`. The VAT and the total are worked out at 20% to make a
    # whole fixture; only the ex VAT figure comes from the rate card.

    def test_real_rate_card_values(self):
        # Signed For 2nd Class is £3.51 ex VAT on the published rate card.
        cost = _money({"amount": 351_000_000, "tax": 70_200_000,
                       "after_tax": 421_200_000, "currency": "GBP"})
        self.assertEqual(cost.amount_pence, 351)
        self.assertEqual(cost.tax_pence, 70)
        self.assertEqual(cost.total_pence, 421)
        self.assertEqual(cost.currency, "GBP")

    def test_second_class(self):
        # 2nd Class is £0.84 ex VAT on the published rate card.
        cost = _money({"amount": 84_000_000, "tax": 16_800_000,
                       "after_tax": 100_800_000})
        self.assertEqual(cost.amount_pence, 84)
        self.assertEqual(cost.total_pence, 101)

    def test_divisor_is_ten_to_the_eight(self):
        self.assertEqual(COST_DIVISOR, 10 ** 8)

    def test_missing_cost_is_zero_not_a_crash(self):
        self.assertEqual(_money(None).total_pence, 0)
        self.assertEqual(_money({}).total_pence, 0)

    def test_rounds_rather_than_truncates(self):
        # £1.006 is 100.6 pence. Rounding gives 101 and truncating gives 100,
        # so this fails against a floor division or an int().
        self.assertEqual(_money({"after_tax": 100_600_000}).total_pence, 101)
        # And 100.4 pence is 100, so it does not always round up either.
        self.assertEqual(_money({"after_tax": 100_400_000}).total_pence, 100)

    def test_formats_as_sterling(self):
        # Signed For 1st Class is £4.34 ex VAT on the published rate card.
        cost = _money({"amount": 434_000_000, "tax": 86_800_000,
                       "after_tax": 520_800_000, "currency": "GBP"})
        self.assertEqual(str(cost), "£5.21 inc VAT (£4.34 + VAT)")


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
        # Signed For 1st Class: £4.34 ex VAT, £5.21 with it.
        "cost": {"amount": 434_000_000, "tax": 86_800_000,
                 "after_tax": 520_800_000, "currency": "GBP"},
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
        self.assertEqual(draft.cost.amount_pence, 434)
        self.assertEqual(draft.cost.total_pence, 521)

    def test_missing_pdf_file_is_caught_before_the_api_call(self):
        with self.assertRaises(IntelliprintError):
            self.prov.draft(source=Path("/nonexistent/letter.pdf"),
                            recipients=self.addr, service="second")

    def test_the_address_is_read_back_in_full(self):
        payload = _payload()
        payload["letters"][0]["address"] = {"name": "Acme Ltd", "line": "1 High St\nLeeds",
                                            "postcode": "LS1 1AA", "country": "GB"}
        draft = StubbedIntelliprint({"api_key": "k"}, payload).draft(
            source="x", recipients=self.addr, service="signed")
        self.assertEqual(len(draft.addresses), 1)
        self.assertEqual(draft.addresses[0].line, "1 High St\nLeeds")
        self.assertEqual(draft.addresses[0].postcode, "LS1 1AA")

    def test_sheets_per_letter_is_the_largest_letter(self):
        payload = _payload(sheets=20)
        payload["letters"] = [dict(payload["letters"][0], sheets=4),
                              dict(payload["letters"][0], sheets=16)]
        draft = StubbedIntelliprint({"api_key": "k"}, payload).draft(
            source="x", recipients=self.addr, service="signed")
        self.assertEqual(draft.sheets_per_letter, 16)

    def test_sheets_per_letter_falls_back_to_the_job_total(self):
        draft = StubbedIntelliprint({"api_key": "k"}, _payload(sheets=16)).draft(
            source="x", recipients=self.addr, service="signed")
        self.assertEqual(draft.sheets_per_letter, 16)

    def test_a_tracked_service_is_never_asked_for_c5(self):
        """Tracked 24 and 48 cannot use C5, per the envelope sizes page."""
        for service in ("tracked-24", "tracked-48"):
            with self.subTest(service=service):
                prov = StubbedIntelliprint({"api_key": "k"}, _payload())
                prov.draft(source="x", recipients=self.addr, service=service)
                self.assertEqual(prov.calls[0]["fields"]["postage"]["ideal_envelope"], "c4")

    def test_a_tracked_service_in_c5_is_refused_before_the_api_call(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload())
        with self.assertRaises(ValueError):
            prov.draft(source="x", recipients=self.addr, service="tracked-24", envelope="c5")
        self.assertEqual(prov.calls, [])

    def test_other_services_default_to_c5(self):
        self.prov.draft(source="x", recipients=self.addr, service="first")
        self.assertEqual(self.prov.calls[0]["fields"]["postage"]["ideal_envelope"], "c5")

    def test_c5_holds_fifteen_sheets(self):
        """From the provider's envelope sizes page."""
        self.assertEqual(Intelliprint.envelope_capacity["c5"], 15)
        self.assertEqual(Intelliprint.envelope_capacity["c4"], 50)


class TestAddressFromPdf(unittest.TestCase):
    """With no recipients, Intelliprint reads the address from page 1."""

    def setUp(self):
        self.prov = StubbedIntelliprint({"api_key": "k"}, _payload())

    def test_sends_no_recipients(self):
        self.prov.draft(source="x", recipients=[], service="signed", address_from_pdf=True)
        self.assertNotIn("recipients", self.prov.calls[0]["fields"])

    def test_no_recipients_without_the_option_is_still_refused(self):
        with self.assertRaises(IntelliprintError):
            self.prov.draft(source="x", recipients=[], service="signed")
        self.assertEqual(self.prov.calls, [])

    def test_recipients_and_the_option_together_are_refused(self):
        with self.assertRaises(IntelliprintError):
            self.prov.draft(source="x", service="signed", address_from_pdf=True,
                            recipients=[Address(name="A", line="B", postcode="C")])
        self.assertEqual(self.prov.calls, [])


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
        self.assertEqual(draft.cost.total_pence, 521)
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

    def test_a_return_keeps_its_reason_and_date(self):
        payload = _payload()
        payload["letters"][0].update({"status": "returned", "returned": {
            "acknowledged": False, "date": 1789900000, "reason": "Not at this address"}})
        m = StubbedIntelliprint({"api_key": "k"}, payload).status("prt_test123")[0]
        self.assertEqual(m.returned_reason, "Not at this address")
        self.assertEqual(m.returned_date, 1789900000)

    def test_each_letter_carries_the_jobs_test_flag(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload(testmode=True))
        self.assertIs(prov.status("prt_test123")[0].testmode, True)
        prov = StubbedIntelliprint({"api_key": "k"}, _payload(testmode=False))
        self.assertIs(prov.status("prt_test123")[0].testmode, False)

    def test_absent_tracking_number_is_none_not_empty_string(self):
        prov = StubbedIntelliprint({"api_key": "k"}, _payload())
        self.assertIsNone(prov.status("prt_test123")[0].tracking_number)


class TestCancel(unittest.TestCase):
    """DELETE on an unconfirmed job deletes it. On a confirmed job it cancels
    every letter still waiting to print, refunds those, and leaves the rest."""

    def test_an_unconfirmed_draft_is_deleted_whole(self):
        prov = StubbedIntelliprint({"api_key": "k"},
                                   {"id": "prt_test123", "object": "print", "deleted": True})
        result = prov.cancel("prt_test123")
        self.assertEqual(prov.calls[0]["method"], "DELETE")
        self.assertEqual(prov.calls[0]["path"], "/prints/prt_test123")
        self.assertTrue(result.deleted)
        self.assertEqual(result.letters, [])

    def test_a_confirmed_job_reports_each_letter(self):
        payload = _payload(confirmed=True, testmode=False)
        payload["letters"] = [
            {"id": "ltr_1", "status": "cancelled", "address": {"name": "Acme Ltd"},
             "postage_service": "uk_first_class"},
            {"id": "ltr_2", "status": "printing", "address": {"name": "Bloggs & Co"},
             "postage_service": "uk_first_class"},
        ]
        result = StubbedIntelliprint({"api_key": "k"}, payload).cancel("prt_test123")
        self.assertFalse(result.deleted)
        self.assertEqual([(m.recipient, m.status) for m in result.letters],
                         [("Acme Ltd", "cancelled"), ("Bloggs & Co", "printing")])
        self.assertEqual(result.letters[0].service, "first")
        self.assertIs(result.testmode, False)

    def test_nothing_left_to_cancel_says_so(self):
        """A 400 here is not an address problem, whatever the generic hint says."""
        prov = StubbedIntelliprint({"api_key": "k"})
        prov._request = lambda *a, **k: (_ for _ in ()).throw(
            IntelliprintError("generic", status=400, body='{"error": {"message": "x"}}'))
        with self.assertRaises(IntelliprintError) as ctx:
            prov.cancel("prt_test123")
        self.assertIn("waiting to print", str(ctx.exception))
        self.assertNotIn("postcode", str(ctx.exception))


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
