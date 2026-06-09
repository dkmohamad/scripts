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
from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path

from recorder.lib import (
    MERGE_GAP_SECS,
    MIC_FILE,
    SCRIPTS_ROOT,
    SYS_FILE,
    TRANSCRIPT_FILE,
    log,
    run,
)

TRANSCRIBE_SH = SCRIPTS_ROOT / "transcribe" / "transcribe.sh"


@total_ordering
@dataclass
class Segment:
    """A single transcribed segment.

    Times are in seconds: *start* and *end* are the speech boundaries
    reported by whisper.
    """

    start: float
    end: float
    transcript: str
    label: str = ""

    def __lt__(self, other: "Segment") -> bool:
        return self.start < other.start

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Segment):
            return NotImplemented
        return self.start == other.start

    def __add__(self, other: "Segment") -> "Segment":
        """Combine two segments.

        Spans from this segment's start to *other*'s end and
        concatenates text. Preserves the subtype of the left operand.
        """
        text = f"{self.transcript} {other.transcript}"
        return type(self)(self.start, other.end, text)

    def __str__(self) -> str:
        if self.label:
            return f"[{self.label}] {self.transcript}"
        return self.transcript

    @classmethod
    def from_csv_row(
        cls, row: list[str]
    ) -> "Segment | None":
        """Parse a whisper ``-ocsv`` row into a Segment.

        Columns are ``start,end,text`` with times in milliseconds.
        Returns None for invalid or empty rows.
        """
        if len(row) < 3:
            return None
        text = (
            ",".join(row[2:]).strip().strip('"').strip()
        )
        if not text:
            return None
        return cls(float(row[0]) / 1000, float(row[1]) / 1000, text)

    @classmethod
    def consolidate(
        cls, segments: "list[Segment]", gap: float
    ) -> "list[Segment]":
        """Merge segments separated by less than *gap* seconds of silence.

        The silence between two segments is ``next.start - prev.end``.
        whisper's VAD emits back-to-back segments mid-sentence, so this
        stitches continuous speech back into sentences and only breaks
        where the speaker paused for at least *gap* seconds. All segments
        must match *cls*; raises TypeError if a segment of a different
        type is encountered.
        """
        if not segments:
            return []
        merged: list[Segment] = [segments[0]]
        for seg in segments:
            if not isinstance(seg, cls):
                raise TypeError(
                    f"expected {cls.__name__},"
                    f" got {type(seg).__name__}"
                )
        for seg in segments[1:]:
            if seg.start - merged[-1].end < gap:
                merged[-1] = merged[-1] + seg
            else:
                merged.append(seg)
        return merged


@dataclass
class YouSegment(Segment):
    """A segment spoken by you (mic track)."""

    label: str = "You"


@dataclass
class ThemSegment(Segment):
    """A segment spoken by them (system track)."""

    label: str = "Them"


def segments_from_csv(csv_path: Path) -> list[Segment]:
    """Parse a whisper ``-ocsv`` file into Segments sorted by start time."""
    segments: list[Segment] = []
    with csv_path.open(newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            seg = Segment.from_csv_row(row)
            if seg is not None:
                segments.append(seg)
    segments.sort()
    return segments


def transcribe_file(
    audio_path: Path,
) -> list[Segment]:
    """Run whisper on an audio file.

    Returns a list of (start_seconds, text) segments sorted
    by timestamp.
    """
    csv_path = audio_path.with_suffix(".csv")

    try:
        run(
            [
                str(TRANSCRIBE_SH),
                "--babel",
                "--csv",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        log.exception("whisper failed to transcribe")
        raise

    segments = segments_from_csv(csv_path)
    csv_path.unlink(missing_ok=True)
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

    mic = YouSegment.consolidate(
        [
            YouSegment(s.start, s.end, s.transcript)
            for s in transcribe_file(mic_file)
        ],
        MERGE_GAP_SECS,
    )
    sys_ = ThemSegment.consolidate(
        [
            ThemSegment(s.start, s.end, s.transcript)
            for s in transcribe_file(sys_file)
        ],
        MERGE_GAP_SECS,
    )

    rows = interleave_tracks(mic, sys_)

    _write_transcript(
        session_dir, [str(s) for s in rows]
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

    merged = Segment.consolidate(segments, MERGE_GAP_SECS)

    _write_transcript(
        session_dir, [str(s) for s in merged]
    )


def main() -> None:
    """CLI entry point for transcribe."""
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
