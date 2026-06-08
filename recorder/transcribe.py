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

from recorder.lib import (
    MIC_FILE,
    SCRIPTS_ROOT,
    SYS_FILE,
    TRANSCRIPT_FILE,
    log_info,
)

TRANSCRIBE_SH = SCRIPTS_ROOT / "transcribe" / "transcribe.sh"


def transcribe_file(
    audio_path: Path,
) -> list[tuple[float, str]]:
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

    segments: list[tuple[float, str]] = []
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
            start = float(row[0])
            segments.append((start, text))

    csv_path.unlink(missing_ok=True)
    segments.sort(key=lambda r: r[0])
    return segments


def interleave_tracks(
    *tracks: tuple[str, list[tuple[float, str]]],
) -> list[tuple[float, str, str]]:
    """Interleave multiple labelled tracks by timestamp.

    Each track is (label, segments) where segments come from
    transcribe_file(). Returns (start, label, text) sorted by
    timestamp.
    """
    rows: list[tuple[float, str, str]] = []
    for label, segments in tracks:
        for start, text in segments:
            rows.append((start, label, text))
    rows.sort(key=lambda r: r[0])
    return rows


def transcribe_dialogue(session_dir: Path) -> None:
    """Transcribe dual-track (mic + system) with speaker labels."""
    mic_file = session_dir / MIC_FILE
    sys_file = session_dir / SYS_FILE
    transcript = session_dir / TRANSCRIPT_FILE

    if not mic_file.exists():
        print(
            f"No {MIC_FILE} found in {session_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    if transcript.exists():
        print(
            f"Skipping {session_dir.name} (transcript exists)"
        )
        return

    print(f"Transcribing {session_dir.name}...")
    log_info(f"Transcribing {session_dir}")

    if not sys_file.exists():
        print(
            f"Warning: no {SYS_FILE} in {session_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    mic_segments = transcribe_file(mic_file)
    sys_segments = transcribe_file(sys_file)

    rows = interleave_tracks(
        ("[You]", mic_segments),
        ("[Them]", sys_segments),
    )

    with transcript.open("w") as f:
        for _, label, text in rows:
            f.write(f"{label} {text}\n")

    line_count = len(transcript.read_text().splitlines())
    print(f"Wrote {transcript} ({line_count} lines)")
    log_info(
        f"Transcript written: {transcript} "
        f"({line_count} lines)"
    )



def transcribe_monologue(
    session_dir: Path, audio_filename: str
) -> None:
    """Transcribe a single audio file as plain text."""
    audio_file = session_dir / audio_filename
    transcript = session_dir / TRANSCRIPT_FILE

    if not audio_file.exists():
        print(
            f"No {audio_filename} found in {session_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    if transcript.exists():
        print(
            f"Skipping {session_dir.name} (transcript exists)"
        )
        return

    print(f"Transcribing {session_dir.name}...")
    log_info(f"Transcribing {session_dir}")

    segments = transcribe_file(audio_file)

    with transcript.open("w") as f:
        for _, text in segments:
            f.write(f"{text}\n")

    line_count = len(transcript.read_text().splitlines())
    print(f"Wrote {transcript} ({line_count} lines)")
    log_info(
        f"Transcript written: {transcript} "
        f"({line_count} lines)"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: transcribe.py <session_dir>",
            file=sys.stderr,
        )
        sys.exit(1)

    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        print(
            f"Error: '{session_dir}' is not a directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    transcribe_dialogue(session_dir)


if __name__ == "__main__":
    main()

