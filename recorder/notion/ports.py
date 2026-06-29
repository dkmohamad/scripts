"""The Notion API port the publish/fetch logic depends on.

High-level code (publish, fetch) imports this interface and receives a concrete
adapter (``NotionClient``) by injection — it never imports the adapter just to
name a type. Tests supply a fake that satisfies this protocol structurally.
"""

from __future__ import annotations

from typing import Any, Protocol

from .blocks import NotionBlock


class NotionApi(Protocol):
    """The Notion operations the recorder pipeline needs."""

    def create_page(
        self,
        database_id: str,
        properties: dict[str, object],
        children: list[NotionBlock],
    ) -> str:
        """Create a database page and return its URL."""
        ...

    def update_page_properties(
        self, page_id: str, properties: dict[str, object]
    ) -> None:
        """Patch a page's properties."""
        ...

    def append_children(
        self, page_id: str, children: list[NotionBlock]
    ) -> None:
        """Append body blocks to a page."""
        ...

    def block_children(self, page_id: str) -> list[dict[str, Any]]:
        """Return a page's child blocks."""
        ...
