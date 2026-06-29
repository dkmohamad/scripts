"""Capture lifecycle states and the marker files that back them.

A recording and a post-recording pipeline are two lifecycle states, each backed
by its own marker file (``ACTIVE_FILE`` / ``PROCESSING_FILE``). Every state
hydrates itself from its marker (``load``), owns that marker's lifecycle
(``begin`` / ``advance`` / ``clear``), and renders itself (``__str__``), so
``status`` simply loads the live states and asks each to report — no per-state
branching.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from ..lib import (
    ACTIVE_FILE,
    MAX_DURATION_SECS,
    META_FILE,
    PROCESSING_FILE,
    human_duration,
    log,
    pid_alive,
)

__all__ = [
    "CaptureState",
    "IdleState",
    "ProcessingState",
    "RecorderStatus",
    "RecordingState",
    "Stage",
]


class Stage(StrEnum):
    """The ordered stages of the post-recording pipeline.

    Reported by ``status`` and written into the processing marker; values are
    the lowercase labels shown to the user.
    """

    STARTING = "starting"
    PREPROCESSING = "preprocessing"
    TRANSCRIBING = "transcribing"
    SUMMARISING = "summarising"
    COMPRESSING = "compressing"
    NOTION = "notion"


@dataclass(frozen=True)
class RecorderStatus:
    """Status of a started recording, reported by _record_meeting.sh on stdout.

    ``mic_pid`` is the single recorder PID (it owns the one mixed recording
    file). The rest describe the acoustic context the recording is running in.
    """

    mic_pid: int
    output_port: str
    headphones: bool
    aec: bool

    @classmethod
    def from_json(cls, raw: str) -> RecorderStatus:
        """Parse the script's JSON status line into a typed object.

        Every field is required: the recorder always emits them, so a missing
        key (or unparseable line) is a broken contract and is raised, not
        defaulted away.

        Args:
            raw: The JSON status line printed by ``_record_meeting.sh``.

        Returns:
            The parsed ``RecorderStatus``.

        Raises:
            ValueError: If the line is missing a field or is not valid JSON.
        """
        try:
            data = json.loads(raw)
            return cls(
                mic_pid=int(data["mic_pid"]),
                output_port=str(data["output_port"]),
                headphones=bool(data["headphones"]),
                aec=bool(data["aec"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"malformed recorder status from _record_meeting.sh: {raw!r}"
            ) from exc


class CaptureState(ABC):
    """A live capture lifecycle state, backed by a marker file.

    Each subclass hydrates itself from its own marker and renders itself, so
    ``status`` loads the live states and asks each to report.
    """

    @classmethod
    @abstractmethod
    def load(cls) -> CaptureState | None:
        """Return the state if its marker is present and live, else None."""

    @abstractmethod
    def __str__(self) -> str:
        """Return the multi-line, human-readable status text."""

    def report(self) -> None:
        """Log this state's status at info level."""
        log.info(str(self))


class IdleState(CaptureState):
    """Nothing recording and no pipeline running — the fallback state."""

    @classmethod
    def load(cls) -> IdleState:
        return cls()

    def __str__(self) -> str:
        return "Nothing in progress."


@dataclass(frozen=True)
class RecordingState(CaptureState):
    """An in-progress recording, backed by ``ACTIVE_FILE`` + ``.meta``."""

    session_dir: Path
    mic_pid: int
    start_epoch: int

    @classmethod
    def begin(
        cls, session_dir: Path, status: RecorderStatus
    ) -> RecordingState:
        """Persist the recording marker (``.meta`` + ``ACTIVE_FILE``).

        The single recorder PID (stored as ``MIC_PID``) owns the mixed
        recording file; stopping it finalises the file.
        """
        state = cls(
            session_dir=session_dir,
            mic_pid=status.mic_pid,
            start_epoch=int(time.time()),
        )
        _write_meta(
            session_dir,
            {
                "MIC_PID": str(state.mic_pid),
                "START_EPOCH": str(state.start_epoch),
            },
        )
        ACTIVE_FILE.write_text(str(session_dir))
        return state

    @classmethod
    def load(cls) -> RecordingState | None:
        session_dir = _active_session()
        if session_dir is None:
            return None
        meta = _read_meta(session_dir)
        return cls(
            session_dir=session_dir,
            mic_pid=int(meta["MIC_PID"]),
            start_epoch=int(meta["START_EPOCH"]),
        )

    def clear(self) -> None:
        """Remove the active-recording marker (the recording is finalised)."""
        ACTIVE_FILE.unlink(missing_ok=True)

    def __str__(self) -> str:
        duration = int(time.time()) - self.start_epoch
        mic_alive = "running" if pid_alive(self.mic_pid) else "dead"
        lines = [
            f"Recording in progress: {human_duration(duration)}",
            f"  Session: {self.session_dir}",
            f"  Mic:     pid {self.mic_pid} ({mic_alive})",
        ]
        remaining = MAX_DURATION_SECS - duration
        if remaining > 0:
            lines.append(f"  Auto-stop in: {human_duration(remaining)}")
        else:
            lines.append("  Past max duration")
        return "\n".join(lines)


@dataclass(frozen=True)
class ProcessingState(CaptureState):
    """An in-progress post-recording pipeline, backed by ``PROCESSING_FILE``.

    Recording has ``ACTIVE_FILE``; the pipeline that runs after it (transcribe →
    summarise → compress → Notion), and the one ``process`` runs on a downloaded
    note, has this. Without it ``status`` only sees recording and reports
    "nothing in progress" while the long pipeline is still working.
    """

    session_dir: Path
    pid: int
    stage: Stage
    start_epoch: int

    @classmethod
    def begin(cls, session_dir: Path) -> ProcessingState:
        """Persist a fresh processing marker for this worker and return it."""
        state = cls(
            session_dir=session_dir,
            pid=os.getpid(),
            stage=Stage.STARTING,
            start_epoch=int(time.time()),
        )
        state._write()
        return state

    @classmethod
    def load(cls) -> ProcessingState | None:
        try:
            return cls.from_json(PROCESSING_FILE.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def advance(self, stage: Stage) -> ProcessingState:
        """Persist a new marker at ``stage`` and return the updated state."""
        updated = replace(self, stage=stage)
        updated._write()
        return updated

    def clear(self) -> None:
        """Remove the processing marker (the pipeline has finished)."""
        PROCESSING_FILE.unlink(missing_ok=True)

    def to_json(self) -> str:
        return json.dumps(
            {
                "session_dir": str(self.session_dir),
                "pid": self.pid,
                "stage": self.stage.value,
                "start_epoch": self.start_epoch,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> ProcessingState:
        data = json.loads(raw)
        return cls(
            session_dir=Path(data["session_dir"]),
            pid=int(data["pid"]),
            stage=Stage(data["stage"]),
            start_epoch=int(data["start_epoch"]),
        )

    def report(self) -> None:
        """Log at info level, or warning when the worker has died."""
        emit = log.info if pid_alive(self.pid) else log.warning
        emit(str(self))

    def __str__(self) -> str:
        elapsed = human_duration(int(time.time()) - self.start_epoch)
        if pid_alive(self.pid):
            return (
                f"Processing in progress: {self.stage} ({elapsed})\n"
                f"  Session: {self.session_dir}\n"
                f"  Worker:  pid {self.pid} (running)"
            )
        return (
            f"Processing marker present but worker pid {self.pid} "
            f"is dead (stage={self.stage}, likely crashed).\n"
            f"  Session: {self.session_dir}\n"
            f"  Stale marker: {PROCESSING_FILE}"
        )

    def _write(self) -> None:
        PROCESSING_FILE.write_text(self.to_json())


def _read_meta(session_dir: Path) -> dict[str, str]:
    meta_path = session_dir / META_FILE
    meta: dict[str, str] = {}
    for line in meta_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        meta[key.strip()] = value.strip()
    return meta


def _write_meta(session_dir: Path, meta: dict[str, str]) -> None:
    meta_path = session_dir / META_FILE
    with meta_path.open("w") as f:
        for key, value in meta.items():
            f.write(f"{key}={value}\n")


def _active_session() -> Path | None:
    if not ACTIVE_FILE.exists():
        return None
    path = Path(ACTIVE_FILE.read_text().strip())
    if path.is_dir() and (path / META_FILE).exists():
        return path
    return None
