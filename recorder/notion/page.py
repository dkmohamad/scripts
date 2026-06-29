"""Map a :class:`~recorder.session.Session` to Notion page payloads."""

from __future__ import annotations

from ..session import Session
from .blocks import NotionBlock, body_blocks

__all__ = ["notion_properties", "page_body"]


def notion_properties(session: Session) -> dict[str, object]:
    """Build the Notion page properties for a session.

    Title and Path are always set; Duration is included only when the audio
    duration is known, and Date only when the recording time is known.
    """
    properties: dict[str, object] = {
        "Title": {"title": [{"text": {"content": session.title}}]},
        "Path": {
            "rich_text": [
                {"text": {"content": str(session.session_dir.resolve())}}
            ]
        },
    }
    if session.duration_minutes is not None:
        properties["Duration"] = {"number": session.duration_minutes}
    if session.recorded_at is not None:
        properties["Date"] = {
            "date": {
                "start": session.recorded_at.strftime("%Y-%m-%dT%H:%M:%S")
            }
        }
    return properties


def page_body(session: Session) -> list[NotionBlock]:
    """Build the Notion page-body blocks (Summary + Transcript) for a session."""
    return body_blocks(session.summary, session.transcript)
