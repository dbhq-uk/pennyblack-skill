"""Cheap checks on a letter, run by `draft`.

Standard library only, so none of this parses a PDF properly. It reads the raw
bytes for the few things that can be found that way, and it checks the address
the way a person would before writing an envelope. The preview is still the
real check: these catch the common mistakes before the agent ever gets there.

Two kinds of result:

- a **problem** is certain to go wrong, so `draft` refuses and uploads nothing
- a **warning** may be fine, so `draft` goes ahead and prints it, and the agent
  checks the preview for it before asking the user to send
"""

import re

#: A4 in millimetres. A page within this much of it passes, so a template
#: with a few millimetres of bleed on each side still counts as A4.
A4_MM = (210.0, 297.0)
A4_TOLERANCE_MM = 7.0

_PT_TO_MM = 25.4 / 72

# The header may sit anywhere in the first 1024 bytes, which is what readers
# accept in practice.
_HEADER_WINDOW = 1024

# /Encrypt in a trailer or an xref stream dictionary is followed by a reference
# or an inline dictionary. Matching that, not the bare word, keeps a letter
# that merely mentions encryption from being refused.
_ENCRYPT = re.compile(rb"/Encrypt\s*(?:\d+\s+\d+\s+R|<<)")

_NUMBER = rb"(-?\d+(?:\.\d+)?|-?\.\d+)"
_MEDIABOX = re.compile(
    rb"/MediaBox\s*\[\s*" + rb"\s+".join([_NUMBER] * 4) + rb"\s*\]"
)

# Format only: outward code, optional space, inward code. It cannot say
# whether a postcode exists, only whether it could.
_GB_POSTCODE = re.compile(
    r"^(?:[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}|GIR ?0AA|BFPO ?[0-9]{1,4})$"
)
_GB = {"GB", "UK", ""}


def pdf_problems(data: bytes) -> list:
    """What makes this file certain to fail. An empty list means none."""
    if b"%PDF-" not in data[:_HEADER_WINDOW]:
        return ["it is not a PDF: the file does not start with %PDF-. "
                "Export or print the document to PDF, then draft that."]
    if _ENCRYPT.search(data):
        return ["the PDF is encrypted or password-protected, so the print house "
                "may not be able to read it. Print it to a new PDF without "
                "protection, then draft that."]
    return []


def page_sizes_mm(data: bytes) -> list:
    """(width, height) in millimetres for every MediaBox that can be read.

    A MediaBox inside a compressed object stream cannot be read without a PDF
    library, so it is simply not seen. That is what "where it can be read"
    means: this check can miss a bad page, but never invents one.
    """
    sizes = []
    for match in _MEDIABOX.finditer(data):
        x1, y1, x2, y2 = (float(v) for v in match.groups())
        sizes.append((abs(x2 - x1) * _PT_TO_MM, abs(y2 - y1) * _PT_TO_MM))
    return sizes


def is_a4(width_mm: float, height_mm: float) -> bool:
    """Portrait A4, allowing for a little bleed."""
    return (abs(width_mm - A4_MM[0]) <= A4_TOLERANCE_MM
            and abs(height_mm - A4_MM[1]) <= A4_TOLERANCE_MM)


def pdf_warnings(data: bytes) -> list:
    """What may be fine but needs a look at the preview."""
    odd = [(w, h) for w, h in page_sizes_mm(data) if not is_a4(w, h)]
    if not odd:
        return []
    w, h = odd[0]
    return [f"a page is {w:.0f} x {h:.0f} mm, not A4 (210 x 297 mm). Letters are "
            "printed on A4, so it may be scaled or cut off, and the address may "
            "not sit in the envelope window. Check every page of the preview."]


def gb_postcode_ok(postcode: str) -> bool:
    return bool(_GB_POSTCODE.match(" ".join((postcode or "").upper().split())))


def address_problems(address) -> list:
    """What is certainly wrong with an address, before it goes anywhere."""
    problems = []
    line = address.line or ""
    if "\n" not in line and "," in line:
        problems.append(
            f"the address is one line with commas in it: {line!r}. It prints as "
            "one long line and wraps in the envelope window. Give each address "
            "line its own --line (or a list for \"line\" in --to-file).")
    if (address.country or "").upper() in _GB and not gb_postcode_ok(address.postcode):
        problems.append(
            f"{address.postcode!r} is not a UK postcode. Check it with the user: "
            "it should look like LS1 1AA.")
    return problems


def sheet_warnings(sheets: int, envelope: str, capacity: dict) -> list:
    """A letter with more sheets than its envelope holds.

    The provider moves it to a bigger envelope and charges for that one, so
    the cost on the draft already includes it. The user should still know.
    """
    most = capacity.get(envelope)
    if not most or not sheets or sheets <= most:
        return []
    return [f"one letter is {sheets} sheets and a {envelope.upper()} envelope holds "
            f"{most}, so it goes in a bigger envelope. The cost shown includes "
            "that. Pass --envelope to choose the envelope yourself."]
