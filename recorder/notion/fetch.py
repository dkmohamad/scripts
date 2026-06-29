"""Fetch audio from an existing Notion page and parse recorder filenames."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import httpx

from recorder.lib import log
from recorder.notion.ports import NotionApi

# Google Recorder filename pattern: D_Mon_at_HH-MM (e.g. "4_Jun_at_12-34"),
# embedded in a name like "nse-...-4_Jun_at_12-34.m4a.m4a".
_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_REC_DT_RE = re.compile(r"(\d{1,2})_([A-Z][a-z]{2})_at_(\d{1,2})-(\d{2})")

_DOWNLOAD_TIMEOUT = 120
_DOWNLOAD_CHUNK = 8192


def extract_page_id(page_ref: str) -> str:
    """Parse a Notion URL or raw ID into a 32-char hex page ID.

    Raises:
        ValueError: If a 32-char hex ID cannot be recovered.
    """
    page_ref = page_ref.strip()
    if "/" in page_ref:
        page_ref = page_ref.rstrip("/").rsplit("/", 1)[-1]
        # The page ID may follow a slug: "Page-Title-abc123...".
        if "-" in page_ref:
            page_ref = page_ref.rsplit("-", 1)[-1]
        page_ref = page_ref.split("?")[0]

    page_ref = page_ref.replace("-", "")
    if len(page_ref) != 32 or not all(
        c in "0123456789abcdef" for c in page_ref
    ):
        raise ValueError(f"Cannot parse Notion page ID from: {page_ref!r}")
    return page_ref


def fetch_audio_block(client: NotionApi, page_id: str) -> tuple[str, str]:
    """Return ``(download_url, filename)`` for a page's first audio block.

    Raises:
        RuntimeError: If the page has no audio block.
    """
    for block in client.block_children(page_id):
        if block.get("type") != "audio":
            continue
        audio = block["audio"]
        if audio["type"] == "file":
            dl_url = audio["file"]["url"]
            return dl_url, _filename_from_url(dl_url)
        if audio["type"] == "external":
            ext_url = audio["external"]["url"]
            return ext_url, _filename_from_url(ext_url)
    raise RuntimeError(f"No audio block found on Notion page {page_id}")


def download_file(url: str, dest: Path) -> Path:
    """Stream-download ``url`` to ``dest`` and return the saved path."""
    log.info(f"Downloading to {dest}")
    with httpx.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes(chunk_size=_DOWNLOAD_CHUNK):
                f.write(chunk)
    size_mb = dest.stat().st_size / (1024 * 1024)
    log.info(f"Downloaded {dest.name} ({size_mb:.1f} MB)")
    return dest


def parse_recording_datetime(filename: str) -> datetime | None:
    """Extract a recording timestamp from a Google Recorder filename.

    Pattern ``D_Mon_at_HH-MM``; the current year is assumed (the name omits it).
    """
    match = _REC_DT_RE.search(filename)
    if not match:
        return None
    month = _MONTH_MAP.get(match.group(2))
    if month is None:
        return None
    day = int(match.group(1))
    hour = int(match.group(3))
    minute = int(match.group(4))
    return datetime(datetime.now().year, month, day, hour, minute)


def _filename_from_url(url: str) -> str:
    """Take the filename from a URL, fixing Notion's doubled extension.

    Notion sometimes doubles the extension (``recording.m4a.m4a``); strip the
    duplicate.
    """
    name = url.split("?")[0].rsplit("/", 1)[-1]
    p = Path(name)
    if p.suffixes[-2:] == [p.suffix, p.suffix]:
        return str(p.with_suffix(""))
    return name
