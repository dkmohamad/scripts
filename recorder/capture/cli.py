"""Capture CLI: ``start`` / ``status`` / ``stop`` / ``process`` subcommands.

Thin dispatch layer. Lifecycle state lives in ``state``; the post-recording
pipeline lives in ``pipeline``. Each command does its command-specific setup
(start the recorder, stop ffmpeg, download from Notion) then delegates.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from functools import partial
from pathlib import Path

from ..lib import (
    MAX_DURATION_SECS,
    MEETING_PREFIX,
    RECORDING_FILE,
    RECORDINGS_DIR,
    get_notion_database_id,
    human_duration,
    human_size,
    log,
    run,
)
from ..notion import (
    download_file,
    extract_page_id,
    fetch_audio_block,
    make_notion_client,
    parse_recording_datetime,
    publish_new_page,
    update_existing_page,
)
from .pipeline import NotionStep, run_pipeline
from .state import (
    IdleState,
    ProcessingState,
    RecorderStatus,
    RecordingState,
)

RECORDER_DIR = Path(__file__).resolve().parent.parent


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
        help="Show active recording duration and process info",
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
        help="skip AI summarisation (transcript still produced)",
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
        help="Process a pre-recorded voice note from Notion",
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


def _cmd_start(args: argparse.Namespace) -> None:
    if RecordingState.load() is not None:
        log.error("Recording already in progress (see: capture status)")
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir = RECORDINGS_DIR / f"{MEETING_PREFIX}-{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)

    script = RECORDER_DIR / "_record_meeting.sh"
    result = run(
        [str(script), str(session_dir), str(MAX_DURATION_SECS)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error(f"Failed to start recording: {result.stderr.strip()}")
        sys.exit(1)

    status = RecorderStatus.from_json(result.stdout)
    RecordingState.begin(session_dir, status)

    log.info(f"Recording started: {session_dir.name}")
    log.info(f"  Session:      {session_dir}")
    log.info(f"  Recorder PID: {status.mic_pid}")
    log.info(
        f"  Output:       {status.output_port} "
        f"(headphones={status.headphones}, aec={status.aec})"
    )
    log.info(f"  Max duration: {MAX_DURATION_SECS // 60} min (auto-stop)")


def _cmd_status(args: argparse.Namespace) -> None:
    states = [
        state
        for state in (RecordingState.load(), ProcessingState.load())
        if state is not None
    ]
    for state in states or [IdleState.load()]:
        state.report()


def _cmd_stop(args: argparse.Namespace) -> None:
    recording = RecordingState.load()
    if recording is None:
        log.error("No recording in progress.")
        sys.exit(1)

    stop_script = RECORDER_DIR / "_stop.sh"
    run([str(stop_script), str(recording.mic_pid)], check=False)

    duration = int(time.time()) - recording.start_epoch
    log.info("Recording stopped.")
    log.info(f"  Duration: {human_duration(duration)}")

    rec_path = recording.session_dir / RECORDING_FILE
    if rec_path.exists():
        log.info(f"  {RECORDING_FILE}: {human_size(rec_path)}")
    log.info(
        f"Recording stopped: {recording.session_dir.name} "
        f"(duration={duration}s)"
    )

    recording.clear()

    notion_step: NotionStep | None = None
    if not args.skip_notion:
        database_id = get_notion_database_id()
        if database_id:
            notion_step = partial(
                publish_new_page,
                client=make_notion_client(),
                database_id=database_id,
            )
        else:
            log.warning("NOTION_DATABASE_ID not set; skipping Notion push")

    run_pipeline(
        recording.session_dir,
        RECORDING_FILE,
        cleanup=args.cleanup,
        skip_summary=args.skip_summary,
        keep_wav=args.keep_wav,
        notion_step=notion_step,
    )


def _cmd_process(args: argparse.Namespace) -> None:
    page_id = extract_page_id(args.page)
    log.info(f"Notion page: {page_id}")

    client = make_notion_client()

    log.info("Fetching audio from Notion...")
    dl_url, filename = fetch_audio_block(client, page_id)
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
    audio_path = download_file(dl_url, session_dir / filename)
    log.info(f"  Saved: {audio_path.name}")

    notion_step: NotionStep | None = (
        None
        if args.skip_notion
        else partial(
            update_existing_page,
            client=client,
            page_id=page_id,
            recorded_at=rec_dt,
        )
    )
    run_pipeline(
        session_dir,
        audio_path.name,
        cleanup=args.cleanup,
        skip_summary=args.skip_summary,
        keep_wav=False,
        notion_step=notion_step,
    )


if __name__ == "__main__":
    main()
