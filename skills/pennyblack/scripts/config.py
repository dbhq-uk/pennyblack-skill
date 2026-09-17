"""Settings and credentials for pennyblack.

Everything lives under ~/.dbhq/pennyblack/, per the DBHQ convention that a
skill keeps its state in ~/.dbhq/<skill>/ rather than a new top-level dotfile.
The directory is 700 and the config file is 600, because it holds an API key
that can spend money.
"""

import json
import os
import stat
from pathlib import Path

HOME = Path(os.environ.get("PENNYBLACK_HOME", Path.home() / ".dbhq" / "pennyblack"))
CONFIG_PATH = HOME / "config.json"
SENT_LOG = HOME / "sent.jsonl"

DEFAULT_PROVIDER = "intelliprint"


class ConfigError(Exception):
    """Raised when the skill is not set up, or is set up wrongly."""


def _ensure_home() -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    os.chmod(HOME, stat.S_IRWXU)  # 700
    return HOME


def load() -> dict:
    """Read the config. Raises ConfigError with a fixable message if absent."""
    if not CONFIG_PATH.exists():
        raise ConfigError(
            f"pennyblack is not set up yet - no config at {CONFIG_PATH}.\n"
            "Run: python3 scripts/pennyblack.py setup"
        )
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{CONFIG_PATH} is not valid JSON: {exc}") from exc

    if not cfg.get("api_key"):
        raise ConfigError(f"No api_key in {CONFIG_PATH}. Run setup again.")
    cfg.setdefault("provider", DEFAULT_PROVIDER)
    return cfg


def save(api_key: str, provider: str = DEFAULT_PROVIDER, **extra) -> Path:
    """Write the config at 600. Overwrites any existing key."""
    _ensure_home()
    cfg = {"provider": provider, "api_key": api_key}
    cfg.update(extra)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 600
    return CONFIG_PATH


def record_sent(entry: dict) -> None:
    """Append one line to the sent log.

    This is the local record of what was actually posted and what it cost.
    A tracking number that only exists in a vendor dashboard is not much use
    six months later when somebody asks whether a letter was sent.
    """
    _ensure_home()
    with SENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    os.chmod(SENT_LOG, stat.S_IRUSR | stat.S_IWUSR)


def read_sent() -> list:
    if not SENT_LOG.exists():
        return []
    out = []
    for line in SENT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
