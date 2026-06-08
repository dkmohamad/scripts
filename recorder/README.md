# Meeting Recorder

Record calls (mic + system audio), transcribe with whisper.cpp
(large-v3), and summarise with Claude Haiku 4.5 via the Anthropic API.

Also supports processing pre-recorded voice notes from Notion
(e.g. recordings made with Google Recorder on a Pixel phone).

## Pipeline

```bash
capture start              # mic + system audio (dual-track)
capture status             # check recording
capture stop               # stop + transcribe + summarise + compress + Notion push
capture stop --skip-summary
capture stop --skip-notion # skip pushing to Notion
capture stop --keep-wav    # keep original WAV files
```

Stopping automatically transcribes, summarises, compresses
WAV to MP3 (~10x size reduction), and pushes to Notion.
Recordings auto-stop after 90 minutes.

### Processing voice notes

```bash
capture process <notion-page-url-or-id>
capture process <page> --skip-summary
capture process <page> --skip-notion
```

For voice notes recorded on a phone (e.g. Google Recorder) and
shared to Notion via the Android share sheet. The command:

1. Downloads the audio attachment from the Notion page
2. Parses the original recording timestamp from the filename
3. Transcribes and summarises the audio
4. Updates the **same** Notion page with the title, date, duration,
   summary, and full transcript

The session directory uses the original recording timestamp
(not the current time), e.g. `capture-20260604-123400/`.

## Output Structure

Each recording creates its own session directory:

```
~/Recordings/
└── capture-20260607-143000/
    ├── mic.mp3
    ├── system.mp3
    ├── transcript.txt
    ├── title.txt
    └── summary.txt
```

Use `--keep-wav` to retain original WAV files alongside the MP3s
(e.g. for re-transcription with different settings).

## Setup

### Requirements

- Python 3.12+ with a project-level venv (see root README)
- `ffmpeg` and PulseAudio utilities for recording
- whisper.cpp with the `large-v3` model (see `transcribe/README.md`)
- An Anthropic API key

```bash
cp .env.template .env
# Add your keys to .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   NOTION_API_KEY=ntn_...
#   NOTION_DATABASE_ID=...
uv sync
```

### Notion Integration

The pipeline pushes each recording to a Notion "Recordings"
database (under the Inbox page) with the title, date, duration,
and local path as properties, plus the summary and full transcript
as page body content.

Audio files (MP3s) are **not** uploaded — the Notion API doesn't
support file uploads. Use the `Path` property to locate files
locally.

#### Database setup

Create a database under your Inbox page with these properties:

| Property | Type | Notes |
|----------|------|-------|
| Title | Title | AI-generated short title |
| Date | Date | Recording start time |
| Duration | Number | Minutes |
| Path | Text | Local session directory path |

Then create an internal integration at
https://www.notion.so/profile/integrations, share the database
with it (database "..." menu → Connections), and add the token
and database ID to `.env`.

Required env vars in `.env`:
- `NOTION_API_KEY` — Notion internal integration token
- `NOTION_DATABASE_ID` — ID of the Recordings database

If either is missing, the Notion push is skipped with a warning
(no crash). Use `--skip-notion` to skip explicitly.

## Scripts

| Script | Description |
|--------|-------------|
| `capture.py` | Main CLI: start/stop/status/process (console script: `capture`) |
| `transcribe.py` | Transcribe audio files (dialogue or monologue) |
| `summarise.py` | Summarise transcript via Anthropic API |
| `notion_push.py` | Push session to Notion database (new page) |
| `lib.py` | Shared utilities for Python scripts |
| `config` | Pipeline configuration (model, filenames) |
| `_notion_fetch.py` | Internal: download audio from a Notion page |
| `_notion_update.py` | Internal: update an existing Notion page |
| `_record_meeting.sh` | Internal: launch dual-track ffmpeg |
| `_stop.sh` | Internal: stop ffmpeg processes |
| `_compress.sh` | Internal: convert WAV to MP3 |

## Logging

All pipeline components log to the systemd journal via `logger`.
Use `journalctl` to inspect logs:

```bash
# Pipeline events (start, stop, transcribe, Notion push)
journalctl -t recorder --since "1 hour ago"

# Whisper transcription (stderr from whisper-cli)
journalctl -t whisper-ptt --since "1 hour ago"

# Summarisation
journalctl -t summarise --since "1 hour ago"

# Notion push/update
journalctl -t notion --since "1 hour ago"
```

If transcription appears to hang or produces no output, check
`whisper-ptt` logs first — whisper errors go to the journal,
not the terminal.

## Cost

The summariser uses the model set in `config` (~$0.007 per
meeting). It outputs `summary.txt` alongside the transcript.
