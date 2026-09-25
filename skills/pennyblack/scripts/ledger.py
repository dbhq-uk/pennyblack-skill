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

LEDGER_DIRNAME = ".pennyblack"
SENT_FILENAME = "sent.jsonl"

README = """# Posted letters

This folder is the record of physical letters sent from this repository with
[pennyblack](https://github.com/dbhq-uk/pennyblack-skill).

- `sent.jsonl` - one line per letter: recipient, postage service, cost,
  tracking number, and the date it was confirmed. Anything that happens to a
  letter later, such as a cancel, is added as a new line with an `event` field.
  No line is ever rewritten.
- `*.pdf` - the exact document that was posted, captured at the moment of
  sending. The provider's own preview link expires within the hour, so this is
  the only durable copy of what actually went in the envelope.

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


def document_name(entry: dict) -> str:
    """A filename that sorts by date and says who it went to."""
    stamp = entry.get("confirmed_at")
    when = (
        datetime.fromtimestamp(stamp, tz=timezone.utc)
        if isinstance(stamp, (int, float)) and stamp
        else datetime.now(tz=timezone.utc)
    ).strftime("%Y-%m-%d")
    who = _slug((entry.get("recipients") or ["letter"])[0])
    short = (entry.get("id") or "")[-8:] or "unknown"
    return f"{when}-{who}-{short}.pdf"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    return path


def record(entry: dict, *, log_dir: Path, document: bytes = None) -> dict:
    """Append one letter to the record, and keep the document beside it.

    Returns the paths written, so the caller can tell the user where the
    evidence went.
    """
    ensure_dir(log_dir)
    written = {"dir": log_dir, "document": None}

    if document:
        target = log_dir / document_name(entry)
        target.write_bytes(document)
        entry = dict(entry, document=target.name)
        written["document"] = target

    line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    sent = log_dir / SENT_FILENAME
    with sent.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    written["sent"] = sent
    return written


def record_event(event: dict, *, log_dir: Path) -> Path:
    """Append something that happened to a letter after it was sent.

    `event` carries an "event" name and the print job "id". The time is added
    here. The send line is never rewritten, so the file stays append-only and
    a merge still resolves by keeping both sides.
    """
    ensure_dir(log_dir)
    event = dict(event)
    event.setdefault("at", int(datetime.now(tz=timezone.utc).timestamp()))
    sent = log_dir / SENT_FILENAME
    with sent.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
    return sent


def letters(entries: list) -> list:
    """The send lines: one per letter posted. Event lines are left out."""
    return [e for e in entries if "event" not in e]


def events(entries: list, print_id: str) -> list:
    """The event lines for one print job, oldest first."""
    return [e for e in entries if "event" in e and e.get("id") == print_id]


def contains(log_dir: Path, print_id: str) -> bool:
    """True if the record already holds a send line for this print job.

    `send` checks this before recording a job it finds already confirmed, so
    that a retry writes the missing line once and never a second copy. Only
    send lines count: a cancel line for the job does not mean it was recorded.
    """
    return any(e.get("id") == print_id for e in letters(read(log_dir)))


def read(log_dir: Path) -> list:
    sent = Path(log_dir) / SENT_FILENAME
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
