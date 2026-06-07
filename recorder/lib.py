"""Shared utilities for the recorder pipeline."""

import subprocess
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# Project root (parent of recorder/)
SCRIPTS_ROOT = Path(__file__).resolve().parent.parent

_CONFIG = dotenv_values(Path(__file__).resolve().parent / "config")

SUMMARY_MODEL = _CONFIG["SUMMARY_MODEL"]
MAX_DURATION_SECS = int(_CONFIG["MAX_DURATION_SECS"])
RECORDINGS_DIR = Path(_CONFIG["RECORDINGS_DIR"]).expanduser()
MEETING_PREFIX = _CONFIG["MEETING_PREFIX"]
MIC_FILE = _CONFIG["MIC_FILE"]
SYS_FILE = _CONFIG["SYS_FILE"]
MIC_MP3 = _CONFIG["MIC_MP3"]
SYS_MP3 = _CONFIG["SYS_MP3"]
TRANSCRIPT_FILE = _CONFIG["TRANSCRIPT_FILE"]
SUMMARY_FILE = _CONFIG["SUMMARY_FILE"]
TITLE_FILE = _CONFIG["TITLE_FILE"]
META_FILE = ".meta"
ACTIVE_FILE = Path("/tmp/capture.active")


def get_notion_database_id() -> str | None:
    """Return NOTION_DATABASE_ID from .env, or None if unset."""
    import os

    load_env()
    return os.environ.get("NOTION_DATABASE_ID")


def load_env() -> None:
    """Load $SCRIPTS_ROOT/.env into os.environ."""
    load_dotenv(SCRIPTS_ROOT / ".env")


def log_info(msg: str, tag: str = "recorder") -> None:
    subprocess.run(["logger", "-t", tag, msg], check=False)


def log_warn(msg: str, tag: str = "recorder") -> None:
    subprocess.run(
        ["logger", "-p", "user.warning", "-t", tag, msg],
        check=False,
    )


def log_error(msg: str, tag: str = "recorder") -> None:
    subprocess.run(
        ["logger", "-p", "user.err", "-t", tag, msg],
        check=False,
    )
