"""Token metering: turn provider usage into a marked-up USD cost.

    raw_cost   = input_tokens * in_rate + output_tokens * out_rate   (per MTok)
    user_cost  = raw_cost * COST_MARKUP                              (your margin)

The markup is where the business makes money on resold tokens.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.billing.pricing import rate_for
from app.config import settings


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Charge:
    raw_cost_usd: float
    user_cost_usd: float
    markup: float


def price(usage: Usage, markup: float | None = None) -> Charge:
    markup = settings.cost_markup if markup is None else markup
    rate = rate_for(usage.model)
    raw = (
        usage.input_tokens / 1_000_000 * rate.input_per_mtok
        + usage.output_tokens / 1_000_000 * rate.output_per_mtok
    )
    return Charge(
        raw_cost_usd=round(raw, 6),
        user_cost_usd=round(raw * markup, 6),
        markup=markup,
    )
