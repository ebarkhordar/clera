"""Image description, so photo messages aren't invisible to the secretary.

Uses the Anthropic API's vision support when a key is configured. Without a
key we record the photo's existence and caption only — never a made-up
description. Blocking; call via ``asyncio.to_thread``.
"""

from __future__ import annotations

import base64
import logging

from app.config import settings

log = logging.getLogger(__name__)

_PROMPT = (
    "Describe this image in one or two short sentences for a chat transcript, "
    "in the same language the surrounding conversation would use. Factual only."
)


def available() -> bool:
    return bool(settings.anthropic_api_key)


def describe(path: str) -> str | None:
    """One-line description of the image, or None when unavailable/failed."""
    if not available():
        return None
    try:
        import anthropic

        with open(path, "rb") as fh:
            data = base64.standard_b64encode(fh.read()).decode()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.model_for_tier("fast"),
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": data,
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return text or None
    except Exception:
        log.exception("Image description failed for %s", path)
        return None
