#!/usr/bin/env python3
"""Unified capture CLI for the recorder pipeline.

Manages the full lifecycle: start recording, check status, stop +
transcribe + summarise + compress + push to Notion. Always records
dual-track (mic + system).

Also supports processing pre-recorded voice notes from Notion.

Usage:
    capture start
    capture status
    capture stop [--skip-summary] [--skip-notion] [--keep-wav]
    capture process <page> [--skip-summary] [--skip-notion]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from recorder.lib import (
    ACTIVE_FILE,
    MAX_DURATION_SECS,
    MEETING_PREFIX,
    META_FILE,
    MIC_FILE,
    RECORDINGS_DIR,
    SYS_FILE,
    TRANSCRIPT_FILE,
    log_info,
)

RECORDER_DIR = Path(__file__).resolve().parent
COMPRESS_SCRIPT = RECORDER_DIR / "_compress.sh"


def human_duration(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def human_size(path: Path) -> str:
    result = subprocess.run(
        ["numfmt", "--to=iec-i", "--suffix=B", str(path.stat().st_size)],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def read_meta(session_dir: Path) -> dict:
    meta_path = session_dir / META_FILE
    meta: dict = {}
    for line in meta_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        meta[key.strip()] = value.strip()
    return meta


def write_meta(session_dir: Path, meta: dict) -> None:
    meta_path = session_dir / META_FILE
    with meta_path.open("w") as f:
        for key, value in meta.items():
            f.write(f"{key}={value}\n")


def get_active_session() -> Path | None:
    if not ACTIVE_FILE.exists():
        return None
    path = Path(ACTIVE_FILE.read_text().strip())
    if path.is_dir() and (path / META_FILE).exists():
        return path
    return None


def compress_session(
    session_dir: Path, keep_wav: bool = False
) -> None:
    """Compress WAV files to MP3 after transcription."""
    cmd = [str(COMPRESS_SCRIPT), str(session_dir)]
    if keep_wav:
        cmd.append("--keep-wav")
    subprocess.run(cmd, check=False)


def cmd_start(args: argparse.Namespace) -> None:
    active = get_active_session()
    if active is not None:
        print(
            "Recording already in progress "
            "(see: capture.py status)",
            file=sys.stderr,
        )
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir = RECORDINGS_DIR / f"{MEETING_PREFIX}-{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)

    script = RECORDER_DIR / "_record_meeting.sh"

    result = subprocess.run(
        [
            str(script),
            str(session_dir),
            str(MAX_DURATION_SECS),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(
            f"Failed to start recording: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    pids = json.loads(result.stdout.strip())

    meta = {
        "MIC_PID": str(pids["mic_pid"]),
        "SYS_PID": str(pids["sys_pid"]),
        "START_EPOCH": str(int(time.time())),
    }
    write_meta(session_dir, meta)
    ACTIVE_FILE.write_text(str(session_dir))

    log_info(f"Recording started: {session_dir.name}")
    print("Recording started.")
    print(f"  Session: {session_dir}")
    print(f"  Mic PID: {pids['mic_pid']}")
    print(f"  Sys PID: {pids['sys_pid']}")
    print(
        f"  Max duration: {MAX_DURATION_SECS // 60} min "
        "(auto-stop)"
    )


def cmd_status(args: argparse.Namespace) -> None:
    session_dir = get_active_session()
    if session_dir is None:
        print("No recording in progress.")
        return

    meta = read_meta(session_dir)
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

    print(
        f"Recording in progress: {human_duration(duration)}"
    )
    print(f"  Session: {session_dir}")
    print(f"  Mic:     pid {mic_pid} ({mic_alive})")

    sys_pid_str = meta.get("SYS_PID", "")
    if sys_pid_str:
        sys_pid = int(sys_pid_str)
        sys_alive = "dead"
        try:
            os.kill(sys_pid, 0)
            sys_alive = "running"
        except (ProcessLookupError, PermissionError):
            pass
        print(f"  System:  pid {sys_pid} ({sys_alive})")

    remaining = MAX_DURATION_SECS - duration
    if remaining > 0:
        print(
            f"  Auto-stop in: {human_duration(remaining)}"
        )
    else:
        print("  ⚠ Past max duration")


def cmd_stop(args: argparse.Namespace) -> None:
    session_dir = get_active_session()
    if session_dir is None:
        print("No recording in progress.", file=sys.stderr)
        sys.exit(1)

    meta = read_meta(session_dir)
    start = int(meta["START_EPOCH"])

    # Stop ffmpeg processes
    stop_script = RECORDER_DIR / "_stop.sh"
    stop_args = [str(stop_script), meta["MIC_PID"]]
    sys_pid_str = meta.get("SYS_PID", "")
    if sys_pid_str:
        stop_args.append(sys_pid_str)

    subprocess.run(stop_args, check=False)

    now = int(time.time())
    duration = now - start

    print("Recording stopped.")
    print(f"  Duration: {human_duration(duration)}")

    for fname in [MIC_FILE, SYS_FILE]:
        fpath = session_dir / fname
        if fpath.exists():
            print(f"  {fname}: {human_size(fpath)}")

    log_info(
        f"Recording stopped: {session_dir.name} "
        f"(duration={duration}s)"
    )

    # Clean up active marker
    ACTIVE_FILE.unlink(missing_ok=True)

    # Transcribe
    print()
    print("Transcribing...")
    from recorder.transcribe import transcribe_dialogue

    transcribe_dialogue(session_dir)

    # Summarise
    if not args.skip_summary:
        transcript = session_dir / TRANSCRIPT_FILE
        if transcript.exists():
            print()
            print("Summarising...")
            from recorder.summarise import summarise

            summarise(transcript)
    else:
        print()
        print("Skipped summary (--skip-summary).")

    # Compress WAV to MP3
    print()
    print("Compressing...")
    compress_session(session_dir, keep_wav=args.keep_wav)

    # Push to Notion
    if not args.skip_notion:
        print()
        print("Pushing to Notion...")
        from recorder.notion_push import push_to_notion

        push_to_notion(session_dir)
    else:
        print()
        print("Skipped Notion push (--skip-notion).")

    print()
    print(f"All output in: {session_dir}")


def cmd_process(args: argparse.Namespace) -> None:
    from recorder._notion_fetch import (
        download_file,
        extract_page_id,
        fetch_audio_block,
        parse_recording_datetime,
    )

    # 1. Extract page ID
    page_id = extract_page_id(args.page)
    print(f"Notion page: {page_id}")

    # 2. Fetch audio block
    print("Fetching audio from Notion...")
    dl_url, filename = fetch_audio_block(page_id)
    print(f"  Audio: {filename}")

    # 3. Parse recording timestamp from filename
    rec_dt = parse_recording_datetime(filename)
    if rec_dt:
        print(f"  Recorded: {rec_dt:%Y-%m-%d %H:%M}")
        ts = rec_dt.strftime("%Y%m%d-%H%M%S")
    else:
        print("  Warning: could not parse timestamp")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    # 4. Create session dir
    session_dir = RECORDINGS_DIR / f"capture-{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Session: {session_dir}")

    # 5. Download audio
    print()
    print("Downloading audio...")
    audio_path = download_file(
        dl_url, session_dir / filename
    )
    print(f"  Saved: {audio_path.name}")

    # 6. Transcribe
    print()
    print("Transcribing...")
    from recorder.transcribe import transcribe_monologue

    transcribe_monologue(session_dir, filename)

    # 7. Summarise
    if not args.skip_summary:
        transcript = session_dir / TRANSCRIPT_FILE
        if transcript.exists():
            print()
            print("Summarising...")
            from recorder.summarise import summarise

            summarise(transcript)
    else:
        print()
        print("Skipped summary (--skip-summary).")

    # 8. Update Notion page
    if not args.skip_notion:
        print()
        print("Updating Notion page...")
        from recorder._notion_update import (
            update_notion_page,
        )

        update_notion_page(page_id, session_dir, rec_dt)
    else:
        print()
        print("Skipped Notion update (--skip-notion).")

    print()
    print(f"All output in: {session_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="capture",
        description=(
            "Record meetings (mic + system audio), then "
            "transcribe, summarise, compress, and push to Notion."
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
            "(Claude Haiku), compress WAV→MP3, and push to "
            "Notion."
        ),
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
        cmd_start(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "process":
        cmd_process(args)


if __name__ == "__main__":
    main()
