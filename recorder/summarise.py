#!/usr/bin/env python3
"""Summarise a transcript using Claude Haiku.

Sends the transcript to the Anthropic Messages API and writes a
structured summary (key points, decisions, action items).

Usage:
    summarise.py <transcript.txt>
"""

import os
import sys
from pathlib import Path

import httpx

from .lib import (
    ANTHROPIC_API_URL,
    ANTHROPIC_VERSION,
    SCRIPTS_ROOT,
    SUMMARY_FILE,
    SUMMARY_MODEL,
    TITLE_FILE,
    load_env,
    log,
)

__all__ = ["SYSTEM_PROMPT", "main", "summarise"]

SYSTEM_PROMPT = (
    "You are a note-taking assistant. Given a transcript "
    "(which may be a multi-person meeting or a solo voice note), "
    "produce a concise summary.\n\n"
    "Start your response with a single `# Title` line — a short "
    "(3-8 word) descriptive title for this recording. "
    "Then proceed with the summary sections.\n\n"
    "Always start with:\n\n"
    "## Description\n"
    "One or two sentences describing what this recording is: "
    "the type of interaction (e.g. language lesson, team standup, "
    "1-on-1, voice memo, phone call), who is involved and their "
    "roles, and the language(s) used. This sets the context for "
    "everything below.\n\n"
    "Then use whichever of these sections are relevant:\n\n"
    "## Key Points\n"
    "- Bullet the main topics or ideas.\n\n"
    "## Decisions Made\n"
    "- List any decisions reached.\n\n"
    "## Action Items\n"
    "- List action items with owners where mentioned.\n\n"
    "Omit sections that have no items. "
    "Be concise. Omit filler, small talk, and repeated content."
)


def summarise(transcript_path: Path) -> None:
    """Summarise a transcript and write the result alongside it.

    Args:
        transcript_path: Path to the transcript text file.

    Raises:
        RuntimeError: If the API key is unset, the API returns an error, or
            the response is empty. The caller's boundary decides what to do.
    """
    load_env()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            f"ANTHROPIC_API_KEY is not set "
            f"(add it to {SCRIPTS_ROOT / '.env'} or export it)"
        )

    transcript_content = transcript_path.read_text()

    log.info(f"Summarising {transcript_path.name}")

    response = httpx.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": SUMMARY_MODEL,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": transcript_content}
            ],
        },
        timeout=60,
    )

    data = response.json()

    error_msg = data.get("error", {}).get("message")
    if error_msg:
        raise RuntimeError(f"Anthropic API error: {error_msg}")

    content = data.get("content", [])
    if not content or content[0].get("text") in (None, "null", ""):
        raise RuntimeError(f"Empty response from Anthropic API: {data}")

    text = content[0]["text"]

    # Parse title from the first "# ..." line.
    title = ""
    rest_lines: list[str] = []
    for i, line in enumerate(text.splitlines()):
        if i == 0 and line.startswith("# "):
            title = line[2:].strip()
        else:
            rest_lines.append(line)

    summary = "\n".join(rest_lines).strip()

    session_dir = transcript_path.parent
    summary_file = session_dir / SUMMARY_FILE
    summary_file.write_text(summary + "\n")

    if title:
        title_file = session_dir / TITLE_FILE
        title_file.write_text(title + "\n")
        log.info(f"Title: {title}")

    log.info(summary)
    log.info(f"Summary written to: {summary_file}")


def main() -> None:
    """CLI entry point for summarise — the resilience boundary."""
    if len(sys.argv) < 2:
        log.error("Usage: summarise.py <transcript.txt>")
        sys.exit(1)

    transcript_path = Path(sys.argv[1])
    if not transcript_path.is_file():
        log.error(f"'{transcript_path}' not found.")
        sys.exit(1)

    try:
        summarise(transcript_path)
    except RuntimeError as exc:
        log.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
