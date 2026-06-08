"""Shared utilities for the recorder pipeline."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv

# Project root (parent of recorder/)
SCRIPTS_ROOT = Path(__file__).resolve().parent.parent

_CONFIG = dotenv_values(Path(__file__).resolve().parent / "config")


def _require(key: str) -> str:
    """Read a required key from the config file."""
    value = _CONFIG.get(key)
    if value is None:
        msg = f"Missing required config key: {key}"
        raise KeyError(msg)
    return value


SUMMARY_MODEL: str = _require("SUMMARY_MODEL")
MAX_DURATION_SECS: int = int(_require("MAX_DURATION_SECS"))
RECORDINGS_DIR: Path = Path(_require("RECORDINGS_DIR")).expanduser()
MEETING_PREFIX: str = _require("MEETING_PREFIX")
MIC_FILE: str = _require("MIC_FILE")
SYS_FILE: str = _require("SYS_FILE")
MIC_MP3: str = _require("MIC_MP3")
SYS_MP3: str = _require("SYS_MP3")
TRANSCRIPT_FILE: str = _require("TRANSCRIPT_FILE")
SUMMARY_FILE: str = _require("SUMMARY_FILE")
TITLE_FILE: str = _require("TITLE_FILE")
META_FILE = ".meta"
ACTIVE_FILE = Path("/tmp/capture.active")

log = logging.getLogger("recorder")
log.setLevel(logging.DEBUG)
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(_stream_handler)


def get_notion_database_id() -> str | None:
    """Return NOTION_DATABASE_ID from .env, or None if unset."""
    load_env()
    return os.environ.get("NOTION_DATABASE_ID")


def load_env() -> None:
    """Load $SCRIPTS_ROOT/.env into os.environ."""
    load_dotenv(SCRIPTS_ROOT / ".env")


def run(
    cmd: list[str], **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    """Run a command with stdin closed.

    Thin wrapper around subprocess.run that always passes
    stdin=DEVNULL so child processes (ffmpeg, deep-filter,
    etc.) never block waiting for terminal input.
    """
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(cmd, **kwargs)
