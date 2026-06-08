"""Push a recording session to a Notion database.

Creates a page in the Recordings database with the transcript and
summary as page body content.

Usage:
    notion_push.py <session_dir>
"""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from recorder.lib import (
    META_FILE,
    SUMMARY_FILE,
    TITLE_FILE,
    TRANSCRIPT_FILE,
    get_notion_database_id,
    load_env,
    log,
)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"

# Notion blocks have a 2000-char limit per rich_text element.
BLOCK_TEXT_LIMIT = 2000

# Notion API JSON structure — arbitrary nested dicts.
type NotionBlock = dict[str, object]


def _chunk_text(text: str) -> list[str]:
    """Split text into chunks that fit Notion's block limit."""
    chunks: list[str] = []
    while len(text) > BLOCK_TEXT_LIMIT:
        # Try to break at a newline
        idx = text.rfind("\n", 0, BLOCK_TEXT_LIMIT)
        if idx == -1:
            idx = BLOCK_TEXT_LIMIT
        chunks.append(text[:idx])
        text = text[idx:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def _paragraph_block(text: str) -> NotionBlock:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text},
                }
            ]
        },
    }


def _heading_block(text: str, level: int = 2) -> NotionBlock:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text},
                }
            ]
        },
    }


def _divider_block() -> NotionBlock:
    return {
        "object": "block",
        "type": "divider",
        "divider": {},
    }


def _build_body_blocks(
    summary: str, transcript: str
) -> list[NotionBlock]:
    """Build Notion block children from summary + transcript."""
    blocks: list[NotionBlock] = []

    blocks.append(_heading_block("Summary"))
    for chunk in _chunk_text(summary):
        blocks.append(_paragraph_block(chunk))

    blocks.append(_divider_block())
    blocks.append(_heading_block("Transcript"))
    for chunk in _chunk_text(transcript):
        blocks.append(_paragraph_block(chunk))

    # Notion API allows max 100 children per request.
    return blocks[:100]


def _parse_date_from_dirname(
    session_dir: Path,
) -> str | None:
    """Extract ISO date from session dirname like meeting-20260607-143000."""
    match = re.search(r"(\d{8})-(\d{6})", session_dir.name)
    if not match:
        return None
    d, t = match.group(1), match.group(2)
    dt = datetime(
        int(d[:4]), int(d[4:6]), int(d[6:8]),
        int(t[:2]), int(t[2:4]), int(t[4:6]),
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def push_to_notion(session_dir: Path) -> None:
    """Create a Notion page from a recording session's transcript and summary."""
    load_env()

    api_key = os.environ.get("NOTION_API_KEY", "")
    database_id = get_notion_database_id()

    if not api_key or not database_id:
        log.warning(
            "NOTION_API_KEY or NOTION_DATABASE_ID not set, "
            "skipping Notion push"
        )
        return

    # Read session metadata
    meta_path = session_dir / META_FILE
    meta: dict[str, str] = {}
    if meta_path.exists():
        for line in meta_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            meta[key.strip()] = value.strip()

    # Compute duration in minutes
    start_epoch = int(meta.get("START_EPOCH", "0"))
    stop_epoch = int(meta.get("STOP_EPOCH", "0"))
    if stop_epoch and start_epoch:
        duration_mins = (stop_epoch - start_epoch) // 60
    elif start_epoch:
        duration_mins = (int(time.time()) - start_epoch) // 60
    else:
        duration_mins = 0

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

    # Build date property
    date_str = _parse_date_from_dirname(session_dir)

    # Build Notion page payload
    properties: dict[str, object] = {
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
    if date_str:
        properties["Date"] = {
            "date": {"start": date_str}
        }

    children = _build_body_blocks(summary, transcript)

    payload: dict[str, object] = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": children,
    }

    log.info(f"Pushing to Notion: {title}")

    response = httpx.post(
        NOTION_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        error = response.json().get(
            "message", response.text
        )
        log.error(f"Notion API error: {error}")
        return

    page_url = response.json().get("url", "")
    log.info(f"Notion page created: {page_url}")


def main() -> None:
    """CLI entry point for notion_push."""
    if len(sys.argv) < 2:
        log.error("Usage: notion_push.py <session_dir>")
        sys.exit(1)

    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        log.error(f"'{session_dir}' is not a directory.")
        sys.exit(1)

    push_to_notion(session_dir)


if __name__ == "__main__":
    main()
