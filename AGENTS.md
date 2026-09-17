# AGENTS.md

Read this before changing anything in this repository.

## What this is

pennyblack posts physical letters in the UK. Running it spends real money and
puts paper through Royal Mail to a real address. Neither is reversible.

That single fact governs every design decision here. If a change makes the tool
more convenient at the cost of making an unintended letter more likely, the
change is wrong.

## The rule that must not be broken

**There is no single command that creates and posts a letter.**

`draft` creates an unconfirmed job. It costs nothing, prints nothing, and
returns the real price plus a preview URL of the actual letter. `send` commits a
specific job by id, and that is the only thing that spends money.

Do not add a `--send-now`, a `--yes` on `draft`, or any other shortcut that
collapses the two. The gap between them is where a human looks at the letter.

`test_draft_is_never_confirmed` and `test_draft_defaults_to_test_mode` exist to
catch this. If you find yourself editing those tests to make a change pass, stop
and reconsider the change.

## Other invariants

**Drafts default to test mode.** `--live` is opt-in. Do not flip the default.

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
rate card (£3.51, £0.84, £4.34).

**The renderer must never lose a sentence.** It converts a subset of markdown
and passes through what it does not understand as plain text. The worst
acceptable outcome is a letter that looks plainer than intended. A letter that
is missing a paragraph is not acceptable. See `test_no_content_is_dropped`.

**Standard library only.** Python 3.9 floor. No dependencies, no virtualenv, no
build step. This is a hard constraint, not a preference - a skill that needs
`pip install` before it can post a letter will not be used.

## Layout

```
skills/pennyblack/
  SKILL.md                     the agent-facing instructions
  scripts/
    pennyblack.py              CLI, safety rails, output
    config.py                  ~/.dbhq/pennyblack/ - key at 600, dir at 700
    render.py                  markdown -> HTML letter
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

`references/postage.md` says Signed For is not proof of service, and cites CPR
6.26 and *Diriye v Bojaj* (2020) EWCA Civ 1400 for it. This is deliberate and
correct: people routinely pay four times the price of first class under a
misconception, and the skill exists partly to say so.

If you update prices or services, update that file and the README table in the
same change, and keep the rate card's effective date accurate. Do not let the
two drift.

## Tests

```bash
cd skills/pennyblack && python3 -m unittest discover -s tests
```

No network, no API key, no account. The transport is stubbed. Keep it that way -
a test suite that posts letters is an expensive test suite.
