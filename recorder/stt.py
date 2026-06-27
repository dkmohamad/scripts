#!/usr/bin/env python3
"""Speechmatics batch speech-to-text engine.

This is the ASR engine seam: ``transcribe.py`` calls ``transcribe_audio``. The
``speechmatics-batch`` SDK submits a batch job with speaker diarization,
deserializes the json-v2 result into a typed ``Transcript``, and formats it; we
return its ``transcript_text``.

**Why Speechmatics.** Accurate diacritised Arabic plus language-agnostic speaker
diarization in one batch call; whisper.cpp (weak Arabic), Google STT (no Arabic
diarization), and pyannote/WhisperX (heavy torch + a gated HuggingFace token)
were rejected.

The SDK is async-only, so the public ``transcribe_audio`` wraps the async work
in ``asyncio.run`` for the otherwise-synchronous pipeline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from speechmatics.batch import (  # pyright: ignore[reportMissingTypeStubs]
    AsyncClient,
    JobConfig,
    JobType,
    Model,
    Transcript,
    TranscriptionConfig,
)

from recorder.lib import (
    SPEECHMATICS_LANG,
    SPEECHMATICS_MODEL,
    SPEECHMATICS_URL,
    get_speechmatics_key,
    log,
)


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe an audio file with Speechmatics; return the transcript text.

    Runs the async batch job to completion: one mixed mono file in, a
    diarization-formatted transcript string out.
    """
    return asyncio.run(_transcribe(audio_path))


async def _transcribe(audio_path: Path) -> str:
    """Submit a diarized batch job and return the SDK-formatted transcript."""
    config = JobConfig(
        type=JobType.TRANSCRIPTION,
        transcription_config=TranscriptionConfig(
            language=SPEECHMATICS_LANG,
            model=Model(SPEECHMATICS_MODEL),
            diarization="speaker",
        ),
    )

    log.info(
        f"Speechmatics: transcribing {audio_path.name} "
        f"(lang={SPEECHMATICS_LANG}, diarization=speaker)"
    )
    async with AsyncClient(
        api_key=get_speechmatics_key(), url=SPEECHMATICS_URL
    ) as client:
        result = await client.transcribe(str(audio_path), config=config)

    # transcribe() defaults to the JSON format, so result is a Transcript (not a
    # preformatted str); fail loudly if that assumption ever changes.
    if not isinstance(result, Transcript):
        raise TypeError("expected a Transcript from Speechmatics")
    return result.transcript_text
