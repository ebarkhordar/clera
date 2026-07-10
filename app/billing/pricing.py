"""Provider token pricing.

Rates are USD per 1,000,000 tokens (input / output). These are illustrative
defaults for the MVP demo — confirm against live provider pricing before
charging real money. Keyed by the exact model id we send to the provider.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    input_per_mtok: float
    output_per_mtok: float


# Illustrative — verify before production use.
RATES: dict[str, Rate] = {
    "claude-opus-4-8": Rate(input_per_mtok=5.00, output_per_mtok=25.00),
    "claude-haiku-4-5-20251001": Rate(input_per_mtok=1.00, output_per_mtok=5.00),
}

# Fallback so an unknown model never crashes metering (charge as best tier).
_FALLBACK = Rate(input_per_mtok=5.00, output_per_mtok=25.00)


def rate_for(model: str) -> Rate:
    return RATES.get(model, _FALLBACK)
