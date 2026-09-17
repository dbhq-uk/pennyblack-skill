#!/usr/bin/env python3
"""pennyblack - send a physical letter in the UK from the command line.

Standard library only. No dependencies, no virtualenv, Python 3.9+.

The shape of this tool is a two-step on purpose:

    draft    creates the letter, prices it, and gives you a preview URL.
             Nothing is printed and nothing is charged.
    send     commits a specific draft by id. This is the step that spends
             money and cannot be undone.

There is no single command that writes a letter and posts it in one go, and
that is not an oversight. Physical post cannot be recalled.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as cfg  # noqa: E402
import ledger  # noqa: E402
import providers  # noqa: E402
from providers.base import Address, EVIDENCE_SERVICES, SERVICES  # noqa: E402


# --------------------------------------------------------------------------
# output helpers


def _out(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    return obj


def fail(message, code=1):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _describe_draft(draft, as_json=False):
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
            "cost_pence": draft.cost.total_pence,
            "cost": str(draft.cost),
            "preview_url": draft.preview_url,
        }, True)

    meta = SERVICES.get(draft.service, {})
    print()
    print(f"  draft      {draft.id}")
    print(f"  to         {', '.join(draft.recipients) or '(none)'}")
    print(f"  service    {meta.get('label', draft.service)}")
    print(f"  pages      {draft.pages} on {draft.sheets} sheet(s)")
    print(f"  cost       {draft.cost}")
    if draft.testmode:
        print("  mode       TEST - nothing will be printed or charged")
    if draft.preview_url:
        print(f"  preview    {draft.preview_url}")
        print("             (signed link, expires in about an hour)")
    print()
    if draft.testmode:
        print("  This is a test draft. Re-run with --live to create a real one.")
    else:
        print(f"  Nothing has been printed or charged yet. To post it:")
        print(f"    pennyblack send {draft.id}")
        print(f"  To throw it away:")
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
    print("  Signed For is a delivery record, not proof of service. See references/postage.md.")
    print()


def _read_source(args):
    """Return the Path to the PDF that will be posted.

    pennyblack posts a document you already have, exactly as it is. It does not
    typeset anything, because a tool that silently reflows a letter is a tool
    that can change what a letter says on the page.
    """
    path = Path(args.source)
    if not path.exists():
        fail(f"no such file: {path}")
    if path.suffix.lower() != ".pdf":
        fail(
            f"pennyblack posts PDFs, and {path.name} is not one.\n"
            "  Export or print your document to PDF first, then send that.\n"
            "  What you see in the PDF is exactly what comes out of the envelope."
        )
    if path.stat().st_size == 0:
        fail(f"{path} is empty")
    return path


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


def _parse_recipient(args):
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
            addr.validate()
            out.append(addr)
        return out

    missing = [f for f in ("name", "line", "postcode") if not getattr(args, f, None)]
    if missing:
        fail(
            "a recipient needs --name, --line and --postcode (or --to-file with JSON).\n"
            f"  missing: {', '.join(missing)}"
        )
    addr = Address(name=args.name, line=_join_lines(args.line), postcode=args.postcode,
                   country=args.country)
    addr.validate()
    return [addr]


def cmd_draft(args):
    conf = cfg.load()
    prov = providers.get(conf)

    if args.service not in SERVICES:
        fail(f"unknown service '{args.service}'. Try: pennyblack services")
    if not prov.supports(args.service):
        fail(f"{prov.name} does not offer '{args.service}'. Try: pennyblack services")

    source = _read_source(args)
    recipients = _parse_recipient(args)

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
    )
    return _describe_draft(draft, args.json)


def cmd_send(args):
    conf = cfg.load()
    prov = providers.get(conf)

    before = prov.retrieve_draft(args.id)
    if before.confirmed:
        fail(f"{args.id} was already confirmed - it is posted or on its way. "
             f"Check it with: pennyblack status {args.id}")

    if not args.yes and sys.stdin.isatty():
        where = ", ".join(before.recipients) or "the address on the draft"
        print(f"\n  About to post {args.id} to {where}")
        print(f"  for {before.cost} by "
              f"{SERVICES.get(before.service, {}).get('label', before.service)}.")
        if not before.testmode:
            print("  Physical post cannot be recalled.")
        print()
        try:
            answer = input("  Type 'send' to confirm: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            fail("cancelled")
        if answer != "send":
            fail("cancelled - nothing was posted")

    draft = prov.confirm(args.id)

    entry = {
        "id": draft.id,
        "provider": draft.provider,
        "service": draft.service,
        "service_label": SERVICES.get(draft.service, {}).get("label", draft.service),
        "recipients": draft.recipients,
        "addresses": [
            l.get("address") for l in (draft.raw.get("letters") or [])
            if l.get("address")
        ],
        "cost_pence": draft.cost.total_pence,
        "pages": draft.pages,
        "testmode": draft.testmode,
        "confirmed_at": draft.raw.get("confirmed_at"),
        "reference": draft.raw.get("reference"),
    }
    tracking = [
        l.get("tracking_number") for l in (draft.raw.get("letters") or [])
        if l.get("tracking_number")
    ]
    if tracking:
        entry["tracking_numbers"] = tracking

    # Capture the document now or never - the preview link is signed and
    # expires within the hour. A tracking number says something arrived; only
    # this says what.
    document = prov.fetch_document(draft)

    log_dir = ledger.resolve_dir(args.log_dir, fallback=cfg.HOME)
    written = ledger.record(entry, log_dir=log_dir, document=document)

    if args.json:
        return _out(entry, True)

    print()
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
        print("  tracking   not issued yet - check again once it has been dispatched:")
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
    if args.json:
        return _out([{
            "id": m.id, "status": m.status, "service": m.service,
            "tracking_number": m.tracking_number, "recipient": m.recipient,
            "shipped_date": m.shipped_date,
        } for m in mailings], True)

    if not mailings:
        print(f"  no mail items on {args.id}")
        return
    print()
    for m in mailings:
        print(f"  {m.recipient or m.id}")
        print(f"    status   {m.status}")
        print(f"    service  {SERVICES.get(m.service, {}).get('label', m.service)}")
        if m.tracking_number:
            print(f"    tracking {m.tracking_number}")
            print(f"             https://www.royalmail.com/track-your-item#/tracking-results/{m.tracking_number}")
        elif m.service in EVIDENCE_SERVICES:
            print("    tracking not issued yet")
    print()


def cmd_cancel(args):
    conf = cfg.load()
    prov = providers.get(conf)
    prov.cancel(args.id)
    print(f"  cancelled {args.id}")


def cmd_log(args):
    log_dir = ledger.resolve_dir(args.log_dir, fallback=cfg.HOME)
    entries = ledger.read(log_dir)
    if args.json:
        return _out(entries, True)
    if not entries:
        print(f"  nothing posted from this repository yet ({log_dir}/sent.jsonl)")
        return

    import datetime as _dt
    print()
    print(f"  {log_dir}")
    print()
    total = 0
    for e in entries[-args.limit:]:
        mode = "  [test]" if e.get("testmode") else ""
        pence = e.get("cost_pence", 0)
        if not e.get("testmode"):
            total += pence
        when = e.get("confirmed_at")
        date = (_dt.datetime.fromtimestamp(when, tz=_dt.timezone.utc).strftime("%d %b %Y")
                if isinstance(when, (int, float)) and when else "")
        print(f"  {date}  {', '.join(e.get('recipients') or ['?'])}{mode}")
        print(f"    {e.get('service_label') or e.get('service','?')}  -  "
              f"£{pence / 100:.2f}")
        if e.get("reference"):
            print(f"    ref      {e['reference']}")
        for t in e.get("tracking_numbers", []):
            print(f"    tracking {t}")
        if e.get("document"):
            print(f"    document {e['document']}")
        print()
    print(f"  {len(entries)} letter(s) recorded, £{total / 100:.2f} spent live")
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
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
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

    s = sub.add_parser("status", parents=[common], help="status and tracking number for a job")
    s.add_argument("id")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("cancel", parents=[common], help="throw away an unconfirmed draft")
    s.add_argument("id")
    s.set_defaults(func=cmd_cancel)

    s = sub.add_parser("log", parents=[common], help="what has been posted from this repository")
    s.add_argument("--limit", type=int, default=20)
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
