# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report privately via
GitHub's *Security → Report a vulnerability* (private advisory) on this repo, or
email the maintainer. We aim to acknowledge within a few days.

## Handling secrets (important for this project)

This is a **public repository** and the app operates on people's private Telegram
chats, so secret hygiene is safety-critical:

- Real tokens and API keys belong **only** in `.env`, which is gitignored. Only
  `.env.example` (placeholders) is tracked.
- Never paste a real `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, or a
  `business_connection_id` into code, issues, PRs, or logs.
- `gitleaks` runs in pre-commit and in CI as a backstop against committed
  secrets. If a secret is ever committed, **rotate it immediately** — removing it
  from history is not enough once it has been pushed to a public repo.

## Operational safety

The secretary replies on behalf of a real person. Keep the conservative defaults
(draft-first approval, contact allowlist, active-hours gate). Any change that
enables sending without human approval should be reviewed deliberately.
