#!/usr/bin/env python3
"""Transcribe a recording session.

Core primitive: transcribe_file() runs whisper on any audio file
and returns timestamped segments.

Two modes build on it:
- transcribe_dialogue() — dual-track (mic + system),
  interleaved with speaker labels
- transcribe_monologue() — single file, plain text

Usage:
    transcribe.py <session_dir>
"""

import csv
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from recorder.lib import (
    MIC_FILE,
    SCRIPTS_ROOT,
    SYS_FILE,
    TRANSCRIPT_FILE,
    log,
)

TRANSCRIBE_SH = SCRIPTS_ROOT / "transcribe" / "transcribe.sh"


class Segment(NamedTuple):
    """A single transcribed line.

    Sorts by timestamp (first field), so a plain list.sort()
    orders segments chronologically.
    """

    timestamp: float
    transcript: str


def transcribe_file(
    audio_path: Path,
) -> list[Segment]:
    """Run whisper on an audio file.

    Returns a list of (start_seconds, text) segments sorted
    by timestamp.
    """
    csv_path = audio_path.with_suffix(".csv")

    subprocess.run(
        [
            str(TRANSCRIBE_SH),
            "--babel",
            "--csv",
            str(audio_path),
        ],
        check=True,
    )

    segments: list[Segment] = []
    with csv_path.open(newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 3:
                continue
            text = (
                ",".join(row[2:]).strip().strip('"').strip()
            )
            if not text:
                continue
            segments.append(
                Segment(float(row[0]), text)
            )

    csv_path.unlink(missing_ok=True)
    segments.sort()
    return segments


def interleave_tracks(
    *tracks: list[Segment],
) -> list[Segment]:
    """Interleave multiple tracks by timestamp.

    Each track is a list of Segments. Returns a single merged
    list sorted by timestamp.
    """
    merged: list[Segment] = []
    for segments in tracks:
        merged.extend(segments)
    merged.sort()
    return merged


def transcribe_dialogue(session_dir: Path) -> None:
    """Transcribe dual-track (mic + system) with speaker labels."""
    if _skip_if_done(session_dir):
        return

    mic_file, sys_file = _require_files(
        session_dir, MIC_FILE, SYS_FILE
    )

    log.info(f"Transcribing {session_dir.name}...")

    mic = [
        Segment(s.timestamp, f"[You] {s.transcript}")
        for s in transcribe_file(mic_file)
    ]
    sys_ = [
        Segment(s.timestamp, f"[Them] {s.transcript}")
        for s in transcribe_file(sys_file)
    ]

    rows = interleave_tracks(mic, sys_)

    _write_transcript(
        session_dir, [s.transcript for s in rows]
    )


def transcribe_monologue(
    session_dir: Path, audio_filename: str
) -> None:
    """Transcribe a single audio file as plain text."""
    if _skip_if_done(session_dir):
        return

    (audio_file,) = _require_files(
        session_dir, audio_filename
    )

    log.info(f"Transcribing {session_dir.name}...")

    segments = transcribe_file(audio_file)

    _write_transcript(
        session_dir,
        [s.transcript for s in segments],
    )


def main() -> None:
    if len(sys.argv) < 2:
        log.error("Usage: transcribe.py <session_dir>")
        sys.exit(1)

    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        log.error(f"'{session_dir}' is not a directory.")
        sys.exit(1)

    transcribe_dialogue(session_dir)


# --- Private helpers ---


def _require_files(
    session_dir: Path, *filenames: str
) -> list[Path]:
    """Resolve audio files, exiting if any are missing."""
    paths: list[Path] = []
    for name in filenames:
        p = session_dir / name
        if not p.exists():
            log.error(f"No {name} found in {session_dir}")
            sys.exit(1)
        paths.append(p)
    return paths


def _write_transcript(
    session_dir: Path, lines: list[str]
) -> None:
    """Write transcript lines and log the result."""
    transcript = session_dir / TRANSCRIPT_FILE
    with transcript.open("w") as f:
        for line in lines:
            f.write(f"{line}\n")
    log.info(
        f"Wrote {transcript} ({len(lines)} lines)"
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
