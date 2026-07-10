# Platform direction: hosted, automatic, managed bots

This document is the source of truth for where Clera is going. It supersedes
the draft-first posture described in early versions of [DESIGN.md](DESIGN.md).

## Product definition

A non-technical person gets **their own Telegram secretary bot** in a few taps.
The bot reads their personal chats and **replies automatically, in their voice,
based on conversation history** — no approve/discard step. They pay per usage.
Everything (hosting, keys, models, ops) is on our side.

Three pillars:

1. **Their own bot, operated by us** — Telegram *managed bots*.
2. **Fully automatic replies** — quality and safety come from memory + an
   escalation path, not from human approval of every message.
3. **Pay-per-usage** — prepaid balance in Telegram Stars, metered per token.

## Verified Telegram platform facts

From https://core.telegram.org/bots/features (checked 2026-07-10):

### Business connections (secretary bots)

- A user connects a bot to their **personal account**; the bot receives
  `business_message`, `edited_business_message`, `deleted_business_messages`
  and `business_connection` updates, and replies as the user via
  `business_connection_id` in send methods.
- The owner chooses which chats the bot can access; write permission is the
  `can_reply` field of the latest `BusinessConnection` update.
- **The bot can only act in chats that were active in the last 24h.**
- The bot receives all updates *except* messages sent by itself and other bots.
- Secretary Mode is enabled in BotFather. On connection, the bot receives a
  deep-link message `/start bizChat<user_chat_id>`.
- Users see a "quick action bar" with **Manage Bot** at the top of each managed
  chat.
- Compliance: Bot Developer Terms of Service, **Section 5.4** specifically.
- **Open question:** the page does not mention a Telegram Premium requirement.
  Our README currently claims Premium is required — verify against a live
  account; if unneeded, the addressable market is much larger.

### Managed bots (one-tap provisioning)

- A *manager bot* with **Bot Management Mode** (enabled in BotFather's MiniApp)
  can create bots on behalf of users.
- Creation link: `https://t.me/newbot/{manager_bot_username}/{new_username}?name={new_name}`
  — user taps, sees a pre-filled (editable) confirmation, done.
- The new bot is **owned by the user**, not by us. Usernames must end in `bot`.
- The manager receives a `managed_bot` update (`ManagedBotUpdated`), then calls
  **`getManagedBotToken`** to obtain the operating token and controls the bot
  via the normal Bot API (profile, settings, messages, webhook).
- **Open question:** whether Secretary Mode can be enabled programmatically on
  a managed bot, or whether the owner must toggle it — determines onboarding
  tap count.

### Payments

- Digital goods/services **must** be charged in **Telegram Stars** (`XTR`);
  other currencies are not allowed for digital services.
- Users buy Stars via Apple/Google in-app purchase or @PremiumBot — no card
  onboarding on our side.
- Flow: `sendInvoice` → `answerPreCheckoutQuery` → successful-payment service
  message. Telegram takes no fee and stores no order data.
- Subscriptions with tiers are natively supported.

### Other relevant primitives

- **Mini Apps**: full web UI inside Telegram — our settings/usage/top-up screen,
  no external website or login.
- **Deep linking** (`?start=parameter`, ≤64 chars of `A-Za-z0-9_-`) for
  attributing onboarding.
- `language_code` arrives on every update — localize automatically.
- BotFather sends **status alerts** when a bot's reply rate is abnormally low
  (~300 requests/minute threshold) — feed into our monitoring.

## Why per-client bots matter

- Each client's traffic runs under **their own bot identity** — rate limits and
  abuse reputation are distributed; no single bot fronting everyone (takedown
  risk flagged in DESIGN.md disappears).
- The client owns their bot; we hold only an operating token. Clean exit story.
- The client's bot is also their UI surface: control chat, Mini App, invoices.

## Target architecture

```
Client ──taps──► manager bot (@Clera…) ──creation link──► client's own bot
                     │                                        (owned by client)
                     │ managed_bot update → getManagedBotToken
                     ▼
        ┌──────────────────────── Clera platform ────────────────────────┐
        │ bot registry (tokens, encrypted)                               │
        │ update ingestion: one runner/webhook per managed bot           │
        │ auto-reply engine: profile + history → reply | silent | notify │
        │ metering → Stars balance (prepaid, gated)                      │
        │ Mini App: settings, usage, top-up                              │
        └─────────────────────────────────────────────────────────────────┘
```

### The auto-reply engine (replaces approval)

There is no send/discard. Per incoming contact message the agent chooses one of:

- **reply** — send immediately as the owner (the default path);
- **silent** — no reply is warranted (conversation ended, owner is handling it);
- **notify** — the message needs the owner personally (payments, commitments,
  facts the agent doesn't have); the owner gets a heads-up in their control
  chat, nothing is sent to the contact.

Guardrails that make automatic sending safe:

- per-contact durable profile + thread history (already built);
- owner-voice learning: the owner's own messages are recorded, never replied to;
- if the owner has replied in the thread more recently than the contact's
  message being processed, stay silent (owner is actively chatting);
- placeholder completions (no API key) are **never** auto-sent;
- optional allowlist = "only handle these contacts"; active-hours window;
- the system prompt forbids invented facts/commitments; those become **notify**.

## Feature backlog (priority order)

| # | Feature | Status |
|---|---------|--------|
| 1 | Auto-reply engine with reply/silent/notify decisions | **in progress** |
| 2 | Managed-bot provisioning (`managed_bot` update, `getManagedBotToken`) | **in progress** |
| 3 | Multi-bot runtime (one process running manager + N secretary bots) | **in progress** — polling now, webhook gateway next |
| 4 | Webhook gateway (per-bot webhooks, public deployment, Docker) | planned |
| 5 | Stars billing: prepaid balance, `sendInvoice`/`XTR`, gate replies on credit | planned |
| 6 | Media understanding: transcribe voice notes, describe images | planned |
| 7 | Mini App: settings (tone, allowlist, hours), usage, top-up | planned |
| 8 | Postgres backend + encrypted token/message storage | planned |
| 9 | Retention/deletion controls (GDPR posture) before public launch | planned |
| 10 | Localization via `language_code` | planned |
| 11 | Monitoring + BotFather status-alert handling | planned |

## Open questions to verify on a live account

1. Is Telegram Premium required for business connections? (README says yes;
   the features page doesn't mention it.)
2. Can Secretary Mode be enabled programmatically for a managed bot?
3. Exact shape of the `managed_bot` / `ManagedBotUpdated` payload and
   `getManagedBotToken` parameters (typed PTB support may lag; we call raw).
4. `can_reply` rights mapping across Bot API versions (defensive read exists).
