"""The record of what was actually posted.

This is deliberately not in `~/.dbhq/pennyblack/`. Credentials are machine
state and belong in a dotfile; a record of the letters you have sent is a
business record, and it belongs with the work, in version control, where it can
be read, diffed and grepped a year later.

Three things are kept per letter:

- a line in `sent.jsonl` - who, what service, what it cost, the tracking number
- **the PDF that was actually posted** - because a tracking number proves that
  something arrived, not what. The provider's preview link expires within the
  hour, and the source file may have been a temporary one, so if the document
  is not captured at the moment of sending it is gone.
- a README, because the folder holds names and postal addresses

A test send is kept apart, in `test.jsonl`, with its document named `test-...`.
Nothing was posted, so it must never sit among the letters that were, where a
reader or a total could count it as one.

`sent.jsonl` is append-only and one line per letter on purpose. Two sessions
posting letters produce two lines and a conflict resolves by keeping both. A
rendered markdown table would conflict on every concurrent write, and keeping a
rendered mirror in step with the data is the drift failure that is worth
avoiding entirely. `pennyblack log` renders it instead.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    UK = ZoneInfo("Europe/London")
except Exception:  # no time zone database on this machine
    # Only a date is ever shown, and UK time is never more than an hour from
    # UTC, so this is wrong at most for an hour after midnight in summer.
    UK = timezone.utc

LEDGER_DIRNAME = ".pennyblack"
SENT_FILENAME = "sent.jsonl"
TEST_FILENAME = "test.jsonl"


def filename(testmode=False) -> str:
    """Where a job's lines go: real letters in sent.jsonl, test sends apart."""
    return TEST_FILENAME if testmode else SENT_FILENAME

README = """# Posted letters

This folder is the record of physical letters sent from this repository with
[pennyblack](https://github.com/dbhq-uk/pennyblack-skill).

- `sent.jsonl` - one line per letter: recipient, postage service, cost,
  tracking number, and the date it was confirmed. Anything that happens to a
  letter later, such as a cancel, a tracking number or a return, is added as a
  new line with an `event` field. No line is ever rewritten.
- `*.pdf` - the exact document that was posted, captured at the moment of
  sending. The provider's own preview link expires within the hour, so this is
  the only durable copy of what actually went in the envelope.
- `test.jsonl` and `test-*.pdf` - test sends. Nothing was printed or posted.
  They are kept apart so that they are never mistaken for real letters.

## Before you commit this

**It contains names and postal addresses.** That is the point of a record of
posted letters, and it is fine in a private repository. In a public one it is a
personal-data disclosure, and under UK GDPR it is yours to answer for.

If this repository is public, add to `.gitignore`:

```
.pennyblack/
```

and keep the record somewhere private instead, with `--log-dir`.
"""


def find_repo_root(start: Path = None) -> Path:
    """Walk up for a .git directory. Returns None if there is not one."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_dir(explicit=None, fallback: Path = None) -> Path:
    """Decide where the record lives.

    1. --log-dir, if given, exactly as given.
    2. <git root>/.pennyblack, so it sits with the work and is found from any
       subdirectory of the repository.
    3. the fallback (the config directory), only when there is no repository -
       a letter still has to be recorded somewhere.
    """
    if explicit:
        return Path(explicit).expanduser()
    root = find_repo_root()
    if root:
        return root / LEDGER_DIRNAME
    return fallback


def _slug(text: str, limit: int = 40) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return out[:limit].strip("-") or "letter"


def uk_time(stamp) -> datetime:
    """A UNIX timestamp in UK time, or None. Dates are shown as the user
    lives them, not in UTC."""
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not stamp:
        return None
    return datetime.fromtimestamp(stamp, tz=UK)


def document_name(entry: dict) -> str:
    """A filename that sorts by date and says who it went to. A test send's
    name starts with `test-`, so it cannot pass for a letter that was posted."""
    when = (uk_time(entry.get("confirmed_at")) or datetime.now(tz=UK)).strftime("%Y-%m-%d")
    who = _slug((entry.get("recipients") or ["letter"])[0])
    short = (entry.get("id") or "")[-8:] or "unknown"
    prefix = "test-" if entry.get("testmode") else ""
    return f"{prefix}{when}-{who}-{short}.pdf"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    return path


def record(entry: dict, *, log_dir: Path, document: bytes = None) -> dict:
    """Append one letter to the record, and keep the document beside it.

    A test send goes to test.jsonl, never sent.jsonl. Returns the paths
    written, so the caller can tell the user where the evidence went.
    """
    ensure_dir(log_dir)
    written = {"dir": log_dir, "document": None}

    if document:
        target = log_dir / document_name(entry)
        target.write_bytes(document)
        entry = dict(entry, document=target.name)
        written["document"] = target

    line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    sent = log_dir / filename(entry.get("testmode"))
    with sent.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    written["sent"] = sent
    return written


def record_event(event: dict, *, log_dir: Path, testmode=False) -> Path:
    """Append something that happened to a letter after it was sent.

    `event` carries an "event" name and the print job "id". The time is added
    here. The send line is never rewritten, so the file stays append-only and
    a merge still resolves by keeping both sides. A test job's events go to
    test.jsonl with its send line.
    """
    ensure_dir(log_dir)
    event = dict(event)
    event.setdefault("at", int(datetime.now(tz=timezone.utc).timestamp()))
    sent = log_dir / filename(testmode)
    with sent.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
    return sent


def letters(entries: list) -> list:
    """The send lines: one per letter posted. Event lines are left out."""
    return [e for e in entries if "event" not in e]


def events(entries: list, print_id: str) -> list:
    """The event lines for one print job, oldest first."""
    return [e for e in entries if "event" in e and e.get("id") == print_id]


def latest_letters(entries: list, print_id: str) -> list:
    """Each letter's last known state for a job, from its newest event that
    carries letters. None if nothing has been heard since send."""
    for event in reversed(events(entries, print_id)):
        if event.get("letters"):
            return event["letters"]
    return None


def record_update(print_id: str, letters_now: list, *, log_dir: Path) -> Path:
    """Append a status line for a job, if anything about its letters changed.

    Returns the file written, or None when the record already had this state.
    Checking a letter ten times writes one line, not ten.
    """
    if latest_letters(read(log_dir), print_id) == letters_now:
        return None
    return record_event({"event": "status", "id": print_id, "letters": letters_now},
                        log_dir=log_dir)


def contains(log_dir: Path, print_id: str, testmode=False) -> bool:
    """True if the record already holds a send line for this print job.

    `send` checks this before recording a job it finds already confirmed, so
    that a retry writes the missing line once and never a second copy. Only
    send lines count: a cancel line for the job does not mean it was recorded.
    A test job is looked for in test.jsonl, a real one in sent.jsonl.
    """
    return any(e.get("id") == print_id
               for e in letters(read(log_dir, filename(testmode))))


def read(log_dir: Path, name: str = SENT_FILENAME) -> list:
    """The lines of one record file, oldest first. sent.jsonl by default."""
    sent = Path(log_dir) / name
    if not sent.exists():
        return []
    out = []
    for line in sent.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
