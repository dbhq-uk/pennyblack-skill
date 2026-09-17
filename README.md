<div align="center">

# pennyblack

**Put a PDF in the post.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://code.claude.com/docs/en/plugins)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey)]()

A free, open-source tool by [DBHQ](https://dbhq.uk)

</div>

---

A PDF goes in. Paper comes out of a print facility in Leeds, and Royal Mail
carries it to a letterbox.

pennyblack is a Claude Code and Codex skill for posting physical letters in the
UK - including **Signed For**, **Tracked 24/48** and **Special Delivery** - and
it hands you back the real Royal Mail tracking number.

It posts your PDF **exactly as it is**. No conversion, no typesetting, no
reflowing. What you see in the PDF is what comes out of the envelope.

Named after the Penny Black, the 1840 stamp that made it possible to pay once
and have a letter carried anywhere.

```bash
# 1. Draft it. Free. Nothing is printed.
pennyblack draft notice.pdf --name "Acme Ltd" \
  --line "1 High Street" --line "Leeds" --postcode "LS1 1AA" \
  --service signed --live

#   draft      print_YheDXex1cHsyD9xosrgZu
#   to         Acme Ltd
#   service    Royal Mail Signed For 1st Class
#   pages      1 on 1 sheet(s)
#   cost       £5.21 inc VAT (£4.34 + VAT)
#   preview    https://... (signed link, expires in about an hour)

# 2. Look at the preview. Then, and only then:
pennyblack send print_YheDXex1cHsyD9xosrgZu
```

## Why it is built this way

**Drafting and sending are separate commands, and there is no one-shot option.**
Physical post cannot be recalled and costs money every time. So the flow is:
create the letter, get the real price and a PDF preview of the actual thing,
show a human, wait. Only `send` spends anything.

**It tells you the truth about what you are buying.** Most people reach for
Signed For because they want to prove a letter was served. It does not do that.
Under CPR 6.26 and *Diriye v Bojaj*, first class post is deemed served on the
second business day whether or not anyone signed, and what a court wants
certified is the date of posting. pennyblack says so rather than quietly taking
four times the price of a first class stamp.
See [`references/postage.md`](skills/pennyblack/references/postage.md).

**Test mode is the default.** Every draft is a test draft until you pass
`--live`, so you can wire up and rehearse the whole thing for nothing.

**No dependencies.** Standard library Python, 3.9 or newer. No virtualenv, no
packages, no build step.

## Install

**As a plugin** (Claude Code):

```
/plugin marketplace add dbhq-uk/marketplace
/plugin install pennyblack@dbhq
```

**Or from source:**

```bash
git clone https://github.com/dbhq-uk/pennyblack-skill.git
cd pennyblack-skill
./install.sh          # Claude Code
./install-codex.sh    # Codex
```

Then get an API key from
[account.intelliprint.net/api_keys](https://account.intelliprint.net/api_keys)
and run:

```bash
python3 ~/.claude/skills/pennyblack/scripts/pennyblack.py setup
```

The key is written to `~/.dbhq/pennyblack/config.json` at mode 600. It never
leaves your machine except to talk to the print provider.

## What it costs

Prices below are the provider's published rate card effective 5 January 2026,
for a single-sided A4 letter in a C5 envelope, excluding VAT, including
printing, the envelope and the postage. `draft` always returns the real figure.

| `--service` | Service | Price | Signature | Tracked |
|---|---|---|---|---|
| `second` | 2nd Class | £0.84 | | |
| `first` | 1st Class | £1.94 | | |
| `signed-second` | Signed For 2nd Class | £3.51 | yes | |
| `signed` | Signed For 1st Class | £4.34 | yes | |
| `tracked-48` | Tracked 48 | varies | optional | yes |
| `tracked-24` | Tracked 24 | varies | optional | yes |
| `special` | Special Delivery by 1pm | £11.35 | viewable | yes |
| `special-9am` | Special Delivery by 9am | £48.97 | viewable | yes |

There is no minimum order, no monthly fee and no contract. You are billed for
what you send.

## Commands

| | |
|---|---|
| `setup` | store your API key |
| `services` | list postage options and what each one actually proves |
| `draft <file.pdf>` | upload and price a letter. Free. Nothing is printed |
| `send <id>` | commit a draft. **This posts it and charges you** |
| `cancel <id>` | throw away an unconfirmed draft |
| `status <id>` | status and Royal Mail tracking number |
| `log` | what this machine has posted, with costs and tracking numbers |

Add `--json` to any of them for machine-readable output, before or after the
subcommand.

## The record

Every confirmed send is written to **`.pennyblack/` at the root of your git
repository**, not to a dotfile in `$HOME`. Credentials are machine state; a
record of what you have posted is a business record, and it belongs with the
work where you can read, diff and grep it a year later.

```
.pennyblack/
  sent.jsonl                             one line per letter, append-only
  2026-09-17-acme-ltd-DpEfeInS.pdf       the document that was actually posted
  README.md                              warns it holds names and addresses
```

**It keeps the PDF, not just a reference to one.** The provider's preview link
is signed and expires within the hour, so the document is captured at the moment
of sending or not at all. A tracking number proves something arrived; only the
document proves what.

`sent.jsonl` is append-only and one line per letter, so two sessions posting
letters produce two lines and a merge conflict resolves by keeping both.
`pennyblack log` renders it.

Use `--log-dir` to keep a particular client's letters with the rest of their
correspondence instead.

> **If your repository is public**, add `.pennyblack/` to `.gitignore` and use
> `--log-dir` to keep the record somewhere private. It holds names and postal
> addresses. The README written into the folder repeats this.

## Input

**PDF, and only PDF.** Export or print your document to PDF first, then send
that. pennyblack does not convert anything, because a tool that silently reflows
a letter is a tool that can change what the letter says on the page.

Letterheads, if your account has one uploaded, are applied by the provider at
print time behind your PDF via `--background-first` and `--background-other`.

## Provider

pennyblack sends through [Intelliprint](https://www.intelliprint.net), a UK
hybrid-mail provider printing in Leeds under ISO 27001, which publishes an
OpenAPI spec, a per-letter rate card and a test mode.

It was chosen over Stannp, Docmail, PostGrid, Lob and Docsaway because it is the
only one that publishes both a Signed For price *and* a signed-for field in a
public API spec, and returns the Royal Mail tracking number. Most UK hybrid-mail
providers cannot offer Signed For at all: an automated enclosing line cannot
apply the per-item barcoded label Royal Mail scans at acceptance.

Everything provider-specific lives in
[`scripts/providers/intelliprint.py`](skills/pennyblack/scripts/providers/intelliprint.py).
The commands, the postage vocabulary and the draft/confirm flow are
provider-neutral, so a second backend is a new file plus a line in the registry.

pennyblack is not affiliated with Intelliprint or Royal Mail. Royal Mail,
Signed For and Special Delivery Guaranteed are trade marks of Royal Mail Group
Ltd.

## Tests

```bash
cd skills/pennyblack && python3 -m unittest discover -s tests
```

No network, no account needed.

## Licence

MIT. See [LICENSE](LICENSE).
