# Launch kit

Working drafts for the v0.1.0 public launch. Edit freely — the voice should be
the maintainer's, not a press release.

## GitHub Release notes (paste when creating the v0.1.0 release from the tag)

```markdown
## Clera v0.1.0 — your Telegram answers itself

First public release. Clera connects to your personal Telegram via the official
Business API and answers your real chats in your voice — replying, staying
silent, or escalating to you when a message needs money, commitments, or facts
only you know.

### Highlights
- **Three-way decision protocol** (reply / silent / escalate) instead of naive auto-reply
- **Per-contact memory**: full thread history, LLM-maintained profiles, and real
  exchange pairs mined as voice ground truth per contact
- **Hears and sees**: local voice transcription (mlx-whisper), photo description
- **Import years of history** from a Telegram Desktop export in one command
- **Owner control from Telegram**: /status /auto /review /pause /mute + daily digest
- **Staged rollout**: collect-only → backfill → review-every-draft → automatic
- **Deploy anywhere**: Docker, launchd, systemd; single-instance lock
- **Try without anything**: `python -m app.demo` — no bot, no Premium, no API key

61 tests, MIT licensed. Thanks @AmirF194 for the first outside contribution (#1).
```

## Show HN

**Title:** Show HN: Clera – an AI secretary that answers your Telegram in your voice

**Body:**

I message in Persian with my family, formally with my doctor, and in slang with
my friends. For the last month a bot has been answering some of those chats as
me — and the people on the other side haven't noticed.

Clera connects to a personal Telegram account through the official Business
API (no userbot, no ToS games). For each incoming message it makes a three-way
decision: reply in my voice, stay silent, or escalate to me. The escalation is
the important part — it refuses to guess about money, commitments, or facts it
doesn't know, and pings me privately instead. My girlfriend's "can you send me
the money for the backpack?" went to me; the "what time is the BBQ?" got
answered.

What made it work was memory, not model tricks: it records every covered chat
(voice notes transcribed locally with whisper), keeps an LLM-maintained profile
per contact, and mines real exchange pairs from each thread as ground-truth
style examples. You can also import your entire Telegram Desktop export so it
starts with years of your actual voice.

Rollout is staged so you can build trust: collect-only (no LLM calls at all) →
profile backfill → review mode (every reply needs your tap) → automatic with a
daily digest of everything it did.

Try the pipeline with zero setup — `python -m app.demo` needs no bot, no
Telegram Premium, no API key.

Honest caveats: needs Telegram Premium for the Business API; replies use
Claude, so automatic mode costs per message; local voice transcription is
Apple-Silicon-only right now (Linux archives audio); and storing your own
chats is inherently sensitive — everything stays in a local SQLite file, but
read the Privacy section before running it.

MIT licensed. https://github.com/ebarkhordar/clera

## r/selfhosted

**Title:** Clera: self-hosted AI secretary for Telegram — answers your real chats in your voice, escalates what it shouldn't answer

**Body:** (shorter variant of the HN body; lead with self-host angle: single
long-polling process, no public URL, SQLite file you own, Docker/systemd/launchd
recipes, nothing leaves your machine except LLM prompts.)

## Checklist before posting

- [ ] Create the v0.1.0 GitHub Release (tag is pushed; notes above)
- [ ] Repo description + topics set (done earlier)
- [ ] Settings → Actions → allow fork PR workflows (so contributor CI runs)
- [ ] Enable GitHub Discussions
- [ ] Record the demo GIF: `python -m app.demo --script` in a clean terminal
      (asciinema or a screen recording), embed at the top of the README
- [ ] Uncheck Releases/Deployments/Packages "include in home page" → re-check
      Releases once v0.1.0 exists
```
