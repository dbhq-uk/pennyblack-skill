# AGENTS.md

Read this before changing anything in this repository.

## What this is

pennyblack posts physical letters in the UK. Running it spends real money and
puts paper through Royal Mail to a real address. Once the letter is printed,
neither is reversible. A sent letter can be recalled only in the short window
before printing starts, so the tool treats `send` as final.

That single fact governs every design decision here. If a change makes the tool
more convenient at the cost of making an unintended letter more likely, the
change is wrong.

## The rule that must not be broken

**There is no single command that creates and posts a letter.**

`draft` creates an unconfirmed job. It costs nothing, prints nothing, and
returns the real price plus a preview of the actual letter, saved to a local
file so the agent can open page 1 and check the address. `send` commits a
specific job by id, and that is the only thing that spends money.

Do not add a `--send-now`, a `--yes` on `draft`, or any other shortcut that
collapses the two. The gap between them is where a human looks at the letter.

`TestDraftSendRail` in `tests/test_cli.py` holds this at the command line an
agent runs. It drives `pennyblack.main()` against a stub provider and against the
real Intelliprint class with its network cut out. It fails if `draft` asks for a
confirmed job, calls `confirm`, runs live without `--live`, gains a confirm-style
option, or if a new subcommand appears. `test_draft_is_never_confirmed` and
`test_draft_defaults_to_test_mode` hold the same rule one layer down, in the
provider. If you find yourself editing any of these tests to make a change pass,
stop and reconsider the change.

## Other invariants

**Drafts default to test mode.** `--live` is opt-in. Do not flip the default.

**`send` can be bound to the price the user approved, and a draft is capped at
5 recipients.** `send --expect-cost` compares the job's cost inc VAT to the
penny before confirming, and refuses on any difference. `draft` refuses more
than `MAX_RECIPIENTS` unless `--max-recipients` is given, because one `send`
posts to every recipient on the job. Do not raise the cap or loosen the
comparison to make something convenient.

**A test send never reads as posted.** `send` on a test draft leads with
`TEST - NOT POSTED`, returns `posted: false` in `--json`, and is recorded in
`test.jsonl`, never `sent.jsonl`, so a test cannot be counted or reported as a
letter that went. The output of `draft`, `send`, `status` and `cancel` starts
with `LIVE` or `TEST`. `TestTestSends` in `tests/test_cli.py` holds this.

**An unsupported postage service is an error, never a downgrade.** If someone
asks for Special Delivery and the provider cannot do it, the tool must refuse.
Silently posting second class when Special Delivery was requested would be the
worst possible failure. `test_unsupported_service_is_refused_not_downgraded`
covers this.

**The cost divisor is 10^8, and lives in exactly one function.** Intelliprint
returns money as an integer scaled by 100,000,000 - not 100. Getting this wrong
understates a letter by a factor of a million, and it is invisible in test mode
because test mode costs nothing either way. All conversion goes through
`_money()` in `providers/intelliprint.py`, which is tested against the published
rate card (£3.51, £0.84, £4.34 - all excluding VAT).

**pennyblack posts PDFs and does not convert anything.** There was a markdown
renderer; it was removed on 17 September 2026, deliberately. A tool that
reflows a document before printing it can change what the document says on the
page, and the user never sees the difference until it is in an envelope. If a
future change reintroduces conversion, the preview step stops being a guarantee
and becomes a hope.

**Credentials and the record live in different places, and must stay that way.**
`config.py` owns `~/.dbhq/pennyblack/` and holds the API key and nothing else.
`ledger.py` owns `.pennyblack/` in the user's git repository and holds what was
posted. Two tests assert the separation. Putting the record back in `$HOME`
would hide a business record in a dotfile; putting the key in the repository
would commit it.

**The record is never written into a public repository by default.** Before
`send` confirms anything, `_check_not_public` asks `gh repo view --json
visibility` in the repository, and refuses on `PUBLIC` unless `--log-dir` is
given. It runs before the confirm, never after, so a refusal can never leave a
posted letter out of the record. Without `gh`, or when `gh` cannot say, it warns
and goes ahead, as it did before the check existed. `TestPublicRepository` in
`tests/test_cli.py` holds this with a fake `gh` on `PATH`.

**The record is append-only, and it keeps up with the letter.** `send` writes
one line. After that, `cancel`, `status` and `log --refresh` append event lines
(a cancel, a tracking number, a posting date, a return and its reason). Nothing
rewrites an earlier line, so a merge still resolves by keeping both sides.
`status` writes only for a job that is already in the record, so it never
starts a record of names and addresses somewhere new.

**The document is captured at send time or never.** The provider's preview link
is signed and short-lived. If a change defers fetching it, the record silently
degrades to a tracking number, which proves something arrived but not what.
A failed capture is reported, not swallowed - see the "NOT captured" branch in
`cmd_send`.

**`send` is safe to retry, and a posted letter always reaches the record.**
If `send` finds the job already confirmed, it never confirms it again. It
records it if the record has no line for it, and changes nothing if it does.
That covers a confirm that timed out after the provider processed it. If the
record cannot be written after confirm, `send` prints the entry on stderr and
exits non-zero with a plain message, never a traceback. `TestSend` in
`tests/test_cli.py` holds all of this.

**The address gets tests, always.** It is the only field that decides whether a
letter arrives, and the sender cannot check it once the envelope is sealed. A
comma-joined address shipped in the first version and wrapped mid-address in the
envelope window on a real PO Box letter, which was only found after it had gone.
`--line` is repeatable and joined with newlines; `test_address.py` holds that
down, including that it is never joined with a comma again. `draft` also
refuses an address given as one line with commas in it, and a UK postcode in
the wrong format, before anything is uploaded (`checks.py`, `test_checks.py`).

**The PDF is not quite what gets printed, so the preview is the check.** The
provider prints the address onto page 1 where the envelope window falls, and a
code string down the left margin. Do not describe pennyblack as posting the PDF
"exactly" as given: what you see in the preview is what comes out. `draft`
saves the preview to a private temporary file, and SKILL.md makes the agent
open page 1 before it asks for "send it".

**Standard library only.** Python 3.9 floor. No dependencies, no virtualenv, no
build step. This is a hard constraint, not a preference - a skill that needs
`pip install` before it can post a letter will not be used.

## Layout

```
skills/pennyblack/
  SKILL.md                     the agent-facing instructions
  scripts/
    pennyblack.py              CLI, safety rails, output
    checks.py                  cheap checks on the PDF and the address, before upload
    config.py                  ~/.dbhq/pennyblack/ - key at 600, dir at 700
    ledger.py                  <git root>/.pennyblack/ - what was posted
    providers/
      base.py                  the interface + the postage vocabulary
      intelliprint.py          every Intelliprint-specific fact
      __init__.py              registry
  references/postage.md        what each service actually proves
  tests/
```

Provider-specific knowledge belongs in `providers/<name>.py` and nowhere else.
If you find yourself writing `uk_first_class_signed_for` outside that file, or
outside a test, something has leaked.

## Adding a provider

See CONTRIBUTING.md. The short version: a new file in `providers/`, a
`service_map` that omits anything the vendor genuinely cannot do, the four
methods, and a line in the registry. Nothing else changes.

## Postage advice is a factual matter

The skill gives postage facts, not legal advice. Keep it that way.

`references/postage.md` says that for a court document served by post under
CPR 6.26, Signed For is not proof of service, and cites *Diriye v Bojaj* (2020)
EWCA Civ 1400 for it. That is correct for court documents, and only for them.

It is wrong for a notice under a lease, a contract or a statute that names the
method, often "registered post or recorded delivery". Other rules apply there,
such as the Recorded Delivery Service Act 1962 s.1 and the Law of Property Act
1925 s.196(4). So `postage.md` tells the agent to send the user to that clause
and use the method it names, and never to say another method will do. Do not
widen the CPR point beyond court documents again: an agent following it could
talk a user out of the method their lease requires and cost them a valid
notice. `tests/test_docs.py` holds the limit.

If you update prices or services, update that file and the README table in the
same change, and keep the rate card's effective date accurate. Do not let the
two drift.

## Tests

```bash
cd skills/pennyblack && python3 -m unittest discover -s tests
```

No network, no API key, no account. The transport is stubbed. Keep it that way -
a test suite that posts letters is an expensive test suite.
