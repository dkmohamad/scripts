#!/usr/bin/env python3
"""Tests for the transcript consolidation pipeline.

Plain asserts, no test framework. Run directly:

    python -m recorder.tests.test_consolidate

Three checks:

1. test_invariants - properties that must hold for any recording, with no
   reimplementation of the merge rule (so it can't go circular): all spoken
   text is preserved in order, timestamps are monotonic, and no line is empty.
2. test_real_regression - pins the exact rendered output for a captured raw
   whisper transcript (test-monologue) so formatting changes are caught.
3. test_merge_golden - a tiny synthetic transcript with hand-built gaps either
   side of the threshold, with a hand-written expected output. This is the
   only check that actually exercises the merge decision, because the real
   fixture happens to contain just one (long) pause.
"""

from pathlib import Path

from recorder.lib import MERGE_GAP_SECS
from recorder.transcribe import (
    Segment,
    segments_from_csv,
)

FIXTURES = Path(__file__).parent / "fixtures"
RAW_CSV = FIXTURES / "test-monologue.csv"
EXPECTED = FIXTURES / "test-monologue.expected.txt"


def run_pipeline(raw: list[Segment]) -> list[str]:
    """Run raw segments through the real consolidation pipeline."""
    merged = Segment.consolidate(raw, MERGE_GAP_SECS)
    return [str(s) for s in merged]


def test_invariants() -> None:
    """Properties that hold for any input, without reimplementing the rule."""
    raw = segments_from_csv(RAW_CSV)
    merged = Segment.consolidate(raw, MERGE_GAP_SECS)
    lines = run_pipeline(raw)

    # Every spoken word survives, in order: consolidation only joins, it never
    # drops, duplicates, or reorders text.
    raw_words = " ".join(s.transcript for s in raw).split()
    out_words = " ".join(s.transcript for s in merged).split()
    assert out_words == raw_words, "consolidation altered the spoken text"

    # Segments stay time-ordered and each spans a non-negative duration.
    for a, b in zip(merged, merged[1:], strict=False):
        assert a.start <= b.start, "segments out of chronological order"
    for s in merged:
        assert s.end >= s.start, f"segment ends before it starts: {s!r}"

    # Every output line carries text; merging never yields fewer lines than 1.
    assert lines, "no output produced"
    assert all(line.strip() for line in lines), "blank output line"

    print("test_invariants: OK")


def test_real_regression() -> None:
    """The rendered transcript matches the committed golden output."""
    raw = segments_from_csv(RAW_CSV)
    got = "\n".join(run_pipeline(raw)) + "\n"
    want = EXPECTED.read_text()
    assert got == want, (
        "output drifted from golden file; if intentional, regenerate "
        f"{EXPECTED.name}"
    )
    print("test_real_regression: OK")


def test_merge_golden() -> None:
    """Synthetic gaps either side of the threshold merge as expected.

    Timeline (seconds), with MERGE_GAP_SECS = 0.7:
        [0.0-1.0] "one"      gap 0.3  -> merged   (< 0.7)
        [1.3-2.0] "two"      gap 1.0  -> new line (>= 0.7)
        [3.0-4.0] "three"
    """
    raw = [
        Segment(0.0, 1.0, "one"),
        Segment(1.3, 2.0, "two"),
        Segment(3.0, 4.0, "three"),
    ]
    assert run_pipeline(raw) == ["one two", "three"], run_pipeline(raw)
    print("test_merge_golden: OK")


def main() -> None:
    """Run all checks."""
    test_invariants()
    test_real_regression()
    test_merge_golden()
    print("\nall tests passed")


if __name__ == "__main__":
    main()
