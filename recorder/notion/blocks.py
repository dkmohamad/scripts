"""Build Notion page-body blocks from a session's summary and transcript."""

from __future__ import annotations

__all__ = ["NotionBlock", "body_blocks"]

# Notion API JSON structure — arbitrary nested dicts we construct, not inspect.
type NotionBlock = dict[str, object]

# Notion allows at most 2000 chars per rich_text element ...
_BLOCK_TEXT_LIMIT = 2000
# ... and at most 100 children per request.
_MAX_CHILDREN = 100


def body_blocks(summary: str, transcript: str) -> list[NotionBlock]:
    """Build the page body: a Summary section then a Transcript section."""
    blocks: list[NotionBlock] = [_heading_block("Summary")]
    blocks.extend(_paragraph_block(chunk) for chunk in _chunk_text(summary))
    blocks.append(_divider_block())
    blocks.append(_heading_block("Transcript"))
    blocks.extend(_paragraph_block(chunk) for chunk in _chunk_text(transcript))
    return blocks[:_MAX_CHILDREN]


def _chunk_text(text: str) -> list[str]:
    """Split text into chunks within Notion's per-element character limit."""
    chunks: list[str] = []
    while len(text) > _BLOCK_TEXT_LIMIT:
        idx = text.rfind("\n", 0, _BLOCK_TEXT_LIMIT)
        if idx == -1:
            idx = _BLOCK_TEXT_LIMIT
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
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _heading_block(text: str, level: int = 2) -> NotionBlock:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _divider_block() -> NotionBlock:
    return {"object": "block", "type": "divider", "divider": {}}
