"""Tests for the Anthropic provider's graceful-degradation contract.

The invariant the whole safety posture rests on: complete() must return a
placeholder (so the handler escalates to the owner) rather than raise or return
an empty reply — otherwise a contact's message is silently dropped, or an empty
message is sent as the owner.
"""

from types import SimpleNamespace

import app.agent.providers.anthropic_provider as provider_mod
from app.agent.providers.anthropic_provider import (
    _MAX_ATTEMPTS,
    _PLACEHOLDER_TEXT,
    AnthropicProvider,
)


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _status_error(status_code):
    """An exception that looks like an SDK APIStatusError (carries status_code)."""
    exc = RuntimeError(f"{status_code} error")
    exc.status_code = status_code
    return exc


def _ok(text="hi"):
    return SimpleNamespace(
        content=[_text_block(text)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


class _FakeMessages:
    def __init__(self, on_create):
        self._on_create = on_create

    def create(self, **kwargs):
        return self._on_create(**kwargs)


def _provider_with(on_create):
    """A provider forced into its live branch with a stubbed client."""
    provider = AnthropicProvider(api_key="sk-fake")
    provider._client = SimpleNamespace(messages=_FakeMessages(on_create))
    return provider


def test_no_client_returns_placeholder():
    provider = AnthropicProvider(api_key="")
    assert not provider.live
    result = provider.complete(system="s", user="u", model="claude-haiku-4-5-20251001")
    assert result.placeholder is True
    assert result.text == _PLACEHOLDER_TEXT


def test_successful_completion_reports_real_usage():
    def on_create(**kwargs):
        return SimpleNamespace(
            content=[_text_block("سلام!")],
            usage=SimpleNamespace(input_tokens=42, output_tokens=7),
        )

    result = _provider_with(on_create).complete(system="s", user="u", model="m")
    assert result.placeholder is False
    assert result.text == "سلام!"
    assert (result.input_tokens, result.output_tokens) == (42, 7)


def test_api_error_degrades_to_placeholder_not_raise():
    def on_create(**kwargs):
        raise RuntimeError("529 overloaded_error")

    # Must not raise — a transient failure escalates via a placeholder.
    result = _provider_with(on_create).complete(system="s", user="u", model="m")
    assert result.placeholder is True
    assert result.text == _PLACEHOLDER_TEXT


def test_empty_completion_degrades_to_placeholder():
    def on_create(**kwargs):
        return SimpleNamespace(
            content=[_text_block("   ")],  # whitespace/no text → nothing to send
            usage=SimpleNamespace(input_tokens=10, output_tokens=0),
        )

    result = _provider_with(on_create).complete(system="s", user="u", model="m")
    assert result.placeholder is True
    assert result.text == _PLACEHOLDER_TEXT


def test_transient_error_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(provider_mod.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def on_create(**kwargs):
        calls["n"] += 1
        if calls["n"] < _MAX_ATTEMPTS:
            raise _status_error(529)  # overloaded — recovers on the final try
        return _ok("recovered")

    result = _provider_with(on_create).complete(system="s", user="u", model="m")
    assert result.placeholder is False
    assert result.text == "recovered"
    assert calls["n"] == _MAX_ATTEMPTS


def test_transient_error_exhausts_retries_then_placeholder(monkeypatch):
    monkeypatch.setattr(provider_mod.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def on_create(**kwargs):
        calls["n"] += 1
        raise _status_error(429)  # keeps rate-limiting

    result = _provider_with(on_create).complete(system="s", user="u", model="m")
    assert result.placeholder is True
    assert calls["n"] == _MAX_ATTEMPTS  # tried every attempt before giving up


def test_non_transient_error_does_not_retry(monkeypatch):
    monkeypatch.setattr(provider_mod.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def on_create(**kwargs):
        calls["n"] += 1
        raise _status_error(400)  # bad request — retrying can't help

    result = _provider_with(on_create).complete(system="s", user="u", model="m")
    assert result.placeholder is True
    assert calls["n"] == 1  # escalated immediately, no retries
