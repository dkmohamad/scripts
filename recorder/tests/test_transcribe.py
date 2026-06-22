#!/usr/bin/env python3
"""Tests for the transcribe wiring (recorder.transcribe).

These exercise the file-handling guards only — no Speechmatics API call. The
transcript content itself is the SDK's job and is checked by live validation.
"""

from pathlib import Path

import pytest

from recorder.lib import TRANSCRIPT_FILE
from recorder.transcribe import transcribe


def test_skips_when_transcript_exists(tmp_path: Path) -> None:
    """An existing transcript short-circuits before any audio/API work."""
    (tmp_path / TRANSCRIPT_FILE).write_text("already here")
    transcribe(tmp_path, "recording.wav")  # no audio file present; must not call out
    assert (tmp_path / TRANSCRIPT_FILE).read_text() == "already here"


def test_missing_audio_raises(tmp_path: Path) -> None:
    """With no transcript yet, a missing audio file fails before the API call."""
    with pytest.raises(FileNotFoundError):
        transcribe(tmp_path, "missing.wav")
