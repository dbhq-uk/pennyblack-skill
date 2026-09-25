"""Provider registry.

pennyblack ships with Intelliprint. To add another, write a module here that
subclasses Provider, and register it below. Nothing else in the skill needs to
change - the commands, the postage vocabulary and the draft/confirm flow are
all provider-neutral.
"""

from .base import (  # noqa: F401  (re-exported for callers)
    Address,
    Cancellation,
    Cost,
    Draft,
    EVIDENCE_SERVICES,
    FINAL_STATUSES,
    LETTER_STATUSES,
    Mailing,
    Provider,
    SERVICES,
)
from .intelliprint import Intelliprint, IntelliprintError  # noqa: F401

REGISTRY = {
    Intelliprint.name: Intelliprint,
}


def get(config: dict) -> Provider:
    """Build the provider named in the config."""
    name = config.get("provider", "intelliprint")
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {', '.join(sorted(REGISTRY))}"
        ) from None
    return cls(config)
