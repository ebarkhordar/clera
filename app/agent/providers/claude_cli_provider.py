"""Claude CLI provider.

Generates drafts by shelling out to the locally-installed `claude` CLI in
non-interactive print mode, using the user's existing Claude Code authentication
instead of an API key.

Notes:
- The CLI carries Claude Code's own (cached) system prompt, so reported token
  counts and cost include that baseline overhead — treat the per-draft cost as
  indicative, not a true marginal price.
- `complete()` blocks while the subprocess runs. Fine for single-user testing;
  a production build should run this off the event loop.
- Degrades to a safe placeholder if the CLI is missing or errors, so the app
  keeps working without any provider configured.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from app.agent.providers.base import Completion
from app.config import settings

_TIMEOUT_S = 120

_PLACEHOLDER_TEXT = "Thanks for your message! I've received it and will get back to you shortly."


def _model_alias(model: str) -> str:
    """Map a model id to a CLI --model alias (opus/sonnet/haiku), else pass through."""
    m = model.lower()
    for alias in ("opus", "sonnet", "haiku"):
        if alias in m:
            return alias
    return model


def _placeholder(model: str, system: str, user: str) -> Completion:
    return Completion(
        text=_PLACEHOLDER_TEXT,
        model=model,
        input_tokens=max(1, len(system + user) // 4),
        output_tokens=max(1, len(_PLACEHOLDER_TEXT) // 4),
        placeholder=True,
    )


class ClaudeCLIProvider:
    def __init__(self, cli_path: str | None = None) -> None:
        self._cli = cli_path or settings.claude_cli_path

    @property
    def live(self) -> bool:
        return shutil.which(self._cli) is not None

    def complete(self, system: str, user: str, model: str) -> Completion:
        if not self.live:
            return _placeholder(model, system, user)

        try:
            proc = subprocess.run(
                [
                    self._cli,
                    "-p",
                    user,
                    "--append-system-prompt",
                    system,
                    "--model",
                    _model_alias(model),
                    "--output-format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
            )
        except (subprocess.TimeoutExpired, OSError):
            return _placeholder(model, system, user)

        if proc.returncode != 0 or not proc.stdout.strip():
            return _placeholder(model, system, user)

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return _placeholder(model, system, user)

        if data.get("is_error"):
            return _placeholder(model, system, user)

        text = (data.get("result") or "").strip()
        if not text:
            return _placeholder(model, system, user)

        usage = data.get("usage") or {}
        return Completion(
            text=text,
            model=model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=data.get("total_cost_usd"),
            placeholder=False,
        )
