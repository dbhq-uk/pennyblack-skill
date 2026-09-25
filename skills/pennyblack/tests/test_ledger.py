"""Tests for the repository record of posted letters."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ledger  # noqa: E402


def _entry(**over):
    e = {
        "id": "print_9m4pV9SAmgzCpvqZsJ3OExvwVGA",
        "service": "signed",
        "service_label": "Royal Mail Signed For 1st Class",
        "recipients": ["Acme Ltd"],
        "cost_pence": 521,
        "testmode": False,
        "confirmed_at": 1789641495,
        "tracking_numbers": ["AB123456789GB"],
    }
    e.update(over)
    return e


class TestResolveDir(unittest.TestCase):
    def test_explicit_wins(self):
        self.assertEqual(
            ledger.resolve_dir("/tmp/somewhere", fallback=Path("/fallback")),
            Path("/tmp/somewhere"),
        )

    def test_finds_git_root_from_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / ".git").mkdir(parents=True)
            deep = root / "a" / "b" / "c"
            deep.mkdir(parents=True)
            cwd = os.getcwd()
            try:
                os.chdir(deep)
                self.assertEqual(ledger.resolve_dir(), root / ".pennyblack")
            finally:
                os.chdir(cwd)

    def test_falls_back_when_not_in_a_repo(self):
        """A letter still has to be recorded somewhere."""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                # /tmp is not inside a git repo on any sane machine
                if ledger.find_repo_root() is None:
                    self.assertEqual(
                        ledger.resolve_dir(fallback=Path("/fallback")),
                        Path("/fallback"),
                    )
            finally:
                os.chdir(cwd)


class TestRecord(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / ".pennyblack"

    def tearDown(self):
        self._tmp.cleanup()

    def test_appends_one_line_per_letter(self):
        ledger.record(_entry(), log_dir=self.dir)
        ledger.record(_entry(id="print_second"), log_dir=self.dir)
        lines = (self.dir / "sent.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["id"], "print_second")

    def test_append_never_rewrites_earlier_lines(self):
        """Append-only is what makes a concurrent write safe to merge."""
        ledger.record(_entry(), log_dir=self.dir)
        first = (self.dir / "sent.jsonl").read_text()
        ledger.record(_entry(id="print_second"), log_dir=self.dir)
        self.assertTrue((self.dir / "sent.jsonl").read_text().startswith(first))

    def test_keeps_the_document(self):
        written = ledger.record(_entry(), log_dir=self.dir, document=b"%PDF-1.7 fake")
        self.assertIsNotNone(written["document"])
        self.assertTrue(written["document"].exists())
        self.assertEqual(written["document"].read_bytes(), b"%PDF-1.7 fake")

    def test_document_filename_sorts_by_date_and_names_the_recipient(self):
        written = ledger.record(_entry(), log_dir=self.dir, document=b"%PDF-1.7")
        name = written["document"].name
        self.assertTrue(name.startswith("2026-09-"), name)
        self.assertIn("acme-ltd", name)
        self.assertTrue(name.endswith(".pdf"))

    def test_entry_points_at_its_document(self):
        ledger.record(_entry(), log_dir=self.dir, document=b"%PDF-1.7")
        entry = ledger.read(self.dir)[0]
        self.assertIn("document", entry)
        self.assertTrue((self.dir / entry["document"]).exists())

    def test_a_missing_document_is_not_fatal(self):
        """The letter still went. Record it rather than lose the record too."""
        written = ledger.record(_entry(), log_dir=self.dir, document=None)
        self.assertIsNone(written["document"])
        self.assertEqual(len(ledger.read(self.dir)), 1)

    def test_writes_a_readme_warning_about_personal_data(self):
        ledger.record(_entry(), log_dir=self.dir)
        readme = (self.dir / "README.md").read_text()
        self.assertIn("names and postal addresses", readme)
        self.assertIn(".gitignore", readme)

    def test_readme_is_not_overwritten(self):
        ledger.ensure_dir(self.dir)
        (self.dir / "README.md").write_text("mine")
        ledger.record(_entry(), log_dir=self.dir)
        self.assertEqual((self.dir / "README.md").read_text(), "mine")

    def test_unicode_recipient_survives(self):
        ledger.record(_entry(recipients=["Åsa Björk"]), log_dir=self.dir)
        self.assertEqual(ledger.read(self.dir)[0]["recipients"], ["Åsa Björk"])


class TestRead(unittest.TestCase):
    def test_empty_when_nothing_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ledger.read(Path(tmp) / ".pennyblack"), [])

    def test_a_corrupt_line_does_not_lose_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / ".pennyblack"
            d.mkdir()
            (d / "sent.jsonl").write_text(
                json.dumps(_entry()) + "\nnot json at all\n"
                + json.dumps(_entry(id="print_third")) + "\n"
            )
            got = ledger.read(d)
            self.assertEqual(len(got), 2)
            self.assertEqual(got[1]["id"], "print_third")


class TestEvents(unittest.TestCase):
    """Things that happen to a letter after send are appended as event lines.
    The file stays append-only: a send line is never rewritten."""

    def test_an_event_is_appended_after_the_send_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / ".pennyblack"
            ledger.record(_entry(), log_dir=d)
            first = (d / "sent.jsonl").read_text()
            ledger.record_event({"event": "cancel", "id": _entry()["id"],
                                 "letters": [{"id": "ltr_1", "status": "cancelled"}]},
                                log_dir=d)
            text = (d / "sent.jsonl").read_text()
            self.assertTrue(text.startswith(first))
            last = json.loads(text.strip().splitlines()[-1])
            self.assertEqual(last["event"], "cancel")
            self.assertIn("at", last)

    def test_letters_and_events_are_told_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / ".pennyblack"
            ledger.record(_entry(), log_dir=d)
            ledger.record_event({"event": "cancel", "id": _entry()["id"], "letters": []},
                                log_dir=d)
            entries = ledger.read(d)
            self.assertEqual(len(ledger.letters(entries)), 1)
            self.assertEqual(len(ledger.events(entries, _entry()["id"])), 1)


class TestContains(unittest.TestCase):
    def test_finds_a_recorded_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / ".pennyblack"
            ledger.record(_entry(), log_dir=d)
            self.assertTrue(ledger.contains(d, "print_9m4pV9SAmgzCpvqZsJ3OExvwVGA"))
            self.assertFalse(ledger.contains(d, "print_other"))

    def test_a_later_event_is_not_a_send(self):
        """A cancel line for a job must not make send think it was recorded."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / ".pennyblack"
            ledger.record_event({"event": "cancel", "id": "print_x", "letters": []},
                                log_dir=d)
            self.assertFalse(ledger.contains(d, "print_x"))

    def test_an_empty_record_holds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(ledger.contains(Path(tmp) / ".pennyblack", "print_x"))


class TestDocumentName(unittest.TestCase):
    def test_awkward_recipient_names_are_slugged(self):
        name = ledger.document_name(_entry(recipients=["O'Brien & Sons (Leeds) Ltd."]))
        self.assertNotIn("'", name)
        self.assertNotIn("&", name)
        self.assertNotIn("/", name)
        self.assertTrue(name.endswith(".pdf"))

    def test_no_recipient_still_produces_a_filename(self):
        name = ledger.document_name({"id": "print_x", "confirmed_at": 1789641495})
        self.assertTrue(name.endswith(".pdf"))

    def test_names_do_not_collide_across_jobs(self):
        a = ledger.document_name(_entry(id="print_aaaaaaaa"))
        b = ledger.document_name(_entry(id="print_bbbbbbbb"))
        self.assertNotEqual(a, b)


class TestSeparation(unittest.TestCase):
    """Credentials are machine state; the record of what was posted is a
    business record. They must not end up in the same place."""

    def test_ledger_does_not_import_config(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts" / "ledger.py").read_text()
        self.assertNotIn("import config", source)

    def test_config_no_longer_holds_a_send_log(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts" / "config.py").read_text()
        self.assertNotIn("sent.jsonl", source)
        self.assertNotIn("record_sent", source)


if __name__ == "__main__":
    unittest.main()
