"""Tests for the command line an agent actually runs.

No network and no account. Where a command needs a provider, a stub is
registered in providers.REGISTRY, so the real Intelliprint class is never built.
"""

import contextlib
import dataclasses
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ledger  # noqa: E402
import pennyblack  # noqa: E402
import providers  # noqa: E402
from providers.base import (  # noqa: E402
    Address, Cancellation, Cost, Draft, Mailing, Provider, SERVICES,
)

PDF = b"%PDF-1.7 stub letter"
A4_PDF = (b"%PDF-1.7\n1 0 obj << /Type /Page /MediaBox [0 0 595.28 841.89] >> endobj\n"
          b"trailer << /Root 1 0 R >>\n%%EOF\n")
ACME = Address(name="Acme Ltd", line="1 High Street\nLeeds", postcode="LS1 1AA")


def _job(**over):
    """One print job as the provider would report it."""
    base = dict(
        id="print_stub0001", provider="stub", cost=Cost(434, 87, 521),
        pages=1, sheets=1, service="signed", testmode=False, confirmed=False,
        recipients=["Acme Ltd"], preview_url="https://example.invalid/p.pdf",
        raw={"confirmed_at": 1789641495, "reference": "ref-1",
             "letters": [{"address": {"name": "Acme Ltd"}}]},
    )
    base.update(over)
    return Draft(**base)


class StubProvider(Provider):
    """A provider with no network at all. Offers every service.

    It holds one job. `confirm` flips it to confirmed, the way the real API
    does, and every call is logged in `calls` so a test can assert what did
    and did not happen.
    """

    name = "stub"
    service_map = {s: s for s in SERVICES}
    envelope_capacity = {"c5": 15, "c4": 50}

    def __init__(self, config=None, *, mailings=None, job=None, document=PDF,
                 cancellation=None):
        super().__init__(config or {})
        self.mailings = mailings or []
        self.job = job or _job()
        self.document = document
        self.cancellation = cancellation
        self.calls = []

    def draft(self, **kwargs):
        """Hand back the job as a draft. The kwargs are kept for the test."""
        self.calls.append(("draft", kwargs))
        recipients = kwargs["recipients"]
        over = dict(testmode=kwargs["testmode"], service=kwargs["service"],
                    confirmed=False)
        if recipients:
            over.update(recipients=[r.name for r in recipients],
                        addresses=list(recipients))
        self.job = dataclasses.replace(self.job, **over)
        return dataclasses.replace(self.job)

    def cancel(self, draft_id):
        self.calls.append(("cancel", draft_id))
        return self.cancellation

    def retrieve_draft(self, draft_id):
        self.calls.append(("retrieve_draft", draft_id))
        return dataclasses.replace(self.job)

    def confirm(self, draft_id):
        self.calls.append(("confirm", draft_id))
        self.job = dataclasses.replace(self.job, confirmed=True)
        return dataclasses.replace(self.job)

    def fetch_document(self, draft):
        self.calls.append(("fetch_document", draft.id))
        return self.document

    def status(self, print_id):
        self.calls.append(("status", print_id))
        if isinstance(self.mailings, dict):
            return self.mailings.get(print_id, [])
        return self.mailings

    def called(self, name):
        return [c for c in self.calls if c[0] == name]


@contextlib.contextmanager
def stub_provider(prov):
    """Make every command use `prov`.

    The registry is cleared first, so the real Intelliprint class cannot be
    built by accident, and the config is faked so no key file is read.
    """
    with mock.patch.dict(providers.REGISTRY, {"stub": lambda config: prov}, clear=True), \
            mock.patch.object(pennyblack.cfg, "load",
                              return_value={"provider": "stub", "api_key": "k"}):
        yield prov


def _subcommands():
    """Every subcommand the parser knows, with a dummy for each positional."""
    parser = pennyblack.build_parser()
    sub = next(a for a in parser._actions
               if a.__class__.__name__ == "_SubParsersAction")
    out = {}
    for name, subparser in sub.choices.items():
        positionals = [a for a in subparser._actions
                       if not a.option_strings and a.dest != "help"]
        out[name] = ["x.pdf" if a.dest == "source" else "print_x" for a in positionals]
    return out


def flat(text):
    """Output with its line wrapping taken out."""
    return " ".join(text.split())


def run(argv):
    """Run pennyblack.main and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = pennyblack.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class TestJsonFlag(unittest.TestCase):
    """SKILL.md and the README both say --json works before or after the
    subcommand. It used to work only after: the subparser's own default of
    False overwrote the top-level True."""

    def test_every_subcommand_is_covered(self):
        self.assertEqual(
            set(_subcommands()),
            {"setup", "services", "draft", "send", "status", "cancel", "log"},
        )

    def test_json_before_the_subcommand(self):
        parser = pennyblack.build_parser()
        for name, positionals in _subcommands().items():
            with self.subTest(command=name):
                args = parser.parse_args(["--json", name, *positionals])
                self.assertIs(args.json, True)

    def test_json_after_the_subcommand(self):
        parser = pennyblack.build_parser()
        for name, positionals in _subcommands().items():
            with self.subTest(command=name):
                args = parser.parse_args([name, *positionals, "--json"])
                self.assertIs(args.json, True)

    def test_no_json_means_false(self):
        parser = pennyblack.build_parser()
        for name, positionals in _subcommands().items():
            with self.subTest(command=name):
                args = parser.parse_args([name, *positionals])
                self.assertIs(args.json, False)

    def test_json_before_log_prints_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger.record({"id": "print_a", "service": "first", "cost_pence": 233,
                           "recipients": ["Acme Ltd"], "testmode": False},
                          log_dir=Path(tmp))
            code, out, _ = run(["--json", "log", "--log-dir", tmp])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["id"], "print_a")


DAY = 86400


def _mailing(**over):
    base = dict(id="ltr_1", status="sent", service="signed", recipient="Acme Ltd",
                shipped_date=1789641495)
    base.update(over)
    return Mailing(**base)


class _RecordCase(unittest.TestCase):
    """A temporary record with one sent letter in it."""

    JOB = "print_stub0001"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name) / ".pennyblack"
        ledger.record({"id": self.JOB, "service": "signed", "cost_pence": 521,
                       "recipients": ["Acme Ltd"], "testmode": False,
                       "confirmed_at": 1789641495}, log_dir=self.log_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def status(self, *mailings, job=None):
        prov = StubProvider(mailings=list(mailings))
        with stub_provider(prov):
            return run(["status", job or self.JOB, "--log-dir", str(self.log_dir)])


class TestStatus(_RecordCase):
    def test_shows_the_posting_date(self):
        """The date of posting is shipped_date, not the time send ran."""
        code, out, _ = self.status(_mailing(service="first"))
        self.assertEqual(code, 0)
        self.assertRegex(out, r"posted\s+17 Sep 2026")

    def test_no_posting_date_before_it_ships(self):
        _, out, _ = self.status(_mailing(status="waiting_to_print", shipped_date=None))
        self.assertNotIn("posted", out)

    def test_a_tracking_number_that_arrives_later_reaches_the_record(self):
        self.status(_mailing(tracking_number="AB123456789GB"))
        events = ledger.events(ledger.read(self.log_dir), self.JOB)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "status")
        letter = events[0]["letters"][0]
        self.assertEqual(letter["tracking_number"], "AB123456789GB")
        self.assertEqual(letter["status"], "sent")
        self.assertEqual(letter["shipped_date"], 1789641495)

    def test_the_send_line_is_never_rewritten(self):
        before = (self.log_dir / "sent.jsonl").read_text()
        self.status(_mailing(tracking_number="AB123456789GB"))
        self.assertTrue((self.log_dir / "sent.jsonl").read_text().startswith(before))

    def test_no_change_writes_no_new_line(self):
        self.status(_mailing(tracking_number="AB123456789GB"))
        self.status(_mailing(tracking_number="AB123456789GB"))
        self.assertEqual(len(ledger.events(ledger.read(self.log_dir), self.JOB)), 1)

    def test_a_job_that_is_not_in_the_record_is_not_written(self):
        self.status(_mailing(), job="print_elsewhere")
        self.assertEqual(ledger.events(ledger.read(self.log_dir), "print_elsewhere"), [])

    def test_log_shows_a_tracking_number_that_arrived_after_send(self):
        self.status(_mailing(tracking_number="AB123456789GB"))
        _, out, _ = run(["log", "--log-dir", str(self.log_dir)])
        self.assertIn("AB123456789GB", out)

    def test_returned_says_why(self):
        _, out, _ = self.status(_mailing(status="returned",
                                         returned_reason="Not at this address",
                                         returned_date=1789900000))
        self.assertIn("could not deliver", out)
        self.assertIn("Not at this address", out)
        self.assertNotIn("not issued yet", out)
        letter = ledger.events(ledger.read(self.log_dir), self.JOB)[0]["letters"][0]
        self.assertEqual(letter["returned"]["reason"], "Not at this address")

    def test_each_failure_has_its_own_message(self):
        seen = {}
        for status in ("returned", "failed_wrong_address", "invalid_address", "cancelled"):
            with self.subTest(status=status):
                _, out, _ = self.status(_mailing(status=status, shipped_date=None))
                self.assertNotIn("not issued yet", out)
                line = next(ln for ln in out.splitlines() if "status" in ln)
                self.assertIn(status, line)
                seen[status] = line
        self.assertEqual(len(set(seen.values())), 4, "two failures read the same")

    def test_signed_for_tracking_comes_after_delivery(self):
        _, out, _ = self.status(_mailing(status="sent"))
        self.assertIn("after delivery", out)


class TestRefresh(unittest.TestCase):
    """log --refresh polls every letter that can still change, and only those."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name) / ".pennyblack"
        now = int(time.time())
        for job, testmode in (("print_open", False), ("print_returned", False),
                              ("print_old", False), ("print_test", True)):
            ledger.record({"id": job, "service": "first", "cost_pence": 233,
                           "recipients": ["Acme Ltd"], "testmode": testmode,
                           "confirmed_at": now - 2 * DAY}, log_dir=self.log_dir)
        ledger.record_event({"event": "status", "id": "print_returned", "letters": [
            {"id": "ltr_r", "status": "returned"}]}, log_dir=self.log_dir)
        ledger.record_event({"event": "status", "id": "print_old", "letters": [
            {"id": "ltr_o", "status": "sent", "shipped_date": now - 60 * DAY}]},
            log_dir=self.log_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_updates_open_letters_only(self):
        prov = StubProvider(mailings={"print_open": [_mailing(
            id="ltr_a", status="sent", service="first")]})
        with stub_provider(prov):
            code, out, err = run(["log", "--refresh", "--log-dir", str(self.log_dir)])
        self.assertEqual(code, 0, err)
        self.assertEqual(prov.called("status"), [("status", "print_open")])
        events = ledger.events(ledger.read(self.log_dir), "print_open")
        self.assertEqual(events[-1]["letters"][0]["status"], "sent")

    def test_log_without_refresh_calls_nothing(self):
        prov = StubProvider()
        with stub_provider(prov):
            run(["log", "--log-dir", str(self.log_dir)])
        self.assertEqual(prov.calls, [])


class TestLogTotal(unittest.TestCase):
    """The "spent live" total used to be summed over the letters shown, so
    with more than --limit letters it understated what was spent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name) / ".pennyblack"

    def tearDown(self):
        self._tmp.cleanup()

    def letters(self, count, testmode=False, pence=100):
        for n in range(count):
            ledger.record({"id": f"print_{testmode}_{n}", "service": "second",
                           "cost_pence": pence, "recipients": ["Acme Ltd"],
                           "testmode": testmode}, log_dir=self.log_dir)

    def log(self, *extra):
        code, out, err = run(["log", "--log-dir", str(self.log_dir), *extra])
        self.assertEqual(code, 0, err)
        return out

    def test_the_total_counts_every_live_letter_not_just_those_shown(self):
        self.letters(25)
        out = self.log()
        self.assertIn("25 letter(s) recorded, £25.00 spent live", out)
        self.assertIn("showing the last 20 of 25", out)

    def test_the_total_does_not_depend_on_the_limit(self):
        self.letters(25)
        self.assertIn("£25.00 spent live", self.log("--limit", "3"))

    def test_test_letters_are_left_out_of_the_total(self):
        self.letters(3)
        self.letters(30, testmode=True, pence=500)
        self.assertIn("33 letter(s) recorded, £3.00 spent live", self.log())

    def test_no_note_when_everything_is_shown(self):
        self.letters(5)
        self.assertNotIn("showing the last", self.log())


class TestUkDates(unittest.TestCase):
    def test_dates_are_uk_time_not_utc(self):
        # 23:30 UTC on 17 Sep 2026 is 00:30 on 18 Sep in London (BST).
        self.assertEqual(pennyblack._date(1789687800), "18 Sep 2026")

    def test_document_names_use_uk_time(self):
        name = ledger.document_name({"id": "print_x", "confirmed_at": 1789687800,
                                     "recipients": ["Acme Ltd"]})
        self.assertTrue(name.startswith("2026-09-18"), name)


class TestSend(unittest.TestCase):
    """send is the step that spends money. After it, the letter has to end up
    in the record, whatever else goes wrong."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name) / ".pennyblack"

    def tearDown(self):
        self._tmp.cleanup()

    def send(self, prov, *extra):
        with stub_provider(prov):
            return run(["send", prov.job.id, "--yes", "--log-dir", str(self.log_dir), *extra])

    def test_confirms_then_records(self):
        prov = StubProvider()
        code, out, _ = self.send(prov)
        self.assertEqual(code, 0)
        self.assertEqual(len(prov.called("confirm")), 1)
        entries = ledger.read(self.log_dir)
        self.assertEqual([e["id"] for e in entries], ["print_stub0001"])

    def test_already_confirmed_but_unrecorded_is_recorded_now(self):
        """A confirm that timed out after the provider processed it leaves a
        posted letter with no record. A retry has to put that right."""
        prov = StubProvider(job=_job(confirmed=True))
        code, out, err = self.send(prov)
        self.assertEqual(code, 0, err)
        self.assertEqual(prov.called("confirm"), [], "it must never confirm twice")
        entries = ledger.read(self.log_dir)
        self.assertEqual([e["id"] for e in entries], ["print_stub0001"])
        self.assertIn("not posted again", out)

    def test_already_confirmed_and_recorded_writes_nothing(self):
        ledger.record({"id": "print_stub0001", "cost_pence": 521}, log_dir=self.log_dir)
        before = (self.log_dir / "sent.jsonl").read_text()
        prov = StubProvider(job=_job(confirmed=True))
        code, _, err = self.send(prov)
        self.assertNotEqual(code, 0)
        self.assertEqual(prov.called("confirm"), [])
        self.assertEqual((self.log_dir / "sent.jsonl").read_text(), before)
        self.assertIn("already in the record", err)

    def test_a_record_that_cannot_be_written_is_not_a_traceback(self):
        """The money is spent by then. The user needs the entry, not a stack."""
        prov = StubProvider()
        with mock.patch.object(pennyblack.ledger, "record",
                               side_effect=OSError(28, "No space left on device")):
            code, out, err = self.send(prov)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(prov.called("confirm")), 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("POSTED", err)
        self.assertIn("No space left on device", err)
        line = next(ln for ln in err.splitlines() if ln.startswith("{"))
        self.assertEqual(json.loads(line)["id"], "print_stub0001")

    def test_json_says_where_the_record_went_and_what_was_captured(self):
        code, out, _ = self.send(StubProvider(), "--json")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertIs(got["captured"], True)
        self.assertTrue(got["document"].endswith(".pdf"))
        self.assertTrue((self.log_dir / got["document"]).exists())
        self.assertEqual(got["ledger"], str(self.log_dir / "sent.jsonl"))
        self.assertIs(got["recovered"], False)

    def test_json_says_when_the_document_was_not_captured(self):
        code, out, _ = self.send(StubProvider(document=None), "--json")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertIs(got["captured"], False)
        self.assertIsNone(got["document"])
        self.assertEqual(got["ledger"], str(self.log_dir / "sent.jsonl"))


class _DraftCase(unittest.TestCase):
    """A temporary folder with a PDF in it, and previews saved inside it."""

    ADDRESS = ["--name", "Acme Ltd", "--line", "1 High Street", "--line", "Leeds",
               "--postcode", "LS1 1AA"]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pdf = self.tmp / "letter.pdf"
        self.pdf.write_bytes(A4_PDF)
        patcher = mock.patch.object(pennyblack.tempfile, "tempdir", str(self.tmp))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def draft(self, prov=None, *extra, address=None, source=None):
        prov = prov or StubProvider()
        with stub_provider(prov):
            code, out, err = run(["draft", str(source or self.pdf), "--service", "first",
                                  *(self.ADDRESS if address is None else address), *extra])
        return prov, code, out, err


class TestDraftPreview(_DraftCase):
    """The agent has to open page 1 of the preview. A link that expires in an
    hour is not enough, so draft saves the file and says where."""

    def test_saves_the_preview_and_prints_its_path(self):
        _, code, out, err = self.draft()
        self.assertEqual(code, 0, err)
        line = next(ln for ln in out.splitlines() if ln.strip().startswith("preview"))
        path = Path(line.split(None, 1)[1])
        self.assertTrue(path.is_absolute())
        self.assertEqual(path.read_bytes(), PDF)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_json_returns_the_preview_path(self):
        _, code, out, _ = self.draft(None, "--json")
        got = json.loads(out)
        self.assertEqual(Path(got["preview_file"]).read_bytes(), PDF)
        self.assertEqual(got["warnings"], [])
        self.assertEqual(got["addresses"], [["Acme Ltd", "1 High Street", "Leeds", "LS1 1AA"]])

    def test_a_preview_that_could_not_be_fetched_says_so(self):
        _, code, out, _ = self.draft(StubProvider(document=None))
        self.assertEqual(code, 0)
        self.assertIn("NOT saved", out)
        self.assertIn("https://example.invalid/p.pdf", out)

    def test_output_asks_for_the_address_window_to_be_checked(self):
        _, _, out, _ = self.draft()
        self.assertIn("page 1", out)
        self.assertIn("address", out)

    def test_output_shows_the_address_line_by_line(self):
        _, _, out, _ = self.draft()
        for line in ("Acme Ltd", "1 High Street", "Leeds", "LS1 1AA"):
            self.assertRegex(out, rf"(?m)^\s+(to\s+)?{line}$")


class TestDraftChecks(_DraftCase):
    """A refused draft uploads nothing. A warning still drafts, and says why."""

    def assertRefused(self, prov, code, err, text):
        self.assertNotEqual(code, 0)
        self.assertIn(text, err)
        self.assertIn("Nothing was uploaded", err)
        self.assertEqual(prov.called("draft"), [], "a refused draft reached the provider")

    def test_non_pdf_bytes_are_refused(self):
        self.pdf.write_bytes(b"<html>404</html>")
        prov, code, _, err = self.draft()
        self.assertRefused(prov, code, err, "not a PDF")

    def test_an_encrypted_pdf_is_refused(self):
        self.pdf.write_bytes(A4_PDF + b"trailer << /Encrypt 5 0 R >>\n")
        prov, code, _, err = self.draft()
        self.assertRefused(prov, code, err, "encrypted")

    def test_a_comma_joined_line_is_refused(self):
        prov, code, _, err = self.draft(None, address=[
            "--name", "HMCTS", "--line", "PO Box 123, Riverside House, Leeds",
            "--postcode", "LS1 1AA"])
        self.assertRefused(prov, code, err, "commas")

    def test_a_comma_joined_line_in_to_file_is_refused(self):
        to = self.tmp / "to.json"
        to.write_text(json.dumps({"name": "HMCTS", "line": "PO Box 123, Leeds",
                                  "postcode": "LS1 1AA"}))
        prov, code, _, err = self.draft(None, address=["--to-file", str(to)])
        self.assertRefused(prov, code, err, "commas")

    def test_a_malformed_postcode_is_refused(self):
        prov, code, _, err = self.draft(None, address=[
            "--name", "Acme Ltd", "--line", "1 High Street", "--line", "Leeds",
            "--postcode", "LS1 1A"])
        self.assertRefused(prov, code, err, "not a UK postcode")

    def test_a_good_letter_drafts_with_no_warnings(self):
        prov, code, out, err = self.draft()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(prov.called("draft")), 1)
        self.assertNotIn("WARNING", out)

    def test_a_non_a4_page_warns_but_drafts(self):
        self.pdf.write_bytes(A4_PDF.replace(b"595.28 841.89", b"612 792"))
        prov, code, out, _ = self.draft()
        self.assertEqual(code, 0)
        self.assertEqual(len(prov.called("draft")), 1)
        self.assertRegex(flat(out), r"WARNING .*not A4")

    def test_too_many_sheets_for_c5_warns(self):
        prov = StubProvider(job=_job(sheets=16, sheets_per_letter=16))
        _, code, out, _ = self.draft(prov)
        self.assertEqual(code, 0)
        self.assertRegex(flat(out), r"WARNING .*16 sheets")

    def test_fifteen_sheets_do_not_warn(self):
        prov = StubProvider(job=_job(sheets=15, sheets_per_letter=15))
        _, _, out, _ = self.draft(prov)
        self.assertNotIn("WARNING", out)


class TestAddressFromPdf(_DraftCase):
    """With --address-from-pdf no recipient is sent, and the provider reads
    the address from page 1. The draft has to show what it read."""

    def read(self, *addresses):
        return StubProvider(job=_job(recipients=[a.name for a in addresses],
                                     addresses=list(addresses)))

    def test_sends_no_recipients(self):
        prov, code, _, err = self.draft(self.read(ACME), "--address-from-pdf", address=[])
        self.assertEqual(code, 0, err)
        kwargs = prov.called("draft")[0][1]
        self.assertEqual(kwargs["recipients"], [])
        self.assertIs(kwargs["address_from_pdf"], True)

    def test_shows_the_address_it_read(self):
        _, _, out, _ = self.draft(self.read(ACME), "--address-from-pdf", address=[])
        self.assertIn("read from", out)
        for line in ("Acme Ltd", "1 High Street", "Leeds", "LS1 1AA"):
            self.assertIn(line, out)

    def test_no_address_read_says_do_not_send(self):
        prov = StubProvider(job=_job(recipients=[], addresses=[]))
        _, code, out, _ = self.draft(prov, "--address-from-pdf", address=[])
        self.assertEqual(code, 0)
        self.assertRegex(flat(out), r"WARNING .*Do not send")

    def test_a_malformed_postcode_read_from_the_pdf_warns(self):
        odd = Address(name="Acme Ltd", line="1 High Street", postcode="LS1 1A")
        _, _, out, _ = self.draft(self.read(odd), "--address-from-pdf", address=[])
        self.assertRegex(flat(out), r"WARNING .*not a UK postcode")

    def test_cannot_be_combined_with_a_recipient(self):
        prov, code, _, err = self.draft(None, "--address-from-pdf")
        self.assertNotEqual(code, 0)
        self.assertIn("one or the other", err)
        self.assertEqual(prov.called("draft"), [])


class TestCancel(unittest.TestCase):
    """A sent letter can be recalled until it is printed. cancel has to say
    which letters were stopped and which had already gone to print."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name) / ".pennyblack"

    def tearDown(self):
        self._tmp.cleanup()

    def cancel(self, result, *extra):
        with stub_provider(StubProvider(cancellation=result)):
            return run(["cancel", "print_stub0001", "--log-dir", str(self.log_dir), *extra])

    def mixed(self):
        return Cancellation(id="print_stub0001", deleted=False, letters=[
            Mailing(id="ltr_1", status="cancelled", service="first", recipient="Acme Ltd"),
            Mailing(id="ltr_2", status="printing", service="first", recipient="Bloggs & Co"),
        ])

    def test_reports_each_letter(self):
        code, out, _ = self.cancel(self.mixed())
        self.assertEqual(code, 0)
        acme = next(ln for ln in out.splitlines() if "Acme Ltd" in ln)
        bloggs = next(ln for ln in out.splitlines() if "Bloggs & Co" in ln)
        self.assertIn("cancelled", acme)
        self.assertIn("printing", bloggs)
        self.assertIn("too late", bloggs)
        self.assertNotIn("too late", acme)
        self.assertIn("1 of 2", out)

    def test_json_reports_each_letter(self):
        code, out, _ = self.cancel(self.mixed(), "--json")
        got = json.loads(out)
        self.assertEqual([(m["recipient"], m["status"]) for m in got["letters"]],
                         [("Acme Ltd", "cancelled"), ("Bloggs & Co", "printing")])
        self.assertEqual(got["cancelled"], 1)

    def test_a_confirmed_job_gets_a_cancel_line_in_the_record(self):
        ledger.record({"id": "print_stub0001", "cost_pence": 233,
                       "recipients": ["Acme Ltd"]}, log_dir=self.log_dir)
        self.cancel(self.mixed())
        entries = ledger.read(self.log_dir)
        self.assertEqual(len(entries), 2)
        event = entries[-1]
        self.assertEqual(event["event"], "cancel")
        self.assertEqual(event["id"], "print_stub0001")
        self.assertEqual([ltr["status"] for ltr in event["letters"]], ["cancelled", "printing"])

    def test_a_deleted_draft_writes_nothing(self):
        """Nothing was posted, so there is nothing to record."""
        code, out, _ = self.cancel(Cancellation(id="print_stub0001", deleted=True))
        self.assertEqual(code, 0)
        self.assertIn("deleted", out)
        self.assertEqual(ledger.read(self.log_dir), [])

    def test_log_shows_the_cancel_and_does_not_count_it_as_a_letter(self):
        ledger.record({"id": "print_stub0001", "cost_pence": 233, "testmode": False,
                       "recipients": ["Acme Ltd"]}, log_dir=self.log_dir)
        self.cancel(self.mixed())
        _, out, _ = run(["log", "--log-dir", str(self.log_dir)])
        self.assertIn("1 letter(s) recorded", out)
        self.assertIn("cancelled", out)


if __name__ == "__main__":
    unittest.main()
