#!/usr/bin/env python3
"""Unified capture CLI for the recorder pipeline.

Manages the full lifecycle: start recording, check status, stop +
transcribe + summarise + compress + push to Notion. Always records
dual-track (mic + system).

Also supports processing pre-recorded voice notes from Notion.

Usage:
    capture start
    capture status
    capture stop [--cleanup] [--skip-summary] [--skip-notion] [--keep-wav]
    capture process <page> [--cleanup] [--skip-summary] [--skip-notion]
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from recorder._notion_fetch import (
    download_file,
    extract_page_id,
    fetch_audio_block,
    parse_recording_datetime,
)
from recorder._notion_update import update_notion_page
from recorder.lib import (
    ACTIVE_FILE,
    MAX_DURATION_SECS,
    MEETING_PREFIX,
    META_FILE,
    RECORDING_FILE,
    RECORDINGS_DIR,
    TRANSCRIPT_FILE,
    log,
    run,
)
from recorder.notion_push import push_to_notion
from recorder.preprocess import preprocess as preprocess_audio
from recorder.summarise import summarise
from recorder.transcribe import transcribe

RECORDER_DIR = Path(__file__).resolve().parent
COMPRESS_SCRIPT = RECORDER_DIR / "_compress.sh"


def _human_duration(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _human_size(path: Path) -> str:
    result = run(
        ["numfmt", "--to=iec-i", "--suffix=B", str(path.stat().st_size)],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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


def _get_active_session() -> Path | None:
    if not ACTIVE_FILE.exists():
        return None
    path = Path(ACTIVE_FILE.read_text().strip())
    if path.is_dir() and (path / META_FILE).exists():
        return path
    return None


def _cleanup_log(fh: logging.FileHandler) -> None:
    log.removeHandler(fh)
    fh.close()


def _init_session_log(
    session_dir: Path,
) -> logging.FileHandler:
    """Add a file handler for session-level logging."""
    fh = logging.FileHandler(session_dir / "capture.log")
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
    )
    log.addHandler(fh)
    return fh


def _stage_summarise(
    session_dir: Path, *, skip: bool
) -> None:
    """Run summarisation if a transcript exists."""
    if skip:
        log.info("Skipped summary (--skip-summary).")
        return
    transcript = session_dir / TRANSCRIPT_FILE
    if transcript.exists():
        log.info("Summarising...")
        summarise(transcript)


def _stage_compress(
    session_dir: Path, *, keep_wav: bool = False
) -> None:
    """Compress WAV files to MP3 after transcription."""
    log.info("Compressing...")
    cmd = [str(COMPRESS_SCRIPT), str(session_dir)]
    if keep_wav:
        cmd.append("--keep-wav")
    run(cmd, check=False)


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
    def from_json(cls, raw: str) -> "RecorderStatus":
        """Parse the script's JSON status line into a typed object.

        Every field is required: the recorder always emits them, so a missing
        key (or unparseable line) is a broken contract and is raised, not
        defaulted away.
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


def _cmd_start(args: argparse.Namespace) -> None:
    active = _get_active_session()
    if active is not None:
        log.error(
            "Recording already in progress "
            "(see: capture.py status)"
        )
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir = RECORDINGS_DIR / f"{MEETING_PREFIX}-{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)

    script = RECORDER_DIR / "_record_meeting.sh"

    result = run(
        [
            str(script),
            str(session_dir),
            str(MAX_DURATION_SECS),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log.error(
            "Failed to start recording: "
            f"{result.stderr.strip()}"
        )
        sys.exit(1)

    status = RecorderStatus.from_json(result.stdout)

    # The single recorder PID (stored as MIC_PID) owns the mixed recording
    # file; stopping it finalises it.
    meta = {
        "MIC_PID": str(status.mic_pid),
        "START_EPOCH": str(int(time.time())),
    }
    _write_meta(session_dir, meta)
    ACTIVE_FILE.write_text(str(session_dir))

    log.info(f"Recording started: {session_dir.name}")
    log.info(f"  Session:      {session_dir}")
    log.info(f"  Recorder PID: {status.mic_pid}")
    log.info(
        f"  Output:       {status.output_port} "
        f"(headphones={status.headphones}, aec={status.aec})"
    )
    log.info(
        f"  Max duration: {MAX_DURATION_SECS // 60} min (auto-stop)"
    )


def _cmd_status(args: argparse.Namespace) -> None:
    session_dir = _get_active_session()
    if session_dir is None:
        log.info("No recording in progress.")
        return

    meta = _read_meta(session_dir)
    now = int(time.time())
    start = int(meta["START_EPOCH"])
    duration = now - start

    mic_pid = int(meta["MIC_PID"])
    mic_alive = "dead"
    try:
        os.kill(mic_pid, 0)
        mic_alive = "running"
    except (ProcessLookupError, PermissionError):
        pass

    log.info(
        f"Recording in progress: {_human_duration(duration)}"
    )
    log.info(f"  Session: {session_dir}")
    log.info(f"  Mic:     pid {mic_pid} ({mic_alive})")

    sys_pid_str = meta.get("SYS_PID", "")
    if sys_pid_str:
        sys_pid = int(sys_pid_str)
        sys_alive = "dead"
        try:
            os.kill(sys_pid, 0)
            sys_alive = "running"
        except (ProcessLookupError, PermissionError):
            pass
        log.info(f"  System:  pid {sys_pid} ({sys_alive})")

    remaining = MAX_DURATION_SECS - duration
    if remaining > 0:
        log.info(
            f"  Auto-stop in: {_human_duration(remaining)}"
        )
    else:
        log.warning("  Past max duration")


def _cmd_stop(args: argparse.Namespace) -> None:
    session_dir = _get_active_session()
    if session_dir is None:
        log.error("No recording in progress.")
        sys.exit(1)

    meta = _read_meta(session_dir)
    start = int(meta["START_EPOCH"])

    # Stop ffmpeg processes
    stop_script = RECORDER_DIR / "_stop.sh"
    stop_args = [str(stop_script), meta["MIC_PID"]]
    sys_pid_str = meta.get("SYS_PID", "")
    if sys_pid_str:
        stop_args.append(sys_pid_str)

    run(stop_args, check=False)

    now = int(time.time())
    duration = now - start

    log.info("Recording stopped.")
    log.info(f"  Duration: {_human_duration(duration)}")

    rec_path = session_dir / RECORDING_FILE
    if rec_path.exists():
        log.info(f"  {RECORDING_FILE}: {_human_size(rec_path)}")

    log.info(
        f"Recording stopped: {session_dir.name} "
        f"(duration={duration}s)"
    )

    # Clean up active marker
    ACTIVE_FILE.unlink(missing_ok=True)

    fh = _init_session_log(session_dir)
    try:
        audio_name = RECORDING_FILE
        if args.cleanup and rec_path.exists():
            log.info("Preprocessing audio...")
            audio_name = preprocess_audio(rec_path).name

        log.info("Transcribing...")
        transcribe(session_dir, audio_name)

        _stage_summarise(
            session_dir, skip=args.skip_summary
        )
        _stage_compress(
            session_dir, keep_wav=args.keep_wav
        )

        if not args.skip_notion:
            log.info("Pushing to Notion...")
            push_to_notion(session_dir)
        else:
            log.info(
                "Skipped Notion push (--skip-notion)."
            )
    except Exception:
        log.exception("Pipeline failed")
        sys.exit(1)
    finally:
        _cleanup_log(fh)

    log.info(f"All output in: {session_dir}")


def _cmd_process(args: argparse.Namespace) -> None:
    page_id = extract_page_id(args.page)
    log.info(f"Notion page: {page_id}")

    log.info("Fetching audio from Notion...")
    dl_url, filename = fetch_audio_block(page_id)
    log.info(f"  Audio: {filename}")

    rec_dt = parse_recording_datetime(filename)
    if rec_dt:
        log.info(f"  Recorded: {rec_dt:%Y-%m-%d %H:%M}")
        ts = rec_dt.strftime("%Y%m%d-%H%M%S")
    else:
        log.warning("  Could not parse timestamp")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    session_dir = RECORDINGS_DIR / f"capture-{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"  Session: {session_dir}")

    log.info("Downloading audio...")
    audio_path = download_file(
        dl_url, session_dir / filename
    )
    log.info(f"  Saved: {audio_path.name}")

    fh = _init_session_log(session_dir)
    try:
        if args.cleanup:
            log.info("Preprocessing audio...")
            clean = preprocess_audio(audio_path)
            filename = clean.name

        log.info("Transcribing...")
        transcribe(session_dir, filename)

        _stage_summarise(
            session_dir, skip=args.skip_summary
        )
        _stage_compress(session_dir)

        if not args.skip_notion:
            log.info("Updating Notion page...")
            update_notion_page(
                page_id, session_dir, rec_dt
            )
        else:
            log.info(
                "Skipped Notion update (--skip-notion)."
            )
    except Exception:
        log.exception("Pipeline failed")
        sys.exit(1)
    finally:
        _cleanup_log(fh)

    log.info(f"All output in: {session_dir}")


def main() -> None:
    """CLI entry point for the capture pipeline."""
    parser = argparse.ArgumentParser(
        prog="capture",
        description=(
            "Record meetings (mic + system audio), then "
            "transcribe, summarise, compress, and push to "
            "Notion."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "start",
        help="Start dual-track recording (mic + system)",
    )

    sub.add_parser(
        "status",
        help=(
            "Show active recording duration and process info"
        ),
    )

    p_stop = sub.add_parser(
        "stop",
        help="Stop recording + transcribe + summarise + push",
        description=(
            "Stop the active recording, then run the full "
            "pipeline: transcribe (whisper.cpp), summarise "
            "(Claude Haiku), compress WAV->MP3, and push to "
            "Notion."
        ),
    )
    p_stop.add_argument(
        "--cleanup",
        action="store_true",
        help="denoise and normalize audio before transcription",
    )
    p_stop.add_argument(
        "--skip-summary",
        action="store_true",
        help=(
            "skip AI summarisation "
            "(transcript still produced)"
        ),
    )
    p_stop.add_argument(
        "--skip-notion",
        action="store_true",
        help="skip pushing the recording to Notion",
    )
    p_stop.add_argument(
        "--keep-wav",
        action="store_true",
        help="retain original WAV files alongside MP3s",
    )

    p_process = sub.add_parser(
        "process",
        help=(
            "Process a pre-recorded voice note from Notion"
        ),
        description=(
            "Download audio from an existing Notion page, "
            "transcribe, summarise, and update the page "
            "with results."
        ),
    )
    p_process.add_argument(
        "page",
        help="Notion page URL or page ID",
    )
    p_process.add_argument(
        "--cleanup",
        action="store_true",
        help="denoise and normalize audio before transcription",
    )
    p_process.add_argument(
        "--skip-summary",
        action="store_true",
        help="skip AI summarisation",
    )
    p_process.add_argument(
        "--skip-notion",
        action="store_true",
        help="skip updating the Notion page",
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "start":
        _cmd_start(args)
    elif args.command == "status":
        _cmd_status(args)
    elif args.command == "stop":
        _cmd_stop(args)
    elif args.command == "process":
        _cmd_process(args)


if __name__ == "__main__":
    main()
