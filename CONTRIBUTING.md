# Contributing

Thanks for looking. Issues and pull requests are welcome.

## Running the tests

```bash
cd skills/pennyblack && python3 -m unittest discover -s tests
```

No network and no account are needed. The provider is stubbed.

## House rules

- **Standard library only.** No dependencies, no virtualenv, no build step.
  Python 3.9 is the floor.
- **British English**, and a plain hyphen rather than an em dash or en dash.
- **Never make it possible to post a letter in one step.** The split between
  `draft` and `send` is the whole safety story. A pull request that adds a
  `--send-now` shortcut will be declined, however convenient.
- **Do not weaken the default.** Drafts are test mode until `--live`.
- **Money arithmetic stays in one place.** `_money()` in the provider is the
  only function that knows about the cost divisor. It is tested against the
  published rate card.

## Adding a provider

Everything vendor-specific lives in `skills/pennyblack/scripts/providers/`.
To add one:

1. Write a module subclassing `Provider` from `providers/base.py`.
2. Fill in `service_map`, mapping pennyblack's service names to the vendor's.
   **Leave out anything the vendor cannot do** - pennyblack will then say so
   plainly rather than silently downgrading a letter to a cheaper service.
3. Implement `draft`, `confirm`, `cancel` and `status`.
4. Register it in `providers/__init__.py`.
5. Add tests that stub the transport, following `test_intelliprint.py`.

A provider that cannot create a letter without immediately sending it does not
fit this skill, because it cannot offer the show-it-before-you-post rail.

## Commit messages

Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
