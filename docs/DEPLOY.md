# Deploying Clera

Clera is a single long-polling process — no public URL, no reverse proxy. What
matters in production is that exactly **one** instance runs (two pollers on one
token conflict; Clera refuses to start if `data/clera.lock` is held) and that it
**survives reboots**.

## macOS (launchd)

```bash
sed "s|CLERA_DIR|$PWD|g" deploy/com.clera.secretary.plist \
  > ~/Library/LaunchAgents/com.clera.secretary.plist
launchctl load ~/Library/LaunchAgents/com.clera.secretary.plist
```

- Logs: `tail -f data/clera.log`
- Stop: `launchctl unload ~/Library/LaunchAgents/com.clera.secretary.plist`
- Voice transcription works here (Apple Silicon): `pip install -r requirements-voice.txt`

## Linux (systemd)

```bash
sudo cp deploy/clera.service /etc/systemd/system/   # adjust paths/user inside first
sudo systemctl daemon-reload
sudo systemctl enable --now clera
journalctl -u clera -f
```

## Docker

```bash
docker build -t clera .
docker run -d --name clera --restart unless-stopped \
  --env-file .env -v clera-data:/clera/data clera
```

Note: local voice transcription (mlx-whisper) is Apple-Silicon-only, so inside
Docker voice notes are recorded without transcripts. Everything else works.

## Modes

| Env | Effect |
| --- | --- |
| *(default)* | Secretary active: automatic replies with escalation (or review mode per `/review`) |
| `COLLECT_ONLY=true` | Record every message, act on nothing, no LLM calls — memory-building phase |

Recommended rollout: run `COLLECT_ONLY=true` for a few days →
`python -m app.backfill` to build contact profiles from the history →
restart without the flag in review mode → `/auto` when you trust it.
