from app.billing.meter import Usage, price
from app.billing.pricing import rate_for


def test_price_applies_markup():
    usage = Usage(model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0)
    charge = price(usage, markup=2.0)
    rate = rate_for(usage.model)
    assert charge.raw_cost_usd == rate.input_per_mtok
    assert charge.user_cost_usd == rate.input_per_mtok * 2.0


def test_price_counts_input_and_output():
    usage = Usage(model="claude-opus-4-8", input_tokens=500_000, output_tokens=500_000)
    charge = price(usage, markup=1.0)
    rate = rate_for(usage.model)
    expected = 0.5 * rate.input_per_mtok + 0.5 * rate.output_per_mtok
    assert round(charge.raw_cost_usd, 6) == round(expected, 6)


def test_unknown_model_uses_fallback_not_crash():
    charge = price(Usage(model="totally-unknown", input_tokens=1000, output_tokens=1000))
    assert charge.user_cost_usd > 0
