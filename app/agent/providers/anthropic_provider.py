"""Anthropic (Claude) provider.

Degrades gracefully so a placeholder — never a dropped message — is the worst
case. Returns a safe placeholder draft (with estimated token counts) when no
ANTHROPIC_API_KEY is set, when the SDK isn't installed, when the API call fails
(rate limit, overload, network), or when the model returns no text. A placeholder
is flagged ``placeholder=True`` so the handler escalates it to the owner instead
of auto-sending it — the same graceful-degradation contract the CLI provider
honours.

Transient failures (rate limit, overload, 5xx, connection, timeout) are retried
a few times with exponential backoff before that fallback, so a brief blip
recovers silently instead of pinging the owner. Non-transient errors (auth, bad
request, model-not-found) never recover, so they escalate immediately. The retry
sleeps are blocking, which is fine: ``complete()`` is always called off the event
loop via ``asyncio.to_thread``.
"""

from __future__ import annotations

import logging
import time

from app.agent.providers.base import Completion
from app.config import settings

log = logging.getLogger(__name__)

_MAX_TOKENS = 300

# Retry policy for transient API failures. _MAX_ATTEMPTS includes the first try,
# so 3 = one initial call + two retries, sleeping 0.5s then 1.0s between them.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_S = 0.5

# HTTP statuses worth retrying: rate limit, request timeout/conflict, and 5xx
# (529 is Anthropic's "overloaded"). Everything else is a caller error.
_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})

_PLACEHOLDER_TEXT = "Thanks for your message! I've received it and will get back to you shortly."


def _estimate_tokens(text: str) -> int:
    # Rough heuristic (~4 chars/token) used only for the placeholder path.
    return max(1, len(text) // 4)


def _is_transient(exc: Exception) -> bool:
    """True for failures a retry might recover — without importing the SDK's
    exception classes (it is an optional dependency)."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS
    # Connection/timeout errors carry no HTTP status; classify by type name.
    name = type(exc).__name__
    return "Connection" in name or "Timeout" in name


def _placeholder(model: str, system: str, user: str) -> Completion:
    return Completion(
        text=_PLACEHOLDER_TEXT,
        model=model,
        input_tokens=_estimate_tokens(system + user),
        output_tokens=_estimate_tokens(_PLACEHOLDER_TEXT),
        placeholder=True,
    )


class AnthropicProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else settings.anthropic_api_key
        self._client = None
        if self._api_key:
            try:
                import anthropic  # imported lazily so the app runs without the dep

                self._client = anthropic.Anthropic(api_key=self._api_key)
            except Exception:  # pragma: no cover - defensive; keep demo alive
                self._client = None

    @property
    def live(self) -> bool:
        return self._client is not None

    def complete(self, system: str, user: str, model: str) -> Completion:
        if self._client is None:
            return _placeholder(model, system, user)

        resp = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = self._client.messages.create(
                    model=model,
                    max_tokens=_MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                break
            except Exception as exc:
                # A failed API call must not drop the contact's message: retry a
                # transient blip, then fall back to a placeholder the handler
                # escalates to the owner. Non-transient errors escalate at once.
                if not (_is_transient(exc) and attempt + 1 < _MAX_ATTEMPTS):
                    log.warning("Anthropic API call failed; escalating to owner", exc_info=True)
                    return _placeholder(model, system, user)
                delay = _BACKOFF_BASE_S * 2**attempt
                log.warning(
                    "Anthropic API call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    delay,
                    exc,
                )
                time.sleep(delay)

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            # Empty completion (refusal, non-text blocks): never send an empty
            # reply as the owner — escalate instead.
            log.warning("Anthropic returned no text; escalating to owner")
            return _placeholder(model, system, user)

        return Completion(
            text=text,
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            placeholder=False,
        )
