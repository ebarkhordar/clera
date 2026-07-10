"""Voice-note transcription (local, no API key).

Uses mlx-whisper on Apple Silicon. Telegram voice notes are OGG/Opus; whisper's
loader shells out to ffmpeg, which may not be installed, so we fall back to
decoding with soundfile + resampling with scipy (both pure pip installs).

The model is fetched from Hugging Face on first use and cached locally.
Transcription is CPU/GPU-bound and blocking — call it via ``asyncio.to_thread``.
Returns None when transcription is unavailable or fails; callers must treat a
missing transcript as "we could not read this message", never as silence.
"""

from __future__ import annotations

import logging
import shutil

from app.config import settings

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000  # whisper's expected input


def available() -> bool:
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _load_audio(path: str):
    """Decode an audio file to 16 kHz mono float32 without requiring ffmpeg."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != _SAMPLE_RATE:
        mono = resample_poly(mono, _SAMPLE_RATE, rate).astype(np.float32)
    return mono


def transcribe(path: str) -> str | None:
    """Transcribe an audio file to text. None if unsupported or failed."""
    if not available():
        log.warning("mlx-whisper not installed; cannot transcribe %s", path)
        return None
    try:
        import mlx_whisper

        # Prefer whisper's own loader when ffmpeg exists (handles any codec);
        # otherwise decode ourselves via soundfile.
        audio = path if shutil.which("ffmpeg") else _load_audio(path)
        result = mlx_whisper.transcribe(audio, path_or_hf_repo=settings.whisper_model)
        text = (result.get("text") or "").strip()
        return text or None
    except Exception:
        log.exception("Transcription failed for %s", path)
        return None
