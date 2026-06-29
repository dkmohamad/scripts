"""Publish a recording session to Notion — create a new page or update one.

Both paths load a :class:`~recorder.session.Session`, map it to Notion via
:mod:`recorder.notion.page` / :mod:`recorder.notion.blocks`, and call the
injected :class:`~recorder.notion.ports.NotionApi`.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from ..lib import get_notion_database_id, log
from ..session import Session
from .client import make_notion_client
from .page import notion_properties, page_body
from .ports import NotionApi

__all__ = ["main", "publish_new_page", "update_existing_page"]

_DIRNAME_DT_RE = re.compile(r"(\d{8})-(\d{6})")


def publish_new_page(
    session_dir: Path, *, client: NotionApi, database_id: str
) -> None:
    """Create a Notion database page from a recording session."""
    session = Session.load(
        session_dir, recorded_at=_date_from_dirname(session_dir)
    )
    log.info(f"Pushing to Notion: {session.title}")
    url = client.create_page(
        database_id, notion_properties(session), page_body(session)
    )
    log.info(f"Notion page created: {url}")


def update_existing_page(
    session_dir: Path,
    *,
    client: NotionApi,
    page_id: str,
    recorded_at: datetime | None,
) -> None:
    """Update an existing Notion page with a session's results."""
    session = Session.load(session_dir, recorded_at=recorded_at)
    log.info(f"Updating Notion page {page_id}: {session.title}")
    client.update_page_properties(page_id, notion_properties(session))
    if session.summary or session.transcript:
        client.append_children(page_id, page_body(session))
    log.info(f"Notion page updated: {session.title}")


def _date_from_dirname(session_dir: Path) -> datetime | None:
    """Extract the recording datetime from a meeting-YYYYMMDD-HHMMSS dirname."""
    match = _DIRNAME_DT_RE.search(session_dir.name)
    if not match:
        return None
    d, t = match.group(1), match.group(2)
    return datetime(
        int(d[:4]), int(d[4:6]), int(d[6:8]),
        int(t[:2]), int(t[2:4]), int(t[4:6]),
    )


def main() -> None:
    """CLI entry point: push a session directory to a new Notion page."""
    if len(sys.argv) < 2:
        log.error("Usage: python -m recorder.notion.publish <session_dir>")
        sys.exit(1)
    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        log.error(f"'{session_dir}' is not a directory.")
        sys.exit(1)
    database_id = get_notion_database_id()
    if not database_id:
        log.error("NOTION_DATABASE_ID is not set.")
        sys.exit(1)
    publish_new_page(
        session_dir, client=make_notion_client(), database_id=database_id
    )


if __name__ == "__main__":
    main()
