"""The recording-session value object.

A ``Session`` is the text a recording produces (title, transcript, summary) plus
its derived metadata (audio duration, recording time). It is a pure domain
object: it knows how to load itself from a session directory, but nothing about
how it is published — that mapping lives in :mod:`recorder.notion`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .lib import SUMMARY_FILE, TITLE_FILE, TRANSCRIPT_FILE, run

__all__ = ["Session"]

_DEFAULT_TITLE = "Untitled Recording"
_AUDIO_SUFFIXES = (".m4a", ".mp3", ".wav", ".ogg", ".opus")


@dataclass(frozen=True)
class Session:
    """A recording session's artifacts and derived metadata."""

    session_dir: Path
    title: str
    transcript: str
    summary: str
    duration_minutes: int | None
    recorded_at: datetime | None

    @classmethod
    def load(
        cls,
        session_dir: Path,
        *,
        recorded_at: datetime | None = None,
    ) -> Session:
        """Load a session's text artifacts and audio duration from disk.

        Args:
            session_dir: The session directory holding the artifacts.
            recorded_at: When the recording was made, if known — the caller
                derives it from the meeting dirname or the source filename.

        Returns:
            The populated ``Session``.
        """
        return cls(
            session_dir=session_dir,
            title=_read_text(session_dir / TITLE_FILE) or _DEFAULT_TITLE,
            transcript=_read_text(session_dir / TRANSCRIPT_FILE),
            summary=_read_text(session_dir / SUMMARY_FILE),
            duration_minutes=_audio_duration_minutes(session_dir),
            recorded_at=recorded_at,
        )


def _read_text(path: Path) -> str:
    """Return the stripped contents of ``path``, or "" if it is absent."""
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def _audio_duration_minutes(session_dir: Path) -> int | None:
    """Return the session audio's duration in minutes via ffprobe.

    Returns ``None`` when the session has no audio file — a legitimate unknown
    (e.g. a transcript-only reprocess), distinct from a real zero. A genuine
    ffprobe failure on a present file propagates to the caller's boundary.
    """
    audio = _find_audio(session_dir)
    if audio is None:
        return None
    result = run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(audio),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return round(float(data["format"]["duration"]) / 60)


def _find_audio(session_dir: Path) -> Path | None:
    """Return the first audio file in ``session_dir`` (sorted), or None."""
    for path in sorted(session_dir.iterdir()):
        if (
            path.is_file()
            and not path.name.startswith(".")
            and path.suffix in _AUDIO_SUFFIXES
        ):
            return path
    return None
