#!/usr/bin/env python3
"""Transcribe a recording session.

Given a session directory containing mic.wav (and optionally
system.wav), produces a transcript.txt file. Dual-track sessions
get speaker-labelled output; solo sessions get plain text.

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


def merge_csvs(
    mic_csv: Path, sys_csv: Path, transcript: Path
) -> None:
    """Merge two whisper CSV files into a speaker-labelled
    transcript."""
    rows: list[tuple[float, str, str]] = []

    for csv_path, label in [
        (mic_csv, "[You]"),
        (sys_csv, "[Them]"),
    ]:
        with csv_path.open(newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) < 3:
                    continue
                text = ",".join(row[2:]).strip().strip('"').strip()
                if not text:
                    continue
                start = float(row[0])
                rows.append((start, label, text))

    rows.sort(key=lambda r: r[0])

    with transcript.open("w") as f:
        for _, label, text in rows:
            f.write(f"{label} {text}\n")


def transcribe_one(session_dir: Path) -> None:
    """Transcribe a single session directory."""
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
        print(f"Skipping {session_dir.name} (transcript exists)")
        return

    print(f"Transcribing {session_dir.name}...")
    log_info(f"Transcribing {session_dir}")

    if sys_file.exists():
        mic_csv = session_dir / "mic.csv"
        sys_csv = session_dir / "system.csv"

        subprocess.run(
            [
                str(TRANSCRIBE_SH),
                "--babel",
                "--csv",
                str(mic_file),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(TRANSCRIBE_SH),
                "--babel",
                "--csv",
                str(sys_file),
            ],
            check=True,
        )

        merge_csvs(mic_csv, sys_csv, transcript)

        mic_csv.unlink(missing_ok=True)
        sys_csv.unlink(missing_ok=True)
    else:
        result = subprocess.run(
            [str(TRANSCRIBE_SH), "--babel", str(mic_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        transcript.write_text(result.stdout)

    line_count = len(transcript.read_text().splitlines())
    print(f"Wrote {transcript} ({line_count} lines)")
    log_info(
        f"Transcript written: {transcript} ({line_count} lines)"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: transcribe.py <session_dir>", file=sys.stderr
        )
        sys.exit(1)

    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        print(
            f"Error: '{session_dir}' is not a directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    transcribe_one(session_dir)


if __name__ == "__main__":
    main()
