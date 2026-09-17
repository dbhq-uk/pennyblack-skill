---
name: pennyblack
description: Post a PDF as a physical letter in the UK, printed and delivered by Royal Mail. Supports Signed For, Tracked 24/48 and Special Delivery, and returns the Royal Mail tracking number. Use when the user wants to post a document, put a PDF in the post, send something by recorded or signed-for delivery, write to someone by post rather than email, or check whether a letter that was posted has arrived. Trigger on phrases like "post this", "send this letter", "put this in the post", "send it recorded delivery", "signed for", "special delivery", "post the invoice", "did that letter arrive", "track that letter".
---

# pennyblack

Post a PDF. It is printed in Leeds and Royal Mail delivers it.

Named after the Penny Black, the 1840 stamp that made it possible to pay once
and have a letter carried anywhere.

**It posts the PDF exactly as it is.** No typesetting, no conversion, no
letterhead applied unless the account has one configured. What the user sees in
their PDF is what comes out of the envelope. If they hand you a `.md`, `.docx`
or anything else, tell them to export it to PDF first rather than converting it
yourself - a letter that gets silently reflowed is a letter that might not say
what they think it says.

## The rule that matters

**Never post anything without showing the user first and getting an explicit
"send it".** Physical post cannot be recalled, and it costs money every time.

The tool is two steps so this is easy to honour:

| | |
|---|---|
| `draft` | uploads it, prices it, returns a preview. **Free. Nothing is printed.** |
| `send`  | commits one draft by id. **This posts it and charges the account.** |

There is no one-shot command, deliberately. Draft it, show the user the cost and
the preview link, wait, then send.

## Setup

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" setup
```

Prompts for an Intelliprint API key (from
https://account.intelliprint.net/api_keys) and writes it to
`~/.dbhq/pennyblack/config.json` at mode 600.

Drafts are **test mode** until `--live` is passed, so the whole flow can be
rehearsed for nothing.

## Posting a letter

**1. Draft it.**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" draft invoice.pdf \
  --name "Acme Ltd" \
  --line "1 High Street, Leeds" \
  --postcode "LS1 1AA" \
  --service signed \
  --reference "Acme - March invoice" \
  --live
```

Returns the job id, the page count, the real cost inc VAT, and a **signed URL to
a PDF preview of the letter as it will be printed** (valid about an hour).

**2. Show the user.** Give them the cost and the preview link. If they are on
another device, serve the preview over Tailscale rather than relying on an
inline render. Then wait.

**3. Send it, only once they have said so.**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" send print_YheDXex1cHsyD9xosrgZu
```

Or bin it with `cancel print_...`.

Ids look like `print_YheDXex1cHsyD9xosrgZu`.

## Choosing the postage

**Ask the user which service. One question, then wait.** Do not pick silently -
the cheapest and dearest differ by more than a factor of ten, and the expensive
ones are often bought for the wrong reason.

Run `python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" services` for the list.
The short version, for one A4 sheet, **excluding VAT**:

| `--service` | What it is | Roughly |
|---|---|---|
| `second` | 2nd Class | £0.84 |
| `first` | 1st Class | £1.94 |
| `signed` | Signed For 1st Class | £4.34 |
| `special` | Special Delivery by 1pm | £11.35 |

VAT is added on top, so `signed` bills at about £5.21. The draft step always
returns the real figure including VAT - quote that, not this table.

Read `references/postage.md` before advising anyone which to buy, because the
obvious answer is often wrong.

**The thing people get wrong:** Signed For is a delivery record, not proof of
service. Under CPR 6.26 and *Diriye v Bojaj*, first class post is deemed served
on the second business day whether or not anybody signed, and what a court wants
certified is the **date of posting**. If someone is paying four times the price
of first class to "make it official", say so. If they need evidence that will
actually hold up, that is Special Delivery, the only service where the signature
can be viewed.

## Checking on a letter

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" status print_YheDXex1cHsyD9xosrgZu
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" log
```

Tracking numbers are issued for `signed`, `signed-second`, `tracked-24`,
`tracked-48`, `special` and `special-9am` only. They appear once the item has
been dispatched, not at the moment of confirmation - so if `send` says "not
issued yet", that is normal, and `status` will have it later.

## The record

Every confirmed send is written to **`.pennyblack/` at the root of the current
git repository** - not to a dotfile in `$HOME`. A record of letters you have
sent is a business record and belongs with the work, in version control.

```
.pennyblack/
  sent.jsonl                             one line per letter, append-only
  2026-09-17-acme-ltd-DpEfeInS.pdf       the document that was actually posted
  README.md                              warns it holds names and addresses
```

**The PDF is captured at the moment of sending, because it cannot be recovered
afterwards** - the provider's preview link is signed and expires within the
hour. A tracking number proves something arrived; only the document proves what.

`--log-dir` puts it somewhere else. Use it to file a client's letters with the
rest of their correspondence rather than at the repo root.

Only credentials live in `~/.dbhq/pennyblack/`.

**Tell the user if the repository is public.** The record holds names and postal
addresses, which is fine in a private repo and a personal-data disclosure in a
public one. The README written into the folder says so and gives the
`.gitignore` line.

## Useful flags

- `--service` - see above. Default `second`.
- `--envelope c5|c4|c4_plus|a4_box` - default `c5`, which holds 15 sheets folded.
- `--single-sided` - default is double-sided, which is cheaper.
- `--black-and-white` - colour is standard and included; this is for preference.
- `--confidential` - hides the contents from other users of the account dashboard.
- `--to-file recipients.json` - `{"name":..., "line":..., "postcode":...}` or a list.
- `--background-first` / `--background-other` - letterhead ids, if the account
  has backgrounds uploaded. Applied at print time, behind the PDF.
- `--json` - machine-readable output, before or after the subcommand.

## When not to use this

- **Anything that must arrive today.** Same-day dispatch needs the job confirmed
  before 3pm, and Royal Mail still has to carry it.
- **Email.** If the recipient reads email, post is slower and costs money.
- **Bulk mailshots.** The API supports mailing lists and thousands of recipients
  per call; this skill deliberately does not, because show-it-and-confirm does
  not make sense for a mailshot.
- **Anything that is not already a PDF.** Export it first.

## Providers

Everything vendor-specific is confined to
`scripts/providers/intelliprint.py`; the commands, the postage vocabulary and
the draft/confirm flow are provider-neutral, so a second backend is a new file
in `scripts/providers/` plus a line in the registry.

Docsaway is the documented fallback if Intelliprint is unavailable: it also does
Royal Mail Signed For by API, from £4.79, but gives no signature copy, offers no
compensation, and is operated from Australia. Worse on price, evidence and data
residency, which is why it is second.
