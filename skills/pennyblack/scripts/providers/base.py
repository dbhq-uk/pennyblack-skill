"""The provider interface, and the vocabulary every provider must speak.

pennyblack ships with one provider. The interface exists so that adding a
second one is a new file rather than a rewrite - but it is deliberately shaped
around what a letter-sending service must do, not around what any one vendor's
API happens to look like.

The service names below are pennyblack's own. Every provider maps them onto
whatever its API calls them. They are named after what Royal Mail sells,
because that is what the user is buying.
"""

from dataclasses import dataclass, field
from typing import Optional


#: pennyblack's postage vocabulary, in ascending order of what it proves.
#: Each entry: (name, what it is for, does it capture a signature, is it tracked)
SERVICES = {
    "second": {
        "label": "Royal Mail 2nd Class",
        "for": "routine post, nothing time-critical",
        "signature": False,
        "tracked": False,
    },
    "first": {
        "label": "Royal Mail 1st Class",
        "for": "anything with a date on it",
        "signature": False,
        "tracked": False,
    },
    "signed-second": {
        "label": "Royal Mail Signed For 2nd Class",
        "for": "a delivery record, where speed does not matter",
        "signature": True,
        "tracked": False,
    },
    "signed": {
        "label": "Royal Mail Signed For 1st Class",
        "for": "a delivery record and a deterrent",
        "signature": True,
        "tracked": False,
    },
    "tracked-48": {
        "label": "Royal Mail Tracked 48",
        "for": "tracking to the delivery point, two to three days",
        "signature": False,
        "tracked": True,
    },
    "tracked-24": {
        "label": "Royal Mail Tracked 24",
        "for": "tracking to the delivery point, next day aim",
        "signature": False,
        "tracked": True,
    },
    "special": {
        "label": "Royal Mail Special Delivery Guaranteed by 1pm",
        "for": "evidence that has to hold up - a signature you can actually view",
        "signature": True,
        "tracked": True,
    },
    "special-9am": {
        "label": "Royal Mail Special Delivery Guaranteed by 9am",
        "for": "as above, by 9am, at a price that reflects it",
        "signature": True,
        "tracked": True,
    },
}

#: Services that produce a tracking number worth surfacing and storing.
EVIDENCE_SERVICES = {
    name for name, meta in SERVICES.items() if meta["signature"] or meta["tracked"]
}


@dataclass
class Address:
    name: str
    line: str
    postcode: str
    country: str = "GB"

    def validate(self) -> None:
        missing = [f for f in ("name", "line", "postcode") if not getattr(self, f).strip()]
        if missing:
            raise ValueError(f"address is missing: {', '.join(missing)}")


@dataclass
class Cost:
    """Money, held in pence as an integer so nothing is lost to float drift."""

    amount_pence: int
    tax_pence: int
    total_pence: int
    currency: str = "GBP"

    def __str__(self) -> str:
        sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(self.currency, self.currency + " ")
        return f"{sym}{self.total_pence / 100:.2f} inc VAT ({sym}{self.amount_pence / 100:.2f} + VAT)"


@dataclass
class Draft:
    """A letter created but not yet committed. Costs nothing until confirmed."""

    id: str
    provider: str
    cost: Cost
    pages: int
    sheets: int
    service: str
    testmode: bool
    confirmed: bool = False
    recipients: list = field(default_factory=list)
    preview_url: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class Mailing:
    """One physical item, after confirmation."""

    id: str
    status: str
    service: str
    tracking_number: Optional[str] = None
    recipient: Optional[str] = None
    shipped_date: Optional[int] = None
    raw: dict = field(default_factory=dict)


class Provider:
    """What a letter-sending backend has to be able to do.

    The draft/confirm split is not optional. A provider that cannot create a
    letter without immediately sending it cannot offer the one safety property
    pennyblack is built around: you see the cost, and ideally the letter, before
    anything is posted or charged.
    """

    name = "base"
    #: Maps pennyblack service names to the provider's own. Providers that
    #: cannot offer a service simply leave it out, and pennyblack will say so
    #: plainly rather than silently downgrading it.
    service_map: dict = {}

    def __init__(self, config: dict):
        self.config = config

    def supports(self, service: str) -> bool:
        return service in self.service_map

    def draft(self, *, source, recipients, service, reference=None,
              testmode=True, **options) -> Draft:
        raise NotImplementedError

    def retrieve_draft(self, draft_id: str) -> Draft:
        """Fetch an existing job so the caller can check it before confirming."""
        raise NotImplementedError

    def confirm(self, draft_id: str) -> Draft:
        raise NotImplementedError

    def cancel(self, draft_id: str) -> None:
        raise NotImplementedError

    def status(self, print_id: str) -> list:
        """Return the Mailing objects for a print job."""
        raise NotImplementedError
