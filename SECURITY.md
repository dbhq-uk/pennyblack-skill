# Security

## Reporting a vulnerability

Email **dan@dbhq.uk**. Please do not open a public issue for a security
problem. You will get an acknowledgement within a few working days.

## What pennyblack touches

pennyblack spends money and posts documents to physical addresses, so the
security properties that matter are slightly unusual for a skill.

**Your API key** is stored at `~/.dbhq/pennyblack/config.json`, mode 600, in a
directory created 700. It is sent only to the print provider's API over HTTPS.
It is never logged, never printed, and never included in error output.

**Your letters** are uploaded to the print provider in order to be printed. For
Intelliprint that means a facility in Leeds, under ISO 27001, and the provider
states documents are deleted after printing. If you are sending something that
must not leave your control, do not send it through a print bureau - that is
true of every hybrid mail service, not just this one.

**The record** at `.pennyblack/` in your git repository holds recipient names,
postal addresses, costs, tracking numbers **and a copy of every document you
posted**. That is deliberate - it is the evidence that a letter was sent and of
what it said - but it means the folder is personal data under UK GDPR, and in a
public repository it is a disclosure.

So before `send` confirms anything, it asks GitHub whether the repository is
public (`gh repo view --json visibility`, run in the repository). If it is,
`send` refuses and posts nothing, unless `--log-dir` says where to keep the
record instead. Without `gh`, or for a repository that is not on GitHub, it
cannot tell: it says so and goes ahead, and that judgement is yours.

pennyblack also writes a README into the folder saying what it holds, with the
`.gitignore` line to keep it out of commits, and `--log-dir` moves the whole
record somewhere private.

**Nothing is posted without an explicit `send`.** `draft` never prints or
charges. This is the main safety property of the tool, and it is covered by
tests that assert a draft is always created unconfirmed.

## Scope

In scope: credential handling, anything that could cause a letter to be posted
without an explicit confirmation, anything that could send a letter to the wrong
address, and anything that could leak an API key or letter content.

Out of scope: vulnerabilities in the print provider's own systems - report those
to the provider.
