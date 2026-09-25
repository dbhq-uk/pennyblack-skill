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
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ledger  # noqa: E402
import pennyblack  # noqa: E402
import providers  # noqa: E402
from providers.base import (  # noqa: E402
    Cancellation, Cost, Draft, Mailing, Provider, SERVICES,
)

PDF = b"%PDF-1.7 stub letter"


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

    def __init__(self, config=None, *, mailings=None, job=None, document=PDF,
                 cancellation=None):
        super().__init__(config or {})
        self.mailings = mailings or []
        self.job = job or _job()
        self.document = document
        self.cancellation = cancellation
        self.calls = []

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


class TestStatus(unittest.TestCase):
    def test_shows_the_posting_date(self):
        """The date of posting is shipped_date, not the time send ran."""
        prov = StubProvider(mailings=[Mailing(
            id="ltr_1", status="sent", service="first", recipient="Acme Ltd",
            shipped_date=1789641495,
        )])
        with stub_provider(prov):
            code, out, _ = run(["status", "print_x"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"posted\s+17 Sep 2026")

    def test_no_posting_date_before_it_ships(self):
        prov = StubProvider(mailings=[Mailing(
            id="ltr_1", status="waiting_to_print", service="first", recipient="Acme Ltd",
        )])
        with stub_provider(prov):
            _, out, _ = run(["status", "print_x"])
        self.assertNotIn("posted", out)


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
