# Contributing to Clera

Thanks for helping build a secretary people can trust with their own name. This
project is small and readable on purpose — a focused contribution lands quickly.

## Getting started

```bash
git clone https://github.com/ebarkhordar/clera && cd clera
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt ruff pre-commit
pre-commit install
python -m app.demo        # feel the product without any setup
pytest -q                 # the suite is fast; keep it green
```

You don't need a Telegram bot, Premium, or an API key to develop: the in-memory
store and the placeholder provider let almost everything run without secrets,
and `python -m app.demo` exercises the whole decision pipeline.

## What makes a good PR here

- **Safety invariants are sacred.** Nothing may be auto-sent without a real LLM
  decision; money/commitments always escalate; placeholder output never reaches
  a contact; stale backlog is never answered. A PR that touches the message
  path should say explicitly how these hold. Tests that pin them are the most
  valuable thing you can write.
- **Small and focused beats broad.** One fix or one feature per PR, with tests.
  The first outside PR to this repo (#1) is a model example: a real bug, a
  clear invariant argument, and better test coverage than the code it fixed.
- **Match the house style.** `ruff check` + `ruff format` are CI-enforced.
  Docstrings explain *why*, comments carry constraints the code can't show.
- **Multilingual matters.** Many users run Clera in Persian, Arabic, or other
  RTL languages. Don't assume English text, LTR rendering, or Latin name
  matching.

## Where help is most wanted

- Linux voice transcription (faster-whisper backend behind
  `app/agent/transcribe.py`)
- Postgres store backend (the store API is small — see `app/store/repo.py`)
- Additional LLM providers behind `app/agent/providers/base.py`
- Webhook mode for the multi-tenant platform (`docs/PLATFORM.md`)
- Real-world reports from the LIVE_TEST runbook on different account setups

## Process

1. For larger changes, open an issue first — the design docs
   (`docs/DESIGN.md`, `docs/PLATFORM.md`) explain current direction.
2. `pre-commit run --all-files && pytest -q` before pushing.
3. PRs run CI (lint, tests, secret scan). First-time contributors' runs need a
   maintainer click — we're quick about it.

## Security

Never include real tokens, chat exports, or database files in issues, PRs, or
fixtures. Vulnerabilities: see [SECURITY.md](SECURITY.md) for private reporting.
