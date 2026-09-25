"""Tests for the command line an agent actually runs.

No network and no account. Where a command needs a provider, a stub is
registered in providers.REGISTRY, so the real Intelliprint class is never built.
"""

import contextlib
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
from providers.base import Mailing, Provider, SERVICES  # noqa: E402


class StubProvider(Provider):
    """A provider with no network at all. Offers every service."""

    name = "stub"
    service_map = {s: s for s in SERVICES}

    def __init__(self, config=None, *, mailings=None):
        super().__init__(config or {})
        self.mailings = mailings or []
        self.calls = []

    def status(self, print_id):
        self.calls.append(("status", print_id))
        return self.mailings


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


if __name__ == "__main__":
    unittest.main()
