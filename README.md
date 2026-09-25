<div align="center">

# pennyblack

**Put a PDF in the post.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://code.claude.com/docs/en/plugins)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey)]()

A free, open-source tool by [DBHQ](https://dbhq.uk) - documented at [skills.dbhq.uk](https://skills.dbhq.uk/pennyblack/)

</div>

---

A PDF goes in. Paper comes out of a print facility in Leeds, and Royal Mail
carries it to a letterbox.

pennyblack is a Claude Code and Codex skill for posting physical letters in the
UK - including **Signed For**, **Tracked 24/48** and **Special Delivery** - and
it records the real Royal Mail tracking number when Royal Mail issues it.

It never converts, typesets or reflows your PDF. The provider adds the address
to page 1, where the envelope window falls, and a small code string down the
left margin, so `draft` saves a preview of the letter as it will be printed.
**What you see in the preview is what comes out of the envelope.**

Named after the Penny Black, the 1840 stamp that made it possible to pay once
and have a letter carried anywhere.

```bash
# 1. Draft it. Free. Nothing is printed.
pennyblack draft notice.pdf --name "Acme Ltd" \
  --line "1 High Street" --line "Leeds" --postcode "LS1 1AA" \
  --service signed --live

#   LIVE       a real draft - send posts it and charges the account
#   draft      print_YheDXex1cHsyD9xosrgZu
#   to         Acme Ltd
#              1 High Street
#              Leeds
#              LS1 1AA
#   service    Royal Mail Signed For 1st Class
#   envelope   C5
#   pages      1 on 1 sheet(s)
#   cost       £5.21 inc VAT (£4.34 + VAT)
#   preview    /tmp/pennyblack-preview-.../print_YheDXex1cHsyD9xosrgZu.pdf
#              https://... (signed link, expires in about an hour)

# 2. Open page 1 of the preview and check the address window.
# 3. Then, and only then:
pennyblack send print_YheDXex1cHsyD9xosrgZu
```

## What makes it different

**Drafting and sending are separate commands, and there is no one-shot option.**
Physical post cannot be recalled once it is printed, and it costs money every
time. So the flow is: create the letter, get the real price and a PDF preview of
the actual thing, show a human, wait. Only `send` spends anything.

**It checks the letter before it uploads it.** `draft` refuses a file that is
not really a PDF or is encrypted, an address given as one line with commas in
it, and a UK postcode in the wrong format. It warns when a page is not A4 or a
letter will not fit its envelope. None of that replaces looking at the preview,
which is why it saves one.

**A mistake spotted just after `send` can often still be stopped.** Until
printing starts, `cancel` recalls each letter still waiting to print, and the
provider refunds it. It reports every letter, so you know which were stopped and
which had already gone to print.

**It tells you the truth about what you are buying.** For a court document
served by post under CPR 6.26, Signed For proves no more than first class. Under
*Diriye v Bojaj*, first class post is deemed served on the second business day
whether or not anyone signed, and what a court wants certified is the date of
posting. pennyblack says so rather than quietly taking four times the price of a
first class stamp.

That point is about court documents only. If a lease, a contract or a statute
names the delivery method, often "registered post or recorded delivery", the
skill tells the agent to send the user to that clause and use the method it
names. It gives postage facts, not legal advice.
See [`references/postage.md`](skills/pennyblack/references/postage.md).

**Test mode is the default.** Every draft is a test draft until you pass
`--live`, so you can wire up and rehearse the whole thing for nothing. A test
never reads as a real letter: the output of `draft`, `send`, `status` and
`cancel` starts with `LIVE` or `TEST`, `send` on a test draft says
`TEST - NOT POSTED` and returns
`posted: false`, and test sends are kept in `test.jsonl`, apart from the
letters that were posted.

**No dependencies.** Standard library Python, 3.9 or newer. No virtualenv, no
packages, no build step.

## Install

### As a Claude Code plugin (recommended)

```
/plugin marketplace add dbhq-uk/marketplace
/plugin install pennyblack@dbhq
```

### Any agent (Cursor, Copilot, Windsurf, Gemini, Cline and more)

```bash
npx skills add dbhq-uk/pennyblack-skill
```

The [skills.sh](https://skills.sh) CLI installs into whichever agent directories
it finds, so this works outside Claude Code and Codex too.

### Local install (Claude Code or Codex)

```bash
git clone https://github.com/dbhq-uk/pennyblack-skill.git
cd pennyblack-skill
./install.sh          # Claude Code: symlinks into ~/.claude/skills (edits are live)
./install-codex.sh    # Codex: installs into ~/.codex/skills
```

[`install.sh`](install.sh) and [`install-codex.sh`](install-codex.sh) are the
same install two ways: Claude Code substitutes `${CLAUDE_SKILL_DIR}`, so the
whole skill directory is symlinked untouched, while Codex does not, so its
`SKILL.md` is rewritten at install time. Re-run the Codex one after editing
`SKILL.md`.

## Requirements

**Python 3.9 or newer**, standard library only. No virtualenv and no
third-party packages - the floor is what CI proves, on 3.9.

An Intelliprint API key, kept in `~/.dbhq/pennyblack/config.json` at mode
600. **This skill spends money when it runs**, which is why `draft` and
`send` are separate commands and drafts are test mode until `--live`.

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
| `draft <file.pdf>` | check, upload and price a letter, and save a preview. Free. Nothing is printed |
| `send <id>` | commit a draft. **This posts it and charges you** |
| `cancel <id>` | throw away a draft, or recall a sent letter that has not been printed yet |
| `status <id>` | status, posting date and Royal Mail tracking number, written to the record |
| `log` | what has been posted from this repository, with costs, status and tracking numbers. `--refresh` checks every letter that can still change first |

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
  test.jsonl, test-*.pdf                 test sends, kept apart - nothing posted
  README.md                              warns it holds names and addresses
```

**It keeps the PDF, not just a reference to one.** The provider's preview link
is signed and expires within the hour, so the document is captured at the moment
of sending or not at all. A tracking number proves something arrived; only the
document proves what.

`sent.jsonl` is append-only and one line per letter, so two sessions posting
letters produce two lines and a merge conflict resolves by keeping both. A
later cancel, or a status check that finds a tracking number or a return, is
added as a new line, never by rewriting one. `pennyblack log` renders it, in UK
time.

Use `--log-dir` to keep a particular client's letters with the rest of their
correspondence instead.

> **If your repository is public**, add `.pennyblack/` to `.gitignore` and use
> `--log-dir` to keep the record somewhere private. It holds names and postal
> addresses. The README written into the folder repeats this.

## Input

**PDF, and only PDF.** Export or print your document to PDF first, then send
that. pennyblack does not convert anything, because a tool that silently reflows
a letter is a tool that can change what the letter says on the page.

If the PDF already has the address on page 1, where the envelope window falls,
draft it with `--address-from-pdf` instead of `--name`, `--line` and
`--postcode`. The provider reads the address from the file, and `draft` shows
what it read.

Letterheads, if your account has one uploaded, are applied by the provider at
print time behind your PDF via `--background-first` and `--background-other`.

## Provider

pennyblack sends through [Intelliprint](https://www.intelliprint.net), a UK
hybrid-mail provider printing in Leeds under ISO 27001, which publishes an
OpenAPI spec, a per-letter rate card and a test mode.

It was chosen over Stannp, Docmail, PostGrid, Lob and Docsaway because it is the
only one that publishes both a Signed For price *and* a signed-for field in a
public API spec, and returns the Royal Mail tracking number.

Most UK hybrid-mail
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

## Also from DBHQ

Every DBHQ agent skill is free, open source and installable from the same
marketplace, and all of them are documented at
**[skills.dbhq.uk](https://skills.dbhq.uk)**. The marketplace itself is
[dbhq-uk/marketplace](https://github.com/dbhq-uk/marketplace) - one
`/plugin marketplace add` and every one of them is available.

| Skill | What it does |
|---|---|
| [outlook](https://skills.dbhq.uk/outlook/) | Microsoft 365 mail and calendar, from the terminal |
| [trello](https://skills.dbhq.uk/trello/) | Your boards, run from your agent |
| [legwork](https://skills.dbhq.uk/legwork/) | Research that settles a decision, and says when it cannot |
| [dovetail](https://skills.dbhq.uk/dovetail/) | Checks whether your repository still agrees with itself |
| [verve](https://skills.dbhq.uk/verve/) | Strips AI tells from prose and puts a voice back |
| [vela](https://skills.dbhq.uk/vela/) | Compiler-exact code search, in any language you index |
| [garmin](https://skills.dbhq.uk/garmin/) | Your Garmin data, answered in the terminal |
| [imager](https://skills.dbhq.uk/imager/) | Images from GPT Image 2, costed before it spends |
| [gitview](https://skills.dbhq.uk/gitview/) | Which branches are finished, and safe to delete |
| [atlassian](https://skills.dbhq.uk/atlassian/) | Jira issues and Confluence pages |
| [buildwork](https://skills.dbhq.uk/buildwork/) | Your open issues, run as parallel agents |
| [deskwork](https://skills.dbhq.uk/deskwork/) | What an agent noticed, tracked as real work |
| [groupwork](https://skills.dbhq.uk/groupwork/) | A second agent on the work, adversary or partner |
| [headwork](https://skills.dbhq.uk/headwork/) | One decision at a time, with a recommendation |

Plus [heliograph](https://skills.dbhq.uk/heliograph/), for a machine you cannot log into.

## Licence

MIT. See [LICENSE](LICENSE).
