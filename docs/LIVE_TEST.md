# Live test against a Telegram Premium account

This is the one step that can't be automated or done from CI: it needs a real
**Telegram Premium** account (Business mode is Premium-only) and manual taps in
the Telegram app. Budget ~10 minutes.

## What you'll need

- A **Telegram Premium** account (the "owner" whose chats the bot will handle).
- A **second** Telegram account (or a friend) to play the "contact" messaging you.
- A bot token from [@BotFather](https://t.me/BotFather).
- Optional: an `ANTHROPIC_API_KEY` for real drafts. Without it you'll get a
  fixed placeholder draft — still fine to validate the plumbing.

## 1. Configure

```bash
cp .env.example .env
# edit .env:
#   TELEGRAM_BOT_TOKEN=...        (from BotFather)
#   ANTHROPIC_API_KEY=...         (optional)
#   CONTROL_CHAT_ID=...           (your own numeric id, from @userinfobot; optional)
```

## 2. Pre-flight

```bash
python -m app.doctor
```

Expect a ✅ on the bot token. Fix any ❌ before continuing.

## 3. Connect the bot as your business chatbot

In the Telegram app on the **owner** (Premium) account:

1. **Settings → Business → Chatbots**.
2. Select your bot by username.
3. Grant **reply** permission and choose which chats it may access (start with
   "All chats" or a single test chat).

The moment you do this, Telegram sends a `business_connection` update.

## 4. Start the bot

```bash
python -m app.main
```

Watch the logs. On connection you should see:

```
INFO ... Business connection enabled: <id> (owner <your_id>)
```

and a "✅ Secretary connected" message in your control chat.

## 5. Trigger a draft

From the **second** account, send a normal DM to the owner account in a covered
chat, e.g. *"Hey, are you free for a call tomorrow at 3pm?"*

In your **control chat** you should get:

```
✉️ New message from a contact: Hey, are you free ...
🤖 Proposed reply (~$0.00xx, <model>): ...
[ ✅ Send ]  [ 🗑 Discard ]
```

## 6. Approve

Tap **✅ Send**. The reply should appear in the contact's chat **sent as you**
(not from the bot). The control message updates to "✅ Sent as you: …".

## What to capture for debugging

If something doesn't work, grab:

- the bot's stdout logs (they show which update arrived and any policy `IGNORE`
  reason),
- whether the `business_connection` log line appeared at all (if not, the
  chatbot isn't connected or `allowed_updates` didn't include `business_*`),
- the exact error text from any ❌.

## Known checkpoints / gotchas

- **No `business_connection` log on connect** → the app didn't receive the
  update. Confirm the bot is selected in Business → Chatbots and that
  `ALLOWED_UPDATES` in `app/main.py` includes the `business_*` types (it does by
  default).
- **Draft appears but ✅ Send fails** → usually missing reply permission
  (`can_reply`) or the chat wasn't active in the last 24h (Telegram's window for
  bot-initiated sends).
- **Reply comes from the bot, not "as you"** → the send didn't include
  `business_connection_id`; that shouldn't happen with the current code, so file
  it with logs.
- **`business_connection.rights` shape differs by library version** → the code
  reads `can_reply` defensively; if it logs `can_reply=False` unexpectedly on a
  connection you granted reply rights to, note your `python-telegram-bot`
  version so we can pin the field mapping.
