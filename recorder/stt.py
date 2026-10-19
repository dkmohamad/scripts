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

**Auth failures.** The SDK reports a 403 as "check API key permissions", even
when the real cause is an account with no credit, and wraps it in up to three
other SDK errors. An auth failure anywhere in the job (submit or poll) is
re-raised as a ``PermissionError`` naming the likely causes; any other failure
propagates unchanged. The 403 body is a bare nginx page, so the cause can't be
pinned.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from speechmatics.batch import (  # pyright: ignore[reportMissingTypeStubs]
    AsyncClient,
    AuthenticationError,
    FormatType,
    JobConfig,
    JobType,
    Model,
    Transcript,
    TranscriptionConfig,
)

from .lib import (
    SPEECHMATICS_KEY_FILE,
    SPEECHMATICS_LANG,
    SPEECHMATICS_MODEL,
    SPEECHMATICS_URL,
    get_speechmatics_key,
    log,
)

__all__ = ["transcribe_audio"]

# How often to log a "still transcribing" heartbeat while the batch job runs.
# The SDK polls Speechmatics silently, so without this a long job looks hung.
_HEARTBEAT_SECS = 30.0

# The SDK raises one AuthenticationError for both 401 and 403, distinguished
# only by message text; these phrases appear in its 401 and 403 messages.
_SDK_401_PHRASE = "Invalid API key"
_SDK_403_PHRASE = "Access forbidden"


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe an audio file with Speechmatics; return the transcript text.

    Runs the async batch job to completion: one mixed mono file in, a
    diarization-formatted transcript string out.

    Raises:
        PermissionError: If Speechmatics rejects the key or refuses the job
            (no credit, revoked key).
    """
    with _auth_errors_explained():
        return asyncio.run(_transcribe(audio_path))


async def _heartbeat(job_id: str, start: float) -> None:
    """Log periodic progress while a batch job runs.

    ``wait_for_completion`` polls Speechmatics silently, so a long job emits no
    output between submission and result and looks hung. This logs every
    ``_HEARTBEAT_SECS`` until cancelled.
    """
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(_HEARTBEAT_SECS)
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


@contextmanager
def _auth_errors_explained() -> Generator[None]:
    """Re-raise an SDK auth failure as a PermissionError naming likely causes.

    Catches broadly because the SDK wraps the auth error in a different type
    per call (BatchError on submit, JobError on poll); anything that isn't an
    auth failure re-raises unchanged.
    """
    try:
        yield
    except Exception as exc:
        failure = _auth_failure(exc)
        if failure is None:
            raise
        raise failure from exc


def _auth_failure(exc: BaseException) -> PermissionError | None:
    """Return a PermissionError naming likely causes, if ``exc`` is an auth failure.

    Walks ``exc``'s cause chain for the SDK's AuthenticationError; ``None`` means
    the failure isn't auth-related and should propagate unchanged.
    """
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, AuthenticationError):
            return PermissionError(_auth_reason(str(cause)))
        cause = cause.__cause__
    return None


def _auth_reason(sdk_message: str) -> str:
    """Translate the SDK's auth message into one naming the likely causes."""
    if _SDK_403_PHRASE in sdk_message:
        return (
            "Speechmatics refused the job (403). Check the account has credit "
            "in the Speechmatics portal, and that the key in "
            f"{SPEECHMATICS_KEY_FILE} is still active."
        )
    if _SDK_401_PHRASE in sdk_message:
        return (
            "Speechmatics rejected the API key (401). Check the key in "
            f"{SPEECHMATICS_KEY_FILE}."
        )
    return (
        f"Speechmatics auth failed ({sdk_message}). Check account credit and the "
        f"key in {SPEECHMATICS_KEY_FILE}."
    )
