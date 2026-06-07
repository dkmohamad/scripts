#!/usr/bin/env python3
"""Summarise a transcript using Claude Haiku.

Sends the transcript to the Anthropic Messages API and writes a
structured summary (key points, decisions, action items).

Usage:
    summarise.py <transcript.txt>
"""

import sys
from pathlib import Path

import httpx

from recorder.lib import (
    SCRIPTS_ROOT,
    SUMMARY_FILE,
    SUMMARY_MODEL,
    load_env,
    log_error,
    log_info,
)

SYSTEM_PROMPT = (
    "You are a note-taking assistant. Given a transcript "
    "(which may be a multi-person meeting or a solo voice note), "
    "produce a concise summary.\n\n"
    "Use whichever of these sections are relevant:\n\n"
    "## Key Points\n"
    "- Bullet the main topics or ideas.\n\n"
    "## Decisions Made\n"
    "- List any decisions reached.\n\n"
    "## Action Items\n"
    "- List action items with owners where mentioned.\n\n"
    "Omit sections that have no items. "
    "Be concise. Omit filler, small talk, and repeated content."
)

MODEL = SUMMARY_MODEL
API_URL = "https://api.anthropic.com/v1/messages"


def summarise(transcript_path: Path) -> None:
    load_env()

    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(
            "Error: ANTHROPIC_API_KEY is not set.", file=sys.stderr
        )
        print(
            f"Add it to {SCRIPTS_ROOT / '.env'} or export it.",
            file=sys.stderr,
        )
        sys.exit(1)

    transcript_content = transcript_path.read_text()

    log_info(
        f"Summarising {transcript_path.name}", tag="summarise"
    )

    response = httpx.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
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
        log_error(f"API error: {error_msg}", tag="summarise")
        print(f"API error: {error_msg}", file=sys.stderr)
        sys.exit(1)

    content = data.get("content", [])
    if not content or content[0].get("text") in (
        None,
        "null",
        "",
    ):
        log_error("Empty response from API", tag="summarise")
        print(
            "Error: empty response from API.", file=sys.stderr
        )
        print(data, file=sys.stderr)
        sys.exit(1)

    summary = content[0]["text"]

    summary_file = transcript_path.parent / SUMMARY_FILE
    summary_file.write_text(summary + "\n")

    print(summary)
    print()
    print(f"Summary written to: {summary_file}")
    log_info(
        f"Summary written: {summary_file}", tag="summarise"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: summarise.py <transcript.txt>",
            file=sys.stderr,
        )
        sys.exit(1)

    transcript_path = Path(sys.argv[1])
    if not transcript_path.is_file():
        print(
            f"Error: '{transcript_path}' not found.",
            file=sys.stderr,
        )
        sys.exit(1)

    summarise(transcript_path)


if __name__ == "__main__":
    main()
