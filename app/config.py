"""Runtime configuration, loaded from environment / .env.

No secret ever has a real default here — placeholders only — so the repo stays
safe to publish. Missing secrets degrade gracefully (see agent providers).
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    control_chat_id: int | None = None

    @field_validator("control_chat_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        # Treat an empty env var (e.g. `CONTROL_CHAT_ID=`) as unset.
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v

    # Storage
    store_backend: str = "sqlite"  # "sqlite" | "memory"
    sqlite_path: str = "data/clera.db"

    # Memory
    history_limit: int = 20  # messages of thread history included in a draft
    profile_refresh_every: int = 6  # rebuild a contact's profile every N messages

    # Collect-only mode: record every message (voice notes transcribed locally)
    # into history, but never call the LLM and never draft, reply, or escalate.
    # For building up per-contact memory before turning the secretary on.
    collect_only: bool = False

    # Automatic mode: echo each auto-sent reply to the owner's control chat so
    # they can see what the secretary is doing (visibility without approval).
    notify_auto_replies: bool = True

    # Never answer messages older than this (seconds) — queued backlog from
    # while the bot was offline is recorded as history but not replied to.
    # 0 disables the check.
    stale_after_seconds: int = 300

    # Local voice-note transcription (mlx-whisper model, fetched from HF on
    # first use). large-v3-turbo is fast on Apple Silicon and strong on Persian.
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"

    # Hour (local time, 0-23) at which the daily digest is sent to the owner.
    # Set to -1 to disable the scheduled digest (/digest still works on demand).
    digest_hour: int = 21

    # LLM providers
    # "auto" picks: Anthropic API if a key is set, else the Claude CLI if
    # installed, else a safe placeholder. Force one with "anthropic" or "cli".
    llm_provider: str = "auto"  # "auto" | "anthropic" | "cli"
    claude_cli_path: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Model tiers
    model_best: str = "claude-opus-4-8"
    model_fast: str = "claude-haiku-4-5-20251001"
    default_tier: str = "fast"  # "best" | "fast"

    # Metering: multiplier on raw provider token cost, used only to show an
    # informational per-draft estimate (no prepaid balance in the MVP).
    cost_markup: float = 2.5

    def model_for_tier(self, tier: str) -> str:
        return self.model_best if tier == "best" else self.model_fast


settings = Settings()
