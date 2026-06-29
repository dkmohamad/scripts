"""Post-recording pipeline: transcribe → summarise → compress → Notion.

Shared by ``capture stop`` (a mic + system recording) and ``capture process`` (a
voice note downloaded from Notion). The two differ only in the final Notion
step, which is injected as a ``NotionStep`` port — so the orchestration, the
processing-marker lifecycle, and the resilience boundary live here once.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from recorder.capture.state import ProcessingState, Stage
from recorder.lib import TRANSCRIPT_FILE, log, run
from recorder.preprocess import preprocess as preprocess_audio
from recorder.summarise import summarise
from recorder.transcribe import transcribe

RECORDER_DIR = Path(__file__).resolve().parent.parent
COMPRESS_SCRIPT = RECORDER_DIR / "_compress.sh"

# A single-operation port: given the session dir, publish its results to Notion.
type NotionStep = Callable[[Path], None]


def run_pipeline(
    session_dir: Path,
    audio_filename: str,
    *,
    cleanup: bool,
    skip_summary: bool,
    keep_wav: bool,
    notion_step: NotionStep | None,
) -> None:
    """Transcribe, summarise, compress, and publish one session.

    Owns the processing-marker lifecycle, the session-log handler, and the
    resilience boundary. A ``None`` ``notion_step`` skips publishing.

    Args:
        session_dir: The session directory holding the audio and outputs.
        audio_filename: Name of the audio file within ``session_dir``.
        cleanup: Denoise and normalise the audio before transcription.
        skip_summary: Produce the transcript but skip AI summarisation.
        keep_wav: Retain the original WAV alongside the compressed MP3.
        notion_step: Publishes results to Notion, or ``None`` to skip.

    Raises:
        SystemExit: With code 1 if any stage fails.
    """
    fh = _init_session_log(session_dir)
    proc = ProcessingState.begin(session_dir)
    try:
        if cleanup and (session_dir / audio_filename).exists():
            proc = proc.advance(Stage.PREPROCESSING)
            log.info("Preprocessing audio...")
            audio_filename = preprocess_audio(session_dir / audio_filename).name

        proc = proc.advance(Stage.TRANSCRIBING)
        log.info("Transcribing...")
        transcribe(session_dir, audio_filename)

        proc = proc.advance(Stage.SUMMARISING)
        _summarise(session_dir, skip=skip_summary)

        proc = proc.advance(Stage.COMPRESSING)
        _compress(session_dir, keep_wav=keep_wav)

        proc = _publish(session_dir, proc, notion_step)
    except Exception:
        log.exception("Pipeline failed")
        raise SystemExit(1) from None
    finally:
        proc.clear()
        _teardown_session_log(fh)

    log.info(f"All output in: {session_dir}")


def _summarise(session_dir: Path, *, skip: bool) -> None:
    """Summarise the transcript unless skipped or no transcript exists."""
    if skip:
        log.info("Skipped summary (--skip-summary).")
        return
    transcript = session_dir / TRANSCRIPT_FILE
    if transcript.exists():
        log.info("Summarising...")
        summarise(transcript)


def _compress(session_dir: Path, *, keep_wav: bool) -> None:
    """Compress the session's WAV files to MP3."""
    log.info("Compressing...")
    cmd = [str(COMPRESS_SCRIPT), str(session_dir)]
    if keep_wav:
        cmd.append("--keep-wav")
    run(cmd, check=False)


def _publish(
    session_dir: Path, proc: ProcessingState, notion_step: NotionStep | None
) -> ProcessingState:
    """Publish via the injected Notion step; return the (advanced) state.

    A ``None`` ``notion_step`` skips publishing and returns ``proc`` unchanged.
    """
    if notion_step is None:
        log.info("Skipped Notion (--skip-notion).")
        return proc
    proc = proc.advance(Stage.NOTION)
    log.info("Publishing to Notion...")
    notion_step(session_dir)
    return proc


def _init_session_log(session_dir: Path) -> logging.FileHandler:
    """Add a file handler so the pipeline also logs into the session dir."""
    fh = logging.FileHandler(session_dir / "capture.log")
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    log.addHandler(fh)
    return fh


def _teardown_session_log(fh: logging.FileHandler) -> None:
    log.removeHandler(fh)
    fh.close()
