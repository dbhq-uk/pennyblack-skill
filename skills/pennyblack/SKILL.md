---
name: pennyblack
description: Send a physical letter in the UK by post, from a markdown draft or an existing PDF, printed and posted via Royal Mail. Supports Signed For, Tracked 24/48 and Special Delivery, and returns the Royal Mail tracking number. Use when the user wants to post a letter, send something by recorded or signed-for delivery, put a document in the post, write to someone by post rather than email, or check whether a letter that was posted has been delivered. Trigger on phrases like "post this", "send a letter", "put this in the post", "send it recorded delivery", "signed for", "special delivery", "write to them by post", "did that letter arrive", "track that letter".
---

# pennyblack

Send a real letter. Markdown or a PDF goes in; paper comes out of a print
facility in Leeds and Royal Mail delivers it.

Named after the Penny Black, the 1840 stamp that made it possible to pay once
and have a letter carried anywhere.

## The rule that matters

**Never post anything without showing the user first and getting an explicit
"send it".** Physical post cannot be recalled, and it costs money every time.

The tool is built as two steps so this is easy to honour:

| | |
|---|---|
| `draft` | creates the letter, prices it, gives you a preview. **Free. Nothing is printed.** |
| `send`  | commits a specific draft. **This posts it and charges the account.** |

There is no one-shot "write and post" command, deliberately. Draft it, show the
user the cost and the preview link, wait for them to say yes, then send.

## Setup

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" setup
```

Prompts for an Intelliprint API key (from
https://account.intelliprint.net/api_keys) and writes it to
`~/.dbhq/pennyblack/config.json` at mode 600.

Everything defaults to **test mode** until `--live` is passed, so you can build
and rehearse the whole flow for nothing.

## Sending a letter

**1. Write it.** Plain markdown. Headings, bold, italic, lists and rules all
work. A single newline becomes a line break, so a sign-off block keeps its
shape:

```markdown
Dear Ms Smith,

Contract **DB-2026-04** refers.

Kind Regards,
Daniel Grimes
```

**2. Draft it.**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" draft letter.md \
  --name "Acme Ltd" \
  --line "1 High Street, Leeds" \
  --postcode "LS1 1AA" \
  --service signed \
  --reference "Acme - contract notice" \
  --live
```

This returns the job id, the page count, the real cost inc VAT, and a **signed
URL to a PDF preview of the actual letter** (valid about an hour).

**3. Show the user.** Give them the cost and the preview link. If they are on
another device, serve the preview over Tailscale rather than relying on an
inline render. Then wait.

**4. Send it, only once they have said so.**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" send prt_abc123
```

Or throw it away with `cancel prt_abc123`.

## Sending an existing PDF

Same thing, but hand it a `.pdf`. No markdown step, no letterhead applied,
printed as-is:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" draft invoice.pdf \
  --name "Acme Ltd" --line "1 High Street, Leeds" --postcode "LS1 1AA" \
  --service first --live
```

## Choosing the postage

**Ask the user which service. One question, then wait.** Do not pick silently -
the cheapest and dearest differ by more than a factor of ten, and the expensive
ones are often bought for the wrong reason.

Run `python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" services` for the list. The short version:

| `--service` | What it is | Roughly |
|---|---|---|
| `second` | 2nd Class | 84p |
| `first` | 1st Class | £1.94 |
| `signed` | Signed For 1st Class | £4.34 |
| `special` | Special Delivery by 1pm | £11.35 |

Prices are indicative - the draft step returns the real figure. Read
`${CLAUDE_SKILL_DIR}/references/postage.md` before advising anyone which to buy, because the
obvious answer is often wrong.

**The thing people get wrong:** Signed For is a delivery record, not proof of
service. Under CPR 6.26 and *Diriye v Bojaj*, first class post is deemed served
on the second business day whether or not anybody signed, and what a court
wants certified is the **date of posting**. If someone is paying £4.34 to "make
it official", say so. If they need evidence that will actually hold up, that is
Special Delivery, which is the only service where you can view the signature.

## Checking on a letter

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" status prt_abc123   # status + tracking number
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" log                 # what this machine has posted
```

Tracking numbers are issued for `signed`, `signed-second`, `tracked-24`,
`tracked-48`, `special` and `special-9am` only. They appear once the item has
been dispatched, not at the moment of confirmation - so if `send` says "not
issued yet", that is normal, and `status` will have it later.

Every confirmed send is appended to `~/.dbhq/pennyblack/sent.jsonl` with its
cost and tracking number. That local record is the point: a tracking number
that exists only in a vendor dashboard is no use when somebody asks in six
months whether a letter went.

## Useful flags

- `--service` - see above. Default `second`.
- `--envelope c5|c4|c4_plus|a4_box` - default `c5`, which holds 15 sheets folded.
- `--single-sided` - default is double-sided, which is cheaper and greener.
- `--black-and-white` - colour is standard and included; this is for preference.
- `--confidential` - hides the contents from other users of the account dashboard.
- `--to-file recipients.json` - `{"name":..., "line":..., "postcode":...}` or a list.
- `--background-first` / `--background-other` - letterhead ids, if the account
  has backgrounds uploaded. Intelliprint applies them at print time, so the
  markdown does not need to carry any branding.
- `--json` - machine-readable output on any command.

## When not to use this

- **Anything that must arrive today.** Same-day dispatch needs the job
  confirmed before 3pm, and then Royal Mail still has to carry it.
- **Email.** If the recipient reads email, post is slower and costs money.
- **Bulk mailshots.** The API supports mailing lists and thousands of
  recipients per call; this skill deliberately does not, because the
  show-it-and-confirm rail does not make sense for a mailshot.

## Providers

The skill talks to Intelliprint. Everything vendor-specific is confined to
`scripts/providers/intelliprint.py`; the commands, the postage vocabulary and
the draft/confirm flow are provider-neutral, so a second backend is a new file
in `scripts/providers/` plus a line in the registry.

Docsaway is the documented fallback if Intelliprint is ever unavailable: it
also does Royal Mail Signed For by API, from £4.79, but it gives you no
signature copy, offers no compensation, and is operated from Australia. It is
worse on price, evidence and data residency, which is why it is second.
