"""Tests for the Notion publish steps and Session->Notion mappers."""

from datetime import datetime
from pathlib import Path
from typing import Any

from recorder.lib import SUMMARY_FILE, TITLE_FILE, TRANSCRIPT_FILE
from recorder.notion.blocks import NotionBlock, body_blocks
from recorder.notion.page import notion_properties
from recorder.notion.publish import publish_new_page, update_existing_page
from recorder.session import Session


class _FakeNotionClient:
    """Records calls instead of hitting the Notion API (satisfies NotionApi)."""

    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, object], list[NotionBlock]]] = []
        self.updated: list[tuple[str, dict[str, object]]] = []
        self.appended: list[tuple[str, list[NotionBlock]]] = []

    def create_page(
        self,
        database_id: str,
        properties: dict[str, object],
        children: list[NotionBlock],
    ) -> str:
        self.created.append((database_id, properties, children))
        return "https://notion.so/created"

    def update_page_properties(
        self, page_id: str, properties: dict[str, object]
    ) -> None:
        self.updated.append((page_id, properties))

    def append_children(
        self, page_id: str, children: list[NotionBlock]
    ) -> None:
        self.appended.append((page_id, children))

    def block_children(self, page_id: str) -> list[dict[str, Any]]:
        return []


def _write_session(session_dir: Path) -> None:
    (session_dir / TITLE_FILE).write_text("My Meeting\n")
    (session_dir / TRANSCRIPT_FILE).write_text("transcript body\n")
    (session_dir / SUMMARY_FILE).write_text("summary body\n")


def test_publish_new_page_should_create_with_mapped_properties(
    tmp_path: Path,
) -> None:
    """publish_new_page creates a page with the session's mapped properties.

    Arrange a session dir and a fake client, publish, then assert create_page
    is called once with the database id and the mapped Title. Guards the DI
    seam (no httpx) and the Session->Notion property mapping.
    """
    _write_session(tmp_path)
    client = _FakeNotionClient()

    publish_new_page(tmp_path, client=client, database_id="db123")

    assert len(client.created) == 1
    database_id, properties, children = client.created[0]
    assert database_id == "db123"
    assert properties["Title"] == {"title": [{"text": {"content": "My Meeting"}}]}
    assert children


def test_update_existing_page_should_patch_then_append(
    tmp_path: Path,
) -> None:
    """update_existing_page patches properties then appends body blocks.

    Guards that an existing page is updated (properties) and its body filled
    (blocks) via the injected client.
    """
    _write_session(tmp_path)
    client = _FakeNotionClient()

    update_existing_page(
        tmp_path, client=client, page_id="pg1", recorded_at=None
    )

    assert client.updated and client.updated[0][0] == "pg1"
    assert client.appended and client.appended[0][0] == "pg1"


def test_notion_properties_should_omit_unknown_duration_and_date() -> None:
    """notion_properties omits Duration and Date when they are unknown.

    A session with no duration and no recorded_at maps to properties without
    Duration/Date keys. Guards the mapper's optional-field contract.
    """
    session = Session(
        session_dir=Path("/tmp/x"),
        title="T",
        transcript="",
        summary="",
        duration_minutes=None,
        recorded_at=None,
    )

    props = notion_properties(session)

    assert "Duration" not in props
    assert "Date" not in props


def test_notion_properties_should_include_known_duration_and_date() -> None:
    """notion_properties includes Duration and Date when both are known.

    Guards that a fully-populated session maps to the numeric Duration and the
    ISO Date string Notion expects.
    """
    session = Session(
        session_dir=Path("/tmp/x"),
        title="T",
        transcript="",
        summary="",
        duration_minutes=42,
        recorded_at=datetime(2026, 6, 29, 9, 30, 0),
    )

    props = notion_properties(session)

    assert props["Duration"] == {"number": 42}
    assert props["Date"] == {"date": {"start": "2026-06-29T09:30:00"}}


def test_body_blocks_should_chunk_long_text_and_cap_at_100() -> None:
    """body_blocks splits over-long text and never exceeds Notion's 100 cap.

    Feed a transcript far larger than the per-block limit and assert the result
    is capped at 100 blocks. Guards the Notion children-count limit.
    """
    blocks = body_blocks("short summary", "x" * 500_000)

    assert len(blocks) <= 100
