#!/usr/bin/env python3
"""Transcribe a recording into a transcript file.

A session has one audio file (a meeting is mixed to mono at capture, a phone
note already is one file). We hand it to the Speechmatics engine
(``recorder.stt``), which returns a diarization-formatted transcript, and write
that to ``transcript.txt``.

Usage:
    transcribe.py <session_dir>
"""

import sys
from pathlib import Path

from .lib import RECORDING_FILE, TRANSCRIPT_FILE, log

__all__ = ["main", "transcribe"]


def transcribe(session_dir: Path, audio_filename: str) -> None:
    """Transcribe one audio file and write its transcript."""
    if _skip_if_done(session_dir):
        return

    (audio_file,) = _require_files(session_dir, audio_filename)

    log.info(f"Transcribing {session_dir.name}...")

    # Lazy import so the heavy SDK only loads when we actually transcribe.
    from . import stt  # noqa: PLC0415

    text = stt.transcribe_audio(audio_file)
    _write_transcript(session_dir, text)


def main() -> None:
    """CLI entry point for transcribe."""
    if len(sys.argv) < 2:
        log.error("Usage: transcribe.py <session_dir>")
        sys.exit(1)

    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        log.error(f"'{session_dir}' is not a directory.")
        sys.exit(1)

    transcribe(session_dir, RECORDING_FILE)


# --- Private helpers ---


def _require_files(
    session_dir: Path, *filenames: str
) -> list[Path]:
    """Resolve audio files, raising if any are missing."""
    paths: list[Path] = []
    for name in filenames:
        p = session_dir / name
        if not p.exists():
            raise FileNotFoundError(
                f"No {name} found in {session_dir}"
            )
        paths.append(p)
    return paths


def _write_transcript(session_dir: Path, text: str) -> None:
    """Write the transcript text and log the result."""
    transcript = session_dir / TRANSCRIPT_FILE
    transcript.write_text(text)
    log.info(
        f"Wrote {transcript} ({len(text.splitlines())} lines)"
    )


def _skip_if_done(session_dir: Path) -> bool:
    """Return True (and log) if a transcript already exists."""
    if (session_dir / TRANSCRIPT_FILE).exists():
        log.info(
            f"Skipping {session_dir.name} (transcript exists)"
        )
        return True
    return False


if __name__ == "__main__":
    main()
