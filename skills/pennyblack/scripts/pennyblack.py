#!/usr/bin/env python3
"""pennyblack - send a physical letter in the UK from the command line.

Standard library only. No dependencies, no virtualenv, Python 3.9+.

The shape of this tool is a two-step on purpose:

    draft    creates the letter, prices it, and gives you a preview URL.
             Nothing is printed and nothing is charged.
    send     commits a specific draft by id. This is the step that spends
             money and cannot be undone.

There is no single command that writes a letter and posts it in one go, and
that is not an oversight. Physical post cannot be recalled once it is printed.
"""

import argparse
import json
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402
import config as cfg  # noqa: E402
import ledger  # noqa: E402
import providers  # noqa: E402
from providers.base import (  # noqa: E402
    Address, EVIDENCE_SERVICES, FINAL_STATUSES, LETTER_STATUSES, SERVICES,
)


# --------------------------------------------------------------------------
# output helpers


def _out(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    return obj


def fail(message, code=1):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _date(stamp):
    """A UNIX timestamp as a UK date, or an empty string if there is none."""
    when = ledger.uk_time(stamp)
    return when.strftime("%d %b %Y") if when else ""


#: A sent letter is checked by `log --refresh` for this long after it was
#: posted. A Signed For number arrives after delivery, and a return can come
#: back after the letter shows as sent, so "sent" is not final straight away.
SETTLE_DAYS = 30


def _letter_state(m):
    """One letter as it goes into the record. Only what is known is kept."""
    state = {"id": m.id, "recipient": m.recipient, "status": m.status}
    if m.tracking_number:
        state["tracking_number"] = m.tracking_number
    if m.shipped_date:
        state["shipped_date"] = m.shipped_date
    if m.returned_reason or m.returned_date:
        state["returned"] = {"reason": m.returned_reason, "date": m.returned_date}
    return state


def _update_record(print_id, mailings, log_dir):
    """Write what the provider says now into the record, if the job is in it.

    A job that is not in this record was not posted from here, so nothing is
    written - status must never start a record of personal data somewhere new.
    """
    if not mailings or not ledger.contains(log_dir, print_id):
        return None
    return ledger.record_update(print_id, [_letter_state(m) for m in mailings],
                                log_dir=log_dir)


def _is_open(entry, entries, now):
    """Can this letter still change? Test letters never do."""
    if entry.get("testmode"):
        return False
    latest = ledger.latest_letters(entries, entry.get("id"))
    if latest is None:
        return True
    for letter in latest:
        status = letter.get("status")
        if status in FINAL_STATUSES:
            continue
        if status == "sent":
            posted = letter.get("shipped_date") or entry.get("confirmed_at") or now
            if now - posted > SETTLE_DAYS * 86400:
                continue
        return True
    return False


def _address_lines(address):
    """An address as it will read in the envelope window, one line each."""
    lines = [address.name] + (address.line or "").splitlines() + [address.postcode]
    return [ln.strip() for ln in lines if ln and ln.strip()]


def _save_preview(prov, draft):
    """Download the preview to a local file, and return its path or None.

    The link is signed and expires within the hour, and the agent has to be
    able to open page 1 and look at the address window. A private temporary
    directory, because the letter carries a name and an address.
    """
    data = prov.fetch_document(draft)
    if not data:
        return None
    try:
        folder = Path(tempfile.mkdtemp(prefix="pennyblack-preview-"))
        target = folder / f"{draft.id or 'draft'}.pdf"
        target.write_bytes(data)
        os.chmod(target, 0o600)
    except OSError:
        return None
    return target


def _describe_draft(draft, as_json=False, preview_file=None, warnings=(),
                    address_from_pdf=False):
    if as_json:
        return _out({
            "id": draft.id,
            "provider": draft.provider,
            "service": draft.service,
            "service_label": SERVICES.get(draft.service, {}).get("label", draft.service),
            "testmode": draft.testmode,
            "pages": draft.pages,
            "sheets": draft.sheets,
            "recipients": draft.recipients,
            "addresses": [_address_lines(a) for a in draft.addresses],
            "address_from_pdf": address_from_pdf,
            "cost_pence": draft.cost.total_pence,
            "cost": str(draft.cost),
            "preview_url": draft.preview_url,
            "preview_file": str(preview_file) if preview_file else None,
            "warnings": list(warnings),
        }, True)

    meta = SERVICES.get(draft.service, {})
    print()
    print(f"  draft      {draft.id}")
    if draft.addresses:
        first = "read from" if address_from_pdf else "to"
        for n, address in enumerate(draft.addresses):
            for i, line in enumerate(_address_lines(address)):
                label = (first if n == 0 else "and") if i == 0 else ""
                print(f"  {label:<10} {line}")
        if address_from_pdf:
            print("             (the address the provider read from page 1 of the PDF)")
    else:
        print(f"  to         {', '.join(draft.recipients) or '(none)'}")
    print(f"  service    {meta.get('label', draft.service)}")
    print(f"  pages      {draft.pages} on {draft.sheets} sheet(s)")
    print(f"  cost       {draft.cost}")
    if draft.testmode:
        print("  mode       TEST - nothing will be printed or charged")
    if preview_file:
        print(f"  preview    {preview_file}")
    elif draft.preview_url:
        print("  preview    NOT saved - open the link instead")
    if draft.preview_url:
        print(f"             {draft.preview_url}")
        print("             (signed link, expires in about an hour)")
    for warning in warnings:
        print(textwrap.fill(warning, width=78, initial_indent="  WARNING    ",
                            subsequent_indent=" " * 13))
    print()
    print("  Open page 1 of the preview and check the address in the envelope")
    print("  window before anyone says \"send it\".")
    print()
    if draft.testmode:
        print("  This is a test draft. Re-run with --live to create a real one.")
    else:
        print("  Nothing has been printed or charged yet. To post it:")
        print(f"    pennyblack send {draft.id}")
        print("  To throw it away:")
        print(f"    pennyblack cancel {draft.id}")
    print()
    return draft


# --------------------------------------------------------------------------
# commands


def cmd_setup(args):
    key = args.api_key
    if not key:
        try:
            key = input("Intelliprint API key (from https://account.intelliprint.net/api_keys): ").strip()
        except (EOFError, KeyboardInterrupt):
            fail("cancelled")
    if not key:
        fail("no API key given")
    path = cfg.save(key, provider=args.provider)
    print(f"Saved to {path} (mode 600).")
    print("Nothing is live yet - drafts default to test mode until you pass --live.")


def cmd_services(args):
    if args.json:
        return _out(SERVICES, True)
    conf = None
    try:
        conf = cfg.load()
    except cfg.ConfigError:
        pass
    prov = providers.get(conf) if conf else None

    print()
    print("  postage services, cheapest first")
    print()
    for name, meta in SERVICES.items():
        ok = "  " if prov is None or prov.supports(name) else "x "
        marks = []
        if meta["signature"]:
            marks.append("signature")
        if meta["tracked"]:
            marks.append("tracked")
        suffix = f"  [{', '.join(marks)}]" if marks else ""
        print(f"  {ok}{name:<14} {meta['label']}{suffix}")
        print(f"    {' ' * 14} {meta['for']}")
    print()
    if prov:
        missing = [n for n in SERVICES if not prov.supports(n)]
        if missing:
            print(f"  x = not offered by {prov.name}: {', '.join(missing)}")
            print()
    print("  For court documents served under CPR 6.26, Signed For proves no more than")
    print("  first class. If a lease, contract or statute names a delivery method, use")
    print("  that method. Postage facts, not legal advice: see references/postage.md.")
    print()


def _read_source(args):
    """Return the Path to the PDF that will be posted, and its bytes.

    pennyblack posts a document you already have. It does not typeset or
    convert anything, because a tool that silently reflows a letter is a tool
    that can change what a letter says on the page. The provider does add to
    page 1 - the address in the envelope window, and a code string down the
    left margin - which is why the preview is the thing to check.
    """
    path = Path(args.source)
    if not path.exists():
        fail(f"no such file: {path}")
    if path.suffix.lower() != ".pdf":
        fail(
            f"pennyblack posts PDFs, and {path.name} is not one.\n"
            "  Export or print your document to PDF first, then send that."
        )
    data = path.read_bytes()
    if not data:
        fail(f"{path} is empty")
    problems = checks.pdf_problems(data)
    if problems:
        fail(f"{path.name}: " + "\n  ".join(problems) + "\n  Nothing was uploaded.")
    return path, data


def _join_lines(value):
    """Address lines as one newline-separated string.

    The print house honours line breaks in the address field and prints each on
    its own line in the envelope window. A single comma-joined string prints as
    one long line and wraps mid-address, so accept a list (repeated --line, or a
    JSON list) and join it here.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v).strip() for v in value if str(v).strip())
    return str(value)


def _checked(address):
    """Validate one address, and refuse it if it is certainly wrong."""
    address.validate()
    problems = checks.address_problems(address)
    if problems:
        raise ValueError(f"{address.name or 'recipient'}: " + "\n  ".join(problems)
                         + "\n  Nothing was uploaded.")
    return address


def _parse_recipient(args):
    if getattr(args, "address_from_pdf", False):
        given = [f"--{f.replace('_', '-')}" for f in ("name", "line", "postcode", "to_file")
                 if getattr(args, f, None)]
        if given:
            fail(f"--address-from-pdf reads the address from the PDF, so {', '.join(given)} "
                 "cannot be used with it. Use one or the other.")
        return []

    if args.to_file:
        data = json.loads(Path(args.to_file).read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else [data]
        out = []
        for e in entries:
            addr = Address(
                name=e.get("name", ""),
                line=_join_lines(e.get("line", "")),
                postcode=e.get("postcode", ""),
                country=e.get("country", "GB"),
            )
            out.append(_checked(addr))
        return out

    missing = [f for f in ("name", "line", "postcode") if not getattr(args, f, None)]
    if missing:
        fail(
            "a recipient needs --name, --line and --postcode (or --to-file with JSON,\n"
            "  or --address-from-pdf when the address is already on page 1).\n"
            f"  missing: {', '.join(missing)}"
        )
    addr = Address(name=args.name, line=_join_lines(args.line), postcode=args.postcode,
                   country=args.country)
    return [_checked(addr)]


def cmd_draft(args):
    conf = cfg.load()
    prov = providers.get(conf)

    if args.service not in SERVICES:
        fail(f"unknown service '{args.service}'. Try: pennyblack services")
    if not prov.supports(args.service):
        fail(f"{prov.name} does not offer '{args.service}'. Try: pennyblack services")

    source, data = _read_source(args)
    recipients = _parse_recipient(args)
    warnings = checks.pdf_warnings(data)

    draft = prov.draft(
        source=source,
        recipients=recipients,
        service=args.service,
        reference=args.reference,
        testmode=not args.live,
        envelope=args.envelope,
        double_sided=not args.single_sided,
        black_and_white=args.black_and_white,
        confidential=args.confidential,
        background_first=args.background_first,
        background_other=args.background_other,
        address_from_pdf=args.address_from_pdf,
    )

    warnings += checks.sheet_warnings(draft.sheets_per_letter, args.envelope,
                                      prov.envelope_capacity)
    if args.address_from_pdf:
        if not any(_address_lines(a)[1:] for a in draft.addresses):
            warnings.append("the provider read no address from the PDF. Do not send "
                            f"this draft. Cancel it with: pennyblack cancel {draft.id}")
        for a in draft.addresses:
            if (a.country or "GB").upper() in ("GB", "UK") and a.postcode \
                    and not checks.gb_postcode_ok(a.postcode):
                warnings.append(f"the postcode read from the PDF, {a.postcode!r}, is "
                                "not a UK postcode. Check page 1 of the preview.")

    preview_file = _save_preview(prov, draft)
    return _describe_draft(draft, args.json, preview_file=preview_file,
                           warnings=warnings, address_from_pdf=args.address_from_pdf)


def _send_entry(draft):
    """The record line for a confirmed job."""
    letters = draft.raw.get("letters") or []
    entry = {
        "id": draft.id,
        "provider": draft.provider,
        "service": draft.service,
        "service_label": SERVICES.get(draft.service, {}).get("label", draft.service),
        "recipients": draft.recipients,
        "addresses": [l.get("address") for l in letters if l.get("address")],
        "cost_pence": draft.cost.total_pence,
        "pages": draft.pages,
        "testmode": draft.testmode,
        "confirmed_at": draft.raw.get("confirmed_at"),
        "reference": draft.raw.get("reference"),
    }
    tracking = [l.get("tracking_number") for l in letters if l.get("tracking_number")]
    if tracking:
        entry["tracking_numbers"] = tracking
    return entry


def cmd_send(args):
    conf = cfg.load()
    prov = providers.get(conf)
    log_dir = ledger.resolve_dir(args.log_dir, fallback=cfg.HOME)

    before = prov.retrieve_draft(args.id)
    recovered = False
    if before.confirmed:
        if ledger.contains(log_dir, args.id):
            fail(f"{args.id} was already confirmed, and it is already in the record "
                 f"at {log_dir / ledger.SENT_FILENAME}. Nothing was posted this time.\n"
                 f"  Check it with: pennyblack status {args.id}")
        # Confirmed, but never recorded. This is what a confirm that timed out
        # after the provider processed it leaves behind. Record it now, so that
        # retrying send is always safe. Never confirm it a second time.
        recovered = True
        draft = before
    else:
        if not args.yes and sys.stdin.isatty():
            where = ", ".join(before.recipients) or "the address on the draft"
            print(f"\n  About to post {args.id} to {where}")
            print(f"  for {before.cost} by "
                  f"{SERVICES.get(before.service, {}).get('label', before.service)}.")
            if not before.testmode:
                print("  Once it is printed, it cannot be recalled.")
            print()
            try:
                answer = input("  Type 'send' to confirm: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                fail("cancelled")
            if answer != "send":
                fail("cancelled - nothing was posted")

        draft = prov.confirm(args.id)

    entry = _send_entry(draft)
    tracking = entry.get("tracking_numbers", [])

    # Capture the document now or never - the preview link is signed and
    # expires within the hour. A tracking number says something arrived; only
    # this says what.
    document = prov.fetch_document(draft)

    # From here on the letter is posted and paid for. A record that cannot be
    # written must not end in a traceback: print the entry so it can be added
    # by hand, and say plainly what happened.
    try:
        written = ledger.record(entry, log_dir=log_dir, document=document)
    except OSError as exc:
        print(json.dumps(entry, sort_keys=True, ensure_ascii=False), file=sys.stderr)
        fail(f"POSTED, BUT NOT RECORDED. {draft.id} was confirmed, but the record "
             f"could not be written to {log_dir}: {exc}\n"
             f"  Fix that, then run: pennyblack send {draft.id}\n"
             "  It will find the letter already posted, record it, and not post it again.\n"
             f"  Or add the line above to {log_dir / ledger.SENT_FILENAME} by hand.\n"
             "  The copy of the document may not have been saved. Its preview link\n"
             "  expires within the hour:\n"
             f"  {draft.preview_url or '(none)'}")

    if args.json:
        return _out(dict(
            entry,
            document=written["document"].name if written["document"] else None,
            ledger=str(written["sent"]),
            captured=bool(written["document"]),
            recovered=recovered,
        ), True)

    print()
    if recovered:
        print(f"  posted     {draft.id}, by an earlier send")
        print("  note       It was missing from the record, so it has been recorded")
        print("             now. It was not posted again.")
    else:
        print(f"  posted     {draft.id}")
    print(f"  to         {', '.join(draft.recipients)}")
    print(f"  service    {SERVICES.get(draft.service, {}).get('label', draft.service)}")
    print(f"  cost       {draft.cost}")
    if draft.testmode:
        print("  mode       TEST - nothing was actually printed or charged")
    if tracking:
        for t in tracking:
            print(f"  tracking   {t}")
            print(f"             https://www.royalmail.com/track-your-item#/tracking-results/{t}")
    elif draft.service in EVIDENCE_SERVICES and not draft.testmode:
        print("  tracking   not issued yet - check again later with:")
        print(f"             pennyblack status {draft.id}")
    print(f"  recorded   {written['sent']}")
    if written["document"]:
        print(f"  document   {written['document'].name}")
    else:
        print("  document   NOT captured - the preview link did not return a PDF.")
        print("             The letter went; the copy of it did not.")
    print()
    return draft


def cmd_status(args):
    conf = cfg.load()
    prov = providers.get(conf)
    mailings = prov.status(args.id)

    log_dir = ledger.resolve_dir(args.log_dir, fallback=cfg.HOME)
    written = _update_record(args.id, mailings, log_dir)

    if args.json:
        return _out([dict(
            _letter_state(m), service=m.service,
            means=LETTER_STATUSES.get(m.status, {}).get("means", ""),
            final=m.status in FINAL_STATUSES,
        ) for m in mailings], True)

    if not mailings:
        print(f"  no mail items on {args.id}")
        return
    print()
    for m in mailings:
        meta = LETTER_STATUSES.get(m.status, {})
        print(f"  {m.recipient or m.id}")
        print(f"    status   {m.status}" + (f" - {meta['means']}" if meta else ""))
        if m.status == "returned" and (m.returned_reason or m.returned_date):
            print(f"    reason   {m.returned_reason or 'not given'}"
                  + (f", returned {_date(m.returned_date)}" if m.returned_date else ""))
        if meta.get("next"):
            print(f"    next     {meta['next']}")
        print(f"    service  {SERVICES.get(m.service, {}).get('label', m.service)}")
        if m.shipped_date:
            # The date Royal Mail took the letter. It is the date of posting,
            # not the time `send` ran - see references/postage.md.
            print(f"    posted   {_date(m.shipped_date)}")
        if m.tracking_number:
            print(f"    tracking {m.tracking_number}")
            print(f"             https://www.royalmail.com/track-your-item#/tracking-results/{m.tracking_number}")
        elif m.service in EVIDENCE_SERVICES and m.status not in FINAL_STATUSES:
            if SERVICES.get(m.service, {}).get("tracked"):
                print("    tracking not issued yet - check again later")
            else:
                print("    tracking issued after delivery for Signed For - check again later")
    if written:
        print()
        print(f"  recorded   {written}")
    print()


def cmd_cancel(args):
    """Throw away a draft, or recall a sent letter before it is printed.

    Only letters still waiting to print can be stopped. The provider refunds
    those, and anything already printing or later carries on, so the result is
    reported letter by letter rather than as one "cancelled".
    """
    conf = cfg.load()
    prov = providers.get(conf)
    result = prov.cancel(args.id)
    stopped = [m for m in result.letters if m.status == "cancelled"]

    written, problem = None, None
    if not result.deleted:
        # A confirmed job was posted and is in the record, so what happened to
        # it belongs there too. Appended, never rewritten.
        log_dir = ledger.resolve_dir(args.log_dir, fallback=cfg.HOME)
        try:
            written = ledger.record_event({
                "event": "cancel",
                "id": result.id or args.id,
                "letters": [{"id": m.id, "recipient": m.recipient, "status": m.status}
                            for m in result.letters],
            }, log_dir=log_dir)
        except OSError as exc:
            problem = f"the cancel went through, but the record could not be updated: {exc}"

    if args.json:
        _out({
            "id": result.id or args.id,
            "deleted": result.deleted,
            "cancelled": len(stopped),
            "letters": [{"id": m.id, "recipient": m.recipient, "status": m.status}
                        for m in result.letters],
            "ledger": str(written) if written else None,
        }, True)
    elif result.deleted:
        print()
        print(f"  deleted    {args.id}")
        print("             It was an unconfirmed draft. Nothing was printed or charged.")
        print()
    else:
        print()
        print(f"  {args.id}")
        for m in result.letters:
            who = m.recipient or m.id
            if m.status == "cancelled":
                print(f"    {who:<24} cancelled - it will not be printed, and it is refunded")
            else:
                print(f"    {who:<24} {m.status} - too late to cancel, it has gone to print")
        print()
        print(f"  {len(stopped)} of {len(result.letters)} letter(s) cancelled.")
        if written:
            print(f"  recorded   {written}")
        print()

    if problem:
        fail(problem)
    return result


def _refresh(log_dir, entries):
    """Poll every letter that can still change, and record what it says now."""
    conf = cfg.load()
    prov = providers.get(conf)
    now = int(time.time())
    checked = 0
    for entry in ledger.letters(entries):
        if not _is_open(entry, entries, now):
            continue
        _update_record(entry["id"], prov.status(entry["id"]), log_dir)
        checked += 1
    return checked


def cmd_log(args):
    log_dir = ledger.resolve_dir(args.log_dir, fallback=cfg.HOME)
    entries = ledger.read(log_dir)
    checked = None
    if args.refresh and entries:
        checked = _refresh(log_dir, entries)
        entries = ledger.read(log_dir)
    if args.json:
        return _out(entries, True)
    if not entries:
        print(f"  nothing posted from this repository yet ({log_dir}/sent.jsonl)")
        return

    sent = ledger.letters(entries)
    print()
    print(f"  {log_dir}")
    print()
    # The total covers every live letter in the record, not only the ones
    # shown. Summing the displayed slice understated it once there were more
    # letters than --limit, and nothing said the figure was partial.
    total = sum(e.get("cost_pence") or 0 for e in sent if not e.get("testmode"))
    shown = sent[-args.limit:]
    for e in shown:
        mode = "  [test]" if e.get("testmode") else ""
        pence = e.get("cost_pence", 0)
        date = _date(e.get("confirmed_at"))
        print(f"  {date}  {', '.join(e.get('recipients') or ['?'])}{mode}")
        print(f"    {e.get('service_label') or e.get('service','?')}  -  "
              f"£{pence / 100:.2f}")
        if e.get("reference"):
            print(f"    ref      {e['reference']}")
        latest = ledger.latest_letters(entries, e.get("id")) or []
        tracking = list(e.get("tracking_numbers", []))
        tracking += [ltr["tracking_number"] for ltr in latest
                     if ltr.get("tracking_number") and ltr["tracking_number"] not in tracking]
        for ltr in latest:
            line = f"    status   {ltr.get('status', '?')}"
            if ltr.get("shipped_date"):
                line += f", posted {_date(ltr['shipped_date'])}"
            if (ltr.get("returned") or {}).get("reason"):
                line += f", returned: {ltr['returned']['reason']}"
            if len(latest) > 1:
                line += f"  ({ltr.get('recipient') or ltr.get('id')})"
            print(line)
        for t in tracking:
            print(f"    tracking {t}")
        if e.get("document"):
            print(f"    document {e['document']}")
        for ev in ledger.events(entries, e.get("id")):
            if ev.get("event") == "cancel":
                n = sum(1 for ltr in ev.get("letters", []) if ltr.get("status") == "cancelled")
                print(f"    cancelled {n} of {len(ev.get('letters', []))} letter(s)"
                      f" on {_date(ev.get('at'))}")
        print()
    if len(shown) < len(sent):
        print(f"  showing the last {len(shown)} of {len(sent)}. Use --limit to see more.")
    print(f"  {len(sent)} letter(s) recorded, £{total / 100:.2f} spent live")
    if checked is not None:
        print(f"  checked {checked} job(s) that can still change with the provider")
    print()


# --------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="pennyblack",
        description="Send a physical letter in the UK.",
        epilog="Drafts cost nothing. 'send' is the step that spends money.",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")

    # --json is accepted either before or after the subcommand. People write
    # `pennyblack draft x.pdf --json` far more often than the other way round,
    # and argparse does not allow that unless every subparser declares it too.
    #
    # SUPPRESS matters. With a plain store_true, the subparser sets its own
    # default of False and overwrites a --json given before the subcommand, so
    # `pennyblack --json log` printed text. With SUPPRESS the subparser only
    # sets it when --json is actually given after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="machine-readable output")

    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", parents=[common], help="store your API key")
    s.add_argument("--api-key")
    s.add_argument("--provider", default=cfg.DEFAULT_PROVIDER)
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("services", parents=[common], help="list postage services and what each proves")
    s.set_defaults(func=cmd_services)

    s = sub.add_parser("draft", parents=[common], help="create and price a letter without sending it")
    s.add_argument("source", help="the PDF to post")
    s.add_argument("--service", default="second",
                   help="postage service (default: second). See: pennyblack services")
    s.add_argument("--name", help="recipient name")
    s.add_argument("--line", action="append",
                   help="one address line, without the postcode - repeat for each line, "
                        "e.g. --line \"PO Box 12626\" --line \"Harlow\"")
    s.add_argument("--postcode", help="recipient postcode")
    s.add_argument("--country", default="GB", help="ISO country code (default: GB)")
    s.add_argument("--to-file", help="JSON file with one recipient or a list of them")
    s.add_argument("--address-from-pdf", action="store_true",
                   help="give no recipient, and let the provider read the address "
                        "from the envelope window on page 1 of the PDF")
    s.add_argument("--reference", help="your own label for this job, shown in the dashboard")
    s.add_argument("--envelope", default="c5", choices=["c4", "c5", "c4_plus", "a4_box"])
    s.add_argument("--single-sided", action="store_true", help="print one side per sheet")
    s.add_argument("--black-and-white", action="store_true")
    s.add_argument("--confidential", action="store_true",
                   help="hide the contents from other users of the account dashboard")
    s.add_argument("--background-first", help="background (letterhead) id for page 1")
    s.add_argument("--background-other", help="background id for continuation pages")
    s.add_argument("--live", action="store_true",
                   help="create a real draft rather than a test one")
    s.set_defaults(func=cmd_draft)

    s = sub.add_parser("send", parents=[common], help="confirm a draft - this posts it and charges you")
    s.add_argument("id")
    s.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    s.add_argument("--log-dir", help="where to keep the record "
                   "(default: <git root>/.pennyblack)")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("status", parents=[common],
                       help="status, posting date and tracking number for a job, "
                            "written to the record")
    s.add_argument("id")
    s.add_argument("--log-dir", help="where the record lives "
                   "(default: <git root>/.pennyblack)")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("cancel", parents=[common],
                       help="throw away a draft, or recall a sent letter that has "
                            "not been printed yet")
    s.add_argument("id")
    s.add_argument("--log-dir", help="where the record lives "
                   "(default: <git root>/.pennyblack)")
    s.set_defaults(func=cmd_cancel)

    s = sub.add_parser("log", parents=[common], help="what has been posted from this repository")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--refresh", action="store_true",
                   help="check every letter that can still change with the provider "
                        "first, and record what it says")
    s.add_argument("--log-dir", help="where the record lives "
                   "(default: <git root>/.pennyblack)")
    s.set_defaults(func=cmd_log)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False
    try:
        args.func(args)
    except cfg.ConfigError as exc:
        fail(str(exc))
    except providers.IntelliprintError as exc:
        fail(str(exc))
    except ValueError as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
