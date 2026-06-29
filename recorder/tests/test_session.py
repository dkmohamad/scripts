"""Tests for the Session value object."""

from pathlib import Path

from recorder.lib import SUMMARY_FILE, TITLE_FILE, TRANSCRIPT_FILE
from recorder.session import Session


def test_load_should_read_artifacts_and_default_the_title(
    tmp_path: Path,
) -> None:
    """Session.load reads the text artifacts and defaults a missing title.

    Write a transcript and summary but no title file, load the session, and
    assert the artifacts are read while the title falls back to the default.
    Guards the contract that a session is publishable even without a generated
    title.
    """
    (tmp_path / TRANSCRIPT_FILE).write_text("hello transcript\n")
    (tmp_path / SUMMARY_FILE).write_text("the summary\n")

    session = Session.load(tmp_path)

    assert session.transcript == "hello transcript"
    assert session.summary == "the summary"
    assert session.title == "Untitled Recording"


def test_load_should_report_unknown_duration_without_audio(
    tmp_path: Path,
) -> None:
    """Session.load yields duration_minutes None when no audio file exists.

    Load a session dir containing only text and assert the duration is None (a
    legitimate unknown), not a colliding 0. Guards the EAFP fix that
    distinguishes 'no audio' from a real zero-minute duration.
    """
    (tmp_path / TITLE_FILE).write_text("Title\n")

    session = Session.load(tmp_path)

    assert session.duration_minutes is None
