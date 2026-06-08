"""Update an existing Notion page with recording results.

Sets page properties (Title, Date, Duration, Path) and appends
Summary + Transcript blocks to the page body.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import httpx

from recorder.lib import (
    SUMMARY_FILE,
    TITLE_FILE,
    TRANSCRIPT_FILE,
    load_env,
    log_error,
    log_info,
)
from recorder.notion_push import (
    NOTION_VERSION,
    _build_body_blocks,
)

NOTION_API_BASE = "https://api.notion.com/v1"


def _notion_headers() -> dict[str, str]:
    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _get_duration_minutes(session_dir: Path) -> int:
    """Get audio duration in minutes via ffprobe."""
    # Find the audio file (first non-hidden, non-txt file)
    audio_files = [
        f
        for f in session_dir.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix
        in (".m4a", ".mp3", ".wav", ".ogg", ".opus")
    ]
    if not audio_files:
        return 0

    audio_file = audio_files[0]
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_file),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        duration_secs = float(
            data["format"]["duration"]
        )
        return round(duration_secs / 60)
    except (
        subprocess.CalledProcessError,
        KeyError,
        ValueError,
    ):
        return 0


def update_notion_page(
    page_id: str,
    session_dir: Path,
    rec_dt: datetime | None,
) -> None:
    """Update a Notion page with recording results."""
    headers = _notion_headers()

    # Read text files
    title_path = session_dir / TITLE_FILE
    title = "Untitled Recording"
    if title_path.exists():
        title = title_path.read_text().strip() or title

    transcript_path = session_dir / TRANSCRIPT_FILE
    transcript = ""
    if transcript_path.exists():
        transcript = transcript_path.read_text().strip()

    summary_path = session_dir / SUMMARY_FILE
    summary = ""
    if summary_path.exists():
        summary = summary_path.read_text().strip()

    duration_mins = _get_duration_minutes(session_dir)

    # Build properties update
    properties: dict = {
        "Title": {
            "title": [{"text": {"content": title}}]
        },
        "Duration": {"number": duration_mins},
        "Path": {
            "rich_text": [
                {
                    "text": {
                        "content": str(
                            session_dir.resolve()
                        )
                    }
                }
            ]
        },
    }
    if rec_dt:
        properties["Date"] = {
            "date": {
                "start": rec_dt.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
            }
        }

    # PATCH page properties
    log_info(
        f"Updating Notion page {page_id}: {title}",
        tag="notion",
    )
    resp = httpx.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=headers,
        json={"properties": properties},
        timeout=30,
    )
    if resp.status_code >= 400:
        error = resp.json().get("message", resp.text)
        log_error(
            f"Notion page update failed: {error}",
            tag="notion",
        )
        print(f"Warning: Notion page update failed: {error}")
        return

    # Append body blocks (summary + transcript)
    if summary or transcript:
        children = _build_body_blocks(summary, transcript)
        resp = httpx.patch(
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            headers=headers,
            json={"children": children},
            timeout=30,
        )
        if resp.status_code >= 400:
            error = resp.json().get("message", resp.text)
            log_error(
                f"Notion block append failed: {error}",
                tag="notion",
            )
            print(
                f"Warning: Notion block append failed: "
                f"{error}"
            )
            return

    log_info(
        f"Notion page updated: {page_id}", tag="notion"
    )
    print(f"Notion page updated: {title}")
