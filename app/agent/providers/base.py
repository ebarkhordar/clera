"""Provider abstraction so we can swap/add LLM backends (Claude, GPT, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    placeholder: bool = False  # True when generated without a real API key
    cost_usd: float | None = None  # provider-reported real cost, if available


class Provider(Protocol):
    """Minimal contract every LLM backend must implement."""

    def complete(self, system: str, user: str, model: str) -> Completion: ...
