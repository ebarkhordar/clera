"""Anthropic (Claude) provider.

Degrades gracefully: if no ANTHROPIC_API_KEY is set (or the SDK isn't installed),
returns a safe placeholder draft with estimated token counts so the whole app
runs end-to-end without any secret — important for a public repo demo.
"""

from __future__ import annotations

from app.agent.providers.base import Completion
from app.config import settings

_MAX_TOKENS = 300


def _estimate_tokens(text: str) -> int:
    # Rough heuristic (~4 chars/token) used only for the placeholder path.
    return max(1, len(text) // 4)


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
            text = "Thanks for your message! I've received it and will get back to you shortly."
            return Completion(
                text=text,
                model=model,
                input_tokens=_estimate_tokens(system + user),
                output_tokens=_estimate_tokens(text),
                placeholder=True,
            )

        resp = self._client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        return Completion(
            text=text,
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            placeholder=False,
        )
