"""Fetch audio from an existing Notion page.

Given a Notion page URL or ID, downloads the audio attachment
from the page body (the first audio block).
"""

import os
import re
from datetime import datetime
from pathlib import Path

import httpx

from recorder.lib import load_env, log_error, log_info

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Google Recorder filename pattern: D_Mon_at_HH-MM
# e.g. "4_Jun_at_12-34" inside a filename like
# "nse-...-4_Jun_at_12-34.m4a.m4a"
_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_REC_DT_RE = re.compile(
    r"(\d{1,2})_([A-Z][a-z]{2})_at_(\d{1,2})-(\d{2})"
)


def _notion_headers() -> dict[str, str]:
    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
    }


def extract_page_id(page_ref: str) -> str:
    """Parse a Notion URL or raw ID into a 32-char hex page ID."""
    # Strip whitespace
    page_ref = page_ref.strip()

    # If it's a URL, grab the last path segment (before query)
    if "/" in page_ref:
        page_ref = page_ref.rstrip("/").rsplit("/", 1)[-1]
        # The page ID may follow a slug with a hyphen:
        # "Page-Title-abc123def456..."
        if "-" in page_ref:
            page_ref = page_ref.rsplit("-", 1)[-1]
        # Strip query params
        page_ref = page_ref.split("?")[0]

    # Remove any hyphens (Notion sometimes shows dashed UUIDs)
    page_ref = page_ref.replace("-", "")

    if len(page_ref) != 32 or not all(
        c in "0123456789abcdef" for c in page_ref
    ):
        raise ValueError(
            f"Cannot parse Notion page ID from: {page_ref!r}"
        )
    return page_ref


def _clean_filename(filename: str) -> str:
    """Fix duplicate extensions from Notion storage.

    Notion sometimes doubles the extension (e.g.
    "recording.m4a.m4a"). Strip the duplicate.
    """
    p = Path(filename)
    if p.suffixes[-2:] == [p.suffix, p.suffix]:
        return str(p.with_suffix(""))
    return filename


def fetch_audio_block(page_id: str) -> tuple[str, str]:
    """Fetch the first audio block from a Notion page.

    Returns (signed_download_url, original_filename).
    """
    url = f"{NOTION_API_BASE}/blocks/{page_id}/children"
    resp = httpx.get(
        url, headers=_notion_headers(), timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    for block in data.get("results", []):
        if block.get("type") != "audio":
            continue
        audio = block["audio"]
        # Notion audio can be "file" (internal) or "external"
        if audio["type"] == "file":
            file_info = audio["file"]
            dl_url = file_info["url"]
            url_path = file_info["url"].split("?")[0]
            filename = _clean_filename(
                url_path.rsplit("/", 1)[-1]
            )
            return dl_url, filename
        elif audio["type"] == "external":
            ext_url = audio["external"]["url"]
            filename = _clean_filename(
                ext_url.split("?")[0].rsplit("/", 1)[-1]
            )
            return ext_url, filename

    raise RuntimeError(
        f"No audio block found on Notion page {page_id}"
    )


def download_file(url: str, dest: Path) -> Path:
    """Stream-download a file to dest. Return saved path."""
    log_info(f"Downloading to {dest}")
    with httpx.stream("GET", url, timeout=120) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes(chunk_size=8192):
                f.write(chunk)
    size_mb = dest.stat().st_size / (1024 * 1024)
    log_info(f"Downloaded {dest.name} ({size_mb:.1f} MB)")
    return dest


def parse_recording_datetime(
    filename: str,
) -> datetime | None:
    """Extract recording timestamp from Google Recorder filename.

    Pattern: D_Mon_at_HH-MM (e.g. "4_Jun_at_12-34").
    Uses current year since Google Recorder omits it.
    """
    m = _REC_DT_RE.search(filename)
    if not m:
        return None

    day = int(m.group(1))
    month = _MONTH_MAP.get(m.group(2))
    hour = int(m.group(3))
    minute = int(m.group(4))

    if month is None:
        return None

    year = datetime.now().year
    return datetime(year, month, day, hour, minute)
