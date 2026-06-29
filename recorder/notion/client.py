"""HTTP adapter over the Notion REST API.

The single home for the authed Notion endpoints the pipeline uses, so headers,
base URL, and version live once and every call raises on an API error (the
pipeline boundary decides what to do).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from recorder.lib import NOTION_API_BASE, NOTION_VERSION, load_env
from recorder.notion.blocks import NotionBlock
from recorder.notion.ports import NotionApi

_TIMEOUT = 30


class NotionClient(NotionApi):
    """Authenticated client for the Notion pages/blocks API."""

    def __init__(self, api_key: str):
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def create_page(
        self,
        database_id: str,
        properties: dict[str, object],
        children: list[NotionBlock],
    ) -> str:
        """Create a database page and return its URL.

        Raises:
            httpx.HTTPStatusError: If the Notion API rejects the request.
        """
        resp = httpx.post(
            f"{NOTION_API_BASE}/pages",
            headers=self._headers,
            json={
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": children,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        url: Any = resp.json().get("url", "")
        return str(url)

    def update_page_properties(
        self, page_id: str, properties: dict[str, object]
    ) -> None:
        """Patch a page's properties.

        Raises:
            httpx.HTTPStatusError: If the Notion API rejects the request.
        """
        resp = httpx.patch(
            f"{NOTION_API_BASE}/pages/{page_id}",
            headers=self._headers,
            json={"properties": properties},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

    def append_children(
        self, page_id: str, children: list[NotionBlock]
    ) -> None:
        """Append body blocks to a page.

        Raises:
            httpx.HTTPStatusError: If the Notion API rejects the request.
        """
        resp = httpx.patch(
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            headers=self._headers,
            json={"children": children},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

    def block_children(self, page_id: str) -> list[dict[str, Any]]:
        """Return a page's child blocks.

        Raises:
            httpx.HTTPStatusError: If the Notion API rejects the request.
        """
        resp = httpx.get(
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            headers=self._headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        results: Any = resp.json().get("results", [])
        return list(results)


def make_notion_client() -> NotionClient:
    """Build a :class:`NotionClient` from the environment.

    Raises:
        RuntimeError: If ``NOTION_API_KEY`` is not set.
    """
    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        raise RuntimeError("NOTION_API_KEY is not set")
    return NotionClient(api_key)
