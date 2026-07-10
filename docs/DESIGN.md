# Design & product notes

Internal context for contributors: what this project is aiming to be, why it is
built the way it is, and where it is going. User-facing setup lives in the
[README](../README.md).

> **Direction update (2026-07):** the product is now a *fully automatic*
> secretary (no draft approval; the agent replies, stays silent, or escalates
> to the owner) delivered as a hosted platform built on managed bots and
> pay-per-usage Stars billing. [PLATFORM.md](PLATFORM.md) is the source of
> truth for that direction and the backlog; sections below are updated where
> they conflicted.

## Vision

Make it trivial for a non-technical person to have their own Telegram secretary —
a bot that reads their incoming messages and drafts (or, when trusted, sends)
replies on their behalf. The bar is: connect in a few taps, no servers, no code.

## Two Telegram mechanisms

The product combines two features from the
[Bot platform](https://core.telegram.org/bots/features):

1. **Business connection ("secretary bots")** — lets a bot read and reply inside
   a user's *personal* chats. Incoming messages arrive as `business_message`
   updates; replies are sent with a `business_connection_id` so they go out as
   the user. This is the core capability.
2. **Managed bots** — lets a platform provision a bot for a user with a single
   tap (no BotFather). The bot is **owned by the user**, but the platform fetches
   its token via `getManagedBotToken` and operates it. This is what makes
   onboarding turnkey.

The MVP implements (1) end-to-end and stubs (2) in
[`app/handlers/managed.py`](../app/handlers/managed.py).

## Architecture

```
Telegram ──business_message──► Gateway (webhook / polling)
                                   │
                                   ▼
                     Router (per business_connection_id)
                          │            │             │
                          ▼            ▼             ▼
                     Policy        Agent loop    Metering
                   (allowlist,    (provider +   (token → cost
                    hours)         prompt)        estimate)
                          │            │
                          └────────────┴──► control chat (approve) ──► send as user
```

Design intent:

- **Keep the core boring.** The differentiation is onboarding, safety and (later)
  billing — not a bespoke agent runtime. The provider layer wraps LLM APIs
  directly rather than adopting a heavy agent framework.
- **Storage is swappable.** Backends implement a small shared API selected by
  `app/store/repo.py` (`STORE_BACKEND`): persistent SQLite by default, in-memory
  for tests. Postgres can slot in the same way without touching call sites.
- **Providers are pluggable** behind `app/agent/providers/base.py`.

## Safety posture

Replying as a real person is high-stakes. The product is fully automatic, so
safety lives in the *agent's decision protocol* rather than human approval:

- **Reply / silent / notify.** For every message the agent either replies,
  stays silent, or escalates to the owner (`[SILENT]` / `[NOTIFY]` markers,
  parsed in `app/agent/secretary.py`). Money, commitments, and unknown facts
  are always escalated, never guessed.
- **Placeholder output is never auto-sent** — with no LLM configured the
  message is escalated to the owner instead.
- **Never talk over the owner**: if the owner replied while a response was
  being generated, it is dropped.
- **Allowlist + active hours** gate which chats the agent engages at all.
- **Review mode** (draft + approve) remains as an opt-in per connection
  (`auto_send = false`), no longer the default.
- The system prompt forbids inventing facts, commitments, times, prices, or
  agreeing to payments/contracts.

## Per-contact memory

For replies to read as the owner and stay consistent across thousands of
messages, each contact thread carries its own memory:

- **Message history** — every message in a connected chat is stored
  (`messages` table), keyed by `(business_connection_id, chat_id)`. Both
  directions are captured: `in` = from the contact, `out` = from the owner
  (typed manually **or** sent by the bot after approval).
- **Owner voice** — the owner's *own* typed messages arrive as `business_message`
  updates too, so we learn how they actually write. Crucially, messages the owner
  types themselves are recorded but **never** trigger a draft (split on
  `sender_id == owner_user_id`).
- **Durable profile** — a `contacts` row per thread holds an LLM-maintained
  summary (who they are, the tone/language the owner uses with them, key facts).
  It is rebuilt every `PROFILE_REFRESH_EVERY` messages by summarizing recent
  history, so context survives beyond the recent-message window.

A draft is built from: the durable profile + the last `HISTORY_LIMIT` messages
rendered as a transcript. The prompt instructs the model to reply in the
conversation's own language and mirror the owner's style. Summarization runs off
the event loop (`asyncio.to_thread`) so it never blocks message handling.

**Cost note:** including history enlarges each prompt, and profile refreshes add
periodic calls. With the Claude CLI backend, per-call overhead is high (it
carries Claude Code's cached system prompt); an API key is far cheaper at scale.

**Privacy:** this persistently stores the private message content of every
contact. For a hosted product that carries real consent/retention/GDPR-type
obligations (data minimization, deletion, encryption at rest). Not addressed in
the MVP beyond local SQLite — must be before any public offering.

## Business model (direction, not built)

Open-core: this repository is the trust anchor and self-host option; a hosted
service would layer on top. Usage would be metered per token with a markup over
raw provider cost, and users would choose a model tier. Prepaid billing is
**deferred** — the current code only shows an informational per-draft cost
estimate and does not track balances or gate on credit.

## Constraints & open questions

- **Telegram Premium is required** for Business connections. This bounds the
  addressable audience and must be communicated up front.
- **`business_connection` rights mapping** varies across `python-telegram-bot`
  versions; `can_reply` is read defensively and needs confirming against a live
  Premium connection.
- **Abuse & ToS.** A single manager bot fronting many users is a takedown risk;
  rate limiting and content guardrails are needed before any public offering.

## Roadmap

Moved to the backlog in [PLATFORM.md](PLATFORM.md). Done so far:

- [x] Persistent storage — SQLite (Postgres next)
- [x] Per-contact memory — thread history + owner-voice capture + durable profiles
- [x] Automatic replies with reply/silent/notify decisions (approval now opt-in)
- [x] Managed-bot provisioning (`managed_bot` update → `getManagedBotToken`)
- [x] Multi-bot runtime — `python -m app.platform`, polling (webhook gateway next)
