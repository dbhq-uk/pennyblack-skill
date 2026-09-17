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

**The send log** at `~/.dbhq/pennyblack/sent.jsonl` records recipient names,
costs and tracking numbers. It does not record letter contents. It is mode 600.
It may still be personal data under UK GDPR, so treat it accordingly.

**Nothing is posted without an explicit `send`.** `draft` never prints or
charges. This is the main safety property of the tool, and it is covered by
tests that assert a draft is always created unconfirmed.

## Scope

In scope: credential handling, anything that could cause a letter to be posted
without an explicit confirmation, anything that could send a letter to the wrong
address, and anything that could leak an API key or letter content.

Out of scope: vulnerabilities in the print provider's own systems - report those
to the provider.
