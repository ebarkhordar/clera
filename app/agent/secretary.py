"""The secretary agent: draft a reply (with memory) and maintain contact profiles."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.prompts import (
    build_draft_system,
    build_draft_user,
    build_summary_system,
    build_summary_user,
    format_transcript,
)
from app.agent.providers.anthropic_provider import AnthropicProvider
from app.agent.providers.base import Completion, Provider
from app.agent.providers.claude_cli_provider import ClaudeCLIProvider
from app.billing.meter import Usage, price
from app.config import settings
from app.store.models import Message


@dataclass(frozen=True)
class DraftResult:
    text: str
    model: str
    cost_usd: float
    placeholder: bool
    # What the agent decided to do with the message (see prompts):
    #   "reply"  -> text is sent to the contact as the owner
    #   "silent" -> no reply warranted; text is empty
    #   "notify" -> owner must handle it personally; text is the note for the owner
    action: str = "reply"


def parse_action(raw: str) -> tuple[str, str]:
    """Split a completion into (action, text) per the [SILENT]/[NOTIFY] protocol."""
    text = raw.strip()
    if text.startswith("[SILENT]"):
        return "silent", ""
    if text.startswith("[NOTIFY]"):
        return "notify", text.removeprefix("[NOTIFY]").strip()
    return "reply", text


def _select_provider() -> Provider:
    """Choose the LLM backend per LLM_PROVIDER (see config)."""
    choice = settings.llm_provider
    if choice == "anthropic":
        return AnthropicProvider()
    if choice == "cli":
        return ClaudeCLIProvider()

    # auto: prefer an API key, then the Claude CLI, else placeholder (Anthropic).
    if settings.anthropic_api_key:
        return AnthropicProvider()
    cli = ClaudeCLIProvider()
    if cli.live:
        return cli
    return AnthropicProvider()


def _cost_of(completion: Completion) -> float:
    if completion.cost_usd is not None:
        return completion.cost_usd
    return price(
        Usage(
            model=completion.model,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )
    ).user_cost_usd


def draft_reply(
    history: list[Message],
    contact_name: str | None,
    profile: str,
    tone: str,
    tier: str,
) -> DraftResult:
    """Draft a reply that reads as the owner, using thread history + contact profile."""
    model = settings.model_for_tier(tier)
    provider = _select_provider()

    transcript = format_transcript(history, contact_name)
    completion = provider.complete(
        system=build_draft_system(tone, profile),
        user=build_draft_user(transcript),
        model=model,
    )
    action, text = parse_action(completion.text)
    return DraftResult(
        text=text,
        model=completion.model,
        cost_usd=_cost_of(completion),
        placeholder=completion.placeholder,
        action=action,
    )


def summarize_contact(
    history: list[Message],
    contact_name: str | None,
    existing_profile: str,
    tier: str,
) -> str | None:
    """Rebuild a contact's durable profile from recent history. None on failure."""
    provider = _select_provider()
    transcript = format_transcript(history, contact_name)
    completion = provider.complete(
        system=build_summary_system(),
        user=build_summary_user(existing_profile, transcript),
        model=settings.model_for_tier(tier),
    )
    if completion.placeholder or not completion.text.strip():
        return None
    return completion.text.strip()
