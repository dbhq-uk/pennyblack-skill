---
name: pennyblack
description: Post a PDF as a physical letter in the UK, printed and delivered by Royal Mail. Supports Signed For, Tracked 24/48 and Special Delivery, and returns the Royal Mail tracking number. Use when the user wants to post a document, put a PDF in the post, send something by recorded or signed-for delivery, write to someone by post rather than email, or check whether a letter that was posted has arrived. Trigger on phrases like "post this", "send this letter", "put this in the post", "send it recorded delivery", "signed for", "special delivery", "post the invoice", "did that letter arrive", "track that letter".
---

# pennyblack

Post a PDF. It is printed in Leeds and Royal Mail delivers it.

Named after the Penny Black, the 1840 stamp that made it possible to pay once
and have a letter carried anywhere.

**It does not convert or typeset anything.** It posts the user's PDF, with no
letterhead unless they ask for one. The provider does add two things to page 1:
the recipient's address, printed where the envelope window falls, and a small
code string down the left margin. So **what you see in the preview is what
comes out of the envelope**, and the preview is what you check. If they hand you
a `.md`, `.docx` or anything else, tell them to export it to PDF first rather
than converting it yourself - a letter that gets silently reflowed is a letter
that might not say what they think it says.

## The rule that matters

**Never post anything without showing the user first and getting an explicit
"send it".** Physical post cannot be recalled once it is printed, and it costs
money every time.

The tool is two steps so this is easy to honour:

| | |
|---|---|
| `draft` | checks it, uploads it, prices it, saves a preview. **Free. Nothing is printed.** |
| `send`  | commits one draft by id. **This posts it and charges the account.** |

There is no one-shot command, deliberately. Draft it, check page 1 of the
preview, show the user the cost and the preview, wait, then send.

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
  --line "1 High Street" \
  --line "Leeds" \
  --postcode "LS1 1AA" \
  --service signed \
  --reference "Acme - March invoice" \
  --live
```

Returns the job id, the address as the provider will print it, the page count,
the real cost inc VAT, and **a PDF preview of the letter as it will be printed,
saved to a local file**. It prints the file's path (`preview_file` in `--json`)
and the provider's signed link to it, which expires in about an hour.

`draft` checks the letter first. It **refuses**, and uploads nothing, when the
file is not a PDF or is encrypted, when the address is one line with commas in
it, or when a UK postcode is not in the right format. It **warns**, and still
drafts, when a page is not A4 or a letter has more sheets than its envelope
holds. Pass every warning on to the user.

**2. Check the address window on page 1.** Open page 1 of the saved preview and
look at the address before anything else. Do this every time. The address is
the one thing nobody can check once the envelope is sealed. It must:

- show the whole address - the name, every line and the postcode - with nothing
  wrapped, cut off or run together
- sit clear of the letter itself, with nothing from the PDF printed under or
  over it
- leave the left margin clear, where the code string is printed

If any of that is wrong, **do not ask for "send it"**. Cancel the draft, fix the
cause, and draft again.

**3. Show the user.** Give them the cost, the preview and any warnings. Then
wait.

**If the PDF already has the address on page 1** in the window position, as an
invoice from accounting software often does, draft with `--address-from-pdf`
and no `--name`, `--line` or `--postcode`. The provider reads the address from
the file, and `draft` shows what it read. Check that against what the user
expects. Never give an address as well as a PDF that has one: what happens when
both are there is not documented.

**4. Send it, only once they have said so.**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" send print_YheDXex1cHsyD9xosrgZu
```

Or bin the draft with `cancel print_...`. Nothing was printed or charged.

**`send` is safe to run again.** If it fails partway, for example a timeout or a
record that cannot be written, run the same `send` again. A job that is already
confirmed is never confirmed twice: if it is missing from the record, `send`
records it and says so; if it is already there, `send` changes nothing. With
`--json`, `send` returns `captured` (was the PDF kept), `document` and `ledger`
(where the record went). Tell the user if `captured` is false.

Ids look like `print_YheDXex1cHsyD9xosrgZu`.

## Recalling a sent letter

A sent letter can still be stopped **until printing starts**. `cancel` on a
confirmed job cancels every letter that is still waiting to print, and the
provider refunds those. Anything already printing, or further on, carries on.
Printing usually starts the same day for a job confirmed before 3pm, so the
window can be a few hours.

**Only with the user's say-so.** Never cancel a sent letter on your own
initiative, even to fix a mistake you spotted. Tell the user and let them decide.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" cancel print_YheDXex1cHsyD9xosrgZu
```

`cancel` reports each letter: `cancelled` means it will not be printed, and any
other status means it was too late. Pass the result on as it is. A cancel on a
sent letter is added to the record.

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
obvious answer is often wrong. **It gives postage facts, not legal advice, and
so do you.** If whether a letter was validly served matters, the user should ask
a solicitor.

**First, ask whether a document names the method.** If a lease, a contract, a
court order or a statute says how the letter must be sent, ask the user to read
that clause and use the method it names. Never tell them another method will
do. Where it says registered post or recorded delivery, use `special`. Getting
this wrong can cost the user a valid notice, such as a break notice.

**Court documents served under CPR 6.26, and only those:** Signed For is a
delivery record, not proof of service. Under CPR 6.26 and *Diriye v Bojaj*,
first class post is deemed served on the second business day whether or not
anybody signed, and what a court wants certified is the **date of posting**. If
someone serving a court document is paying four times the price of first class
to "make it official", tell them. None of this applies to a notice under a
lease, a contract or a statute.

pennyblack gives no certificate of posting. The date of posting is the
`shipped_date` that `status` shows, not the time `send` ran. If the user needs
evidence that will actually hold up, that is Special Delivery, the only service
where the signature can be viewed.

## Checking on a letter

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" status print_YheDXex1cHsyD9xosrgZu
python3 "${CLAUDE_SKILL_DIR}/scripts/pennyblack.py" log --refresh
```

`status` asks the provider about one job, says what each letter's status means
and what to do next, and writes anything new (status, posting date, tracking
number, a return and its reason) to the record. `log --refresh` does the same for
every letter that can still change, then shows the record. Dates are UK time.

Tracking numbers are issued for `signed`, `signed-second`, `tracked-24`,
`tracked-48`, `special` and `special-9am` only, and never at the moment of
confirmation. For Signed For, Intelliprint issues the number **after delivery**.
So if `send` says "not issued yet", that is normal: `status` or `log --refresh`
will pick it up and record it later.

**A letter that failed says so.** `returned` (with Royal Mail's reason),
`invalid_address`, `failed_wrong_address` and `cancelled` each get their own
message. Pass it on to the user as it is. A return matters most for a notice
where service matters - see `references/postage.md`.

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
- `--line` - **one per address line, repeated.** The print house prints each on its own
  line in the envelope window; a single comma-joined string prints as one long line and
  wraps mid-address. Never put the postcode in it - that is `--postcode`.
- `--to-file recipients.json` - `{"name":..., "line": "..." or ["...", "..."], "postcode":...}` or a list.
- `--address-from-pdf` - no recipient; the provider reads the address from page 1 of
  the PDF. Use it only when the PDF already has the address in the window position.
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
