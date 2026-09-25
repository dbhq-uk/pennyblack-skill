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

#: What each letter status means, and what to do about it. The names are the
#: ones Intelliprint documents, which are generic enough to be pennyblack's own;
#: a provider with different names maps onto these. `final` means the status
#: will not change again.
LETTER_STATUSES = {
    "draft": {
        "means": "not confirmed yet - nothing has been posted",
        "next": "send it, or cancel it",
        "final": False,
    },
    "waiting_to_print": {
        "means": "waiting to be printed",
        "next": "it can still be cancelled, with the user's say-so",
        "final": False,
    },
    "printing": {"means": "being printed", "next": "too late to cancel", "final": False},
    "enclosing": {"means": "being put in its envelope", "next": "", "final": False},
    "shipping": {
        "means": "printed and waiting for Royal Mail to collect it",
        "next": "",
        "final": False,
    },
    "sent": {"means": "handed to Royal Mail", "next": "", "final": False},
    "returned": {
        "means": "Royal Mail could not deliver it, and it came back to the print house",
        "next": "check the address with the user. If it was a notice where service "
                "matters, tell them now: a returned letter can mean it was not served",
        "final": True,
    },
    "cancelled": {
        "means": "cancelled before printing and refunded - nothing was posted",
        "next": "",
        "final": True,
    },
    "invalid_address": {
        "means": "Royal Mail refused to collect it because it judged the address "
                 "invalid - nothing was delivered",
        "next": "check the address with the user, then draft it again",
        "final": True,
    },
    "failed_wrong_address": {
        "means": "the print house could not post it because the address was wrong "
                 "- nothing was delivered",
        "next": "check the address with the user, then draft it again",
        "final": True,
    },
}

FINAL_STATUSES = {name for name, meta in LETTER_STATUSES.items() if meta["final"]}

#: Envelope sizes, smallest first. When a service cannot use the smallest, the
#: next one it can use is picked.
ENVELOPES = ("c5", "c4", "c4_plus", "a4_box")


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
    #: Each recipient's address as the provider holds it - what it will print
    #: in the envelope window. With --address-from-pdf, this is what the
    #: provider read from the file.
    addresses: list = field(default_factory=list)
    #: The most sheets any one letter in the job uses. `sheets` is the total
    #: across every letter, which says nothing about whether one fits its
    #: envelope.
    sheets_per_letter: int = 0


@dataclass
class Mailing:
    """One physical item, after confirmation."""

    id: str
    status: str
    service: str
    tracking_number: Optional[str] = None
    recipient: Optional[str] = None
    shipped_date: Optional[int] = None
    returned_reason: Optional[str] = None
    returned_date: Optional[int] = None
    raw: dict = field(default_factory=dict)
    #: True for a letter in a test job, which is never printed or posted.
    #: None when the provider did not say.
    testmode: Optional[bool] = None


@dataclass
class Cancellation:
    """What a cancel did.

    An unconfirmed draft is deleted whole (`deleted` is True, no letters). On a
    confirmed job, each letter still waiting to print is cancelled and the rest
    carry on, so `letters` holds each one's resulting status.
    """

    id: str
    deleted: bool
    letters: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    #: True for a test job. None when the provider did not say, as for a
    #: deleted draft.
    testmode: Optional[bool] = None


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
    #: How many sheets each envelope size holds. A letter with more sheets
    #: than its envelope holds is moved to a bigger one, and `draft` warns.
    envelope_capacity: dict = {}
    #: Envelopes a service cannot use, by pennyblack service name.
    envelope_excludes: dict = {}

    def __init__(self, config: dict):
        self.config = config

    def supports(self, service: str) -> bool:
        return service in self.service_map

    def envelope_for(self, service: str, envelope: Optional[str] = None) -> str:
        """The envelope to ask for: the one given, or else the smallest this
        service can use. A service that cannot use the one given is refused,
        never quietly moved to another envelope."""
        barred = self.envelope_excludes.get(service, ())
        allowed = [e for e in ENVELOPES if e not in barred]
        if envelope is None:
            return allowed[0]
        if envelope in barred:
            label = SERVICES.get(service, {}).get("label", service)
            raise ValueError(
                f"{label} cannot go in a {envelope.upper()} envelope. Use "
                f"--envelope {allowed[0]}, or leave --envelope out and the smallest "
                "envelope it can use is picked.")
        return envelope

    def draft(self, *, source, recipients, service, reference=None,
              testmode=True, **options) -> Draft:
        """Create an unconfirmed job. Nothing is printed or charged.

        `recipients` may be empty only when `options["address_from_pdf"]` is
        true, and then the provider reads the address from page 1 of the file.
        """
        raise NotImplementedError

    def retrieve_draft(self, draft_id: str) -> Draft:
        """Fetch an existing job so the caller can check it before confirming."""
        raise NotImplementedError

    def confirm(self, draft_id: str) -> Draft:
        raise NotImplementedError

    def cancel(self, draft_id: str) -> "Cancellation":
        """Delete an unconfirmed draft, or recall the letters of a confirmed
        job that have not been printed yet. Return what happened to each."""
        raise NotImplementedError

    def status(self, print_id: str) -> list:
        """Return the Mailing objects for a print job."""
        raise NotImplementedError

    def fetch_document(self, draft: Draft) -> bytes:
        """Return the PDF of the letter as it was printed, or None.

        Captured at the moment of sending and kept in the repository record.
        A tracking number proves something arrived; only the document proves
        what. Providers whose preview links are short-lived - which is most of
        them - make this the only chance to keep it.
        """
        return None
