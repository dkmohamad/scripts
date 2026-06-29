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
    FormatType,
    JobConfig,
    JobType,
    Model,
    Transcript,
    TranscriptionConfig,
)

from .lib import (
    SPEECHMATICS_LANG,
    SPEECHMATICS_MODEL,
    SPEECHMATICS_URL,
    get_speechmatics_key,
    log,
)

__all__ = ["transcribe_audio"]

# How often to log a "still transcribing" heartbeat while the batch job runs.
# The SDK polls Speechmatics silently, so without this a long job looks hung.
HEARTBEAT_SECS = 30.0


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe an audio file with Speechmatics; return the transcript text.

    Runs the async batch job to completion: one mixed mono file in, a
    diarization-formatted transcript string out.
    """
    return asyncio.run(_transcribe(audio_path))


async def _heartbeat(job_id: str, start: float) -> None:
    """Log periodic progress while a batch job runs.

    ``wait_for_completion`` polls Speechmatics silently, so a long job emits no
    output between submission and result and looks hung. This logs every
    ``HEARTBEAT_SECS`` until cancelled.
    """
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(HEARTBEAT_SECS)
        elapsed = int(loop.time() - start)
        log.info(
            f"Speechmatics: still transcribing job {job_id} ({elapsed}s elapsed)"
        )


async def _transcribe(audio_path: Path) -> str:
    """Submit a diarized batch job and return the SDK-formatted transcript.

    Split into submit + wait (rather than the one-shot ``transcribe``) so we can
    log the job id and run a heartbeat while the job polls.
    """
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
        job = await client.submit_job(str(audio_path), config=config)
        log.info(f"Speechmatics: job {job.id} submitted; awaiting result")

        loop = asyncio.get_running_loop()
        heartbeat = asyncio.create_task(_heartbeat(job.id, loop.time()))
        try:
            result = await client.wait_for_completion(
                job.id, format_type=FormatType.JSON
            )
        finally:
            heartbeat.cancel()

    # JSON format yields a Transcript (not a preformatted str); fail loudly if
    # that assumption ever changes.
    if not isinstance(result, Transcript):
        raise TypeError("expected a Transcript from Speechmatics")
    return result.transcript_text
