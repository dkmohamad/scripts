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
capture stop --cleanup     # denoise + normalize audio before transcription
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
capture process <page> --cleanup      # denoise + normalize before transcribing
capture process <page> --skip-summary
capture process <page> --skip-notion
```

For voice notes recorded on a phone (e.g. Google Recorder) and
shared to Notion via the Android share sheet. The command:

1. Downloads the audio attachment from the Notion page
2. Parses the original recording timestamp from the filename
3. *(if `--cleanup`)* Denoises and normalizes audio with DeepFilterNet
4. Transcribes and summarises the audio
5. Updates the **same** Notion page with the title, date, duration,
   summary, and full transcript

#### Audio cleanup

Pass `--cleanup` to run the DeepFilterNet denoising pipeline before
transcription. This is useful for voice notes recorded in noisy
environments (car, outdoors, etc.) where background noise degrades
whisper accuracy. The cleanup step:

- Removes background noise with DeepFilterNet (neural speech enhancement)
- Resamples to 16kHz mono (whisper target format)
- Applies an 80Hz high-pass filter to cut remaining sub-bass rumble
- Peak-normalizes to -1 dB

The cleaned file is saved as `<stem>_clean.wav` in the session
directory. The original recording is kept alongside it.

This adds processing time (~real-time on CPU for a 10-minute file),
so it is opt-in rather than default.

The session directory uses the original recording timestamp
(not the current time), e.g. `capture-20260604-123400/`.

## Pipeline stages

Both commands run through the same pipeline; they differ in audio
source, transcription mode, and Notion operation:

```
acquire → [cleanup] → transcribe → [summarise] → compress → [notify]
```

When `--cleanup` is used, audio analysis reports (RMS levels, noise
floor, SNR, clipping) are logged before and after preprocessing so
you can verify the cleanup improved the signal.

| Stage | `stop` | `process` |
|-------|--------|-----------|
| **acquire** | stop ffmpeg, read WAV from disk | download audio from Notion page |
| **cleanup** | analyse + denoise mic.wav + analyse (`--cleanup`) | analyse + denoise downloaded file + analyse (`--cleanup`) |
| **transcribe** | dialogue (mic + system, speaker labels) | monologue (single file, plain text) |
| **summarise** | Claude Haiku summary (`--skip-summary` to skip) | same |
| **compress** | WAV → MP3 (`--keep-wav` to retain) | WAV → MP3 |
| **notify** | create new Notion page (`--skip-notion`) | update existing Notion page (`--skip-notion`) |

Stages in `[brackets]` are optional. If any stage fails, the full
traceback is logged to `capture.log` inside the session directory.

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
| `preprocess.py` | Denoise + normalize audio (console script: `preprocess`) |
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

The capture pipeline writes a `capture.log` file inside each
session directory. The log covers every stage that runs after
`capture stop` or `capture process` (transcription, summarisation,
compression, Notion push).

```bash
cat ~/Recordings/capture-20260607-143000/capture.log
```

Whisper transcription logs separately to the systemd journal:

```bash
journalctl -t whisper-ptt --since "1 hour ago"
```

## Limitations

### No speaker diarization for single-track recordings

`capture process` treats all audio as a monologue — there are no
speaker labels in the transcript. If the recording contains multiple
speakers (e.g. a call recorded on a phone lying on the desk), the
output is plain text with no indication of who said what. Paragraphs
break on pauses, which often align with speaker turns, but this is
not guaranteed.

Dual-track recordings (`capture stop`) do get speaker labels because
each speaker is on a separate audio track (mic vs system audio).

## Troubleshooting

### DeepFilterNet clipping warnings

When running with `--cleanup` you may see warnings like:

```
[WARN  df::tract] Possible clipping detected (1.001).
```

This means DeepFilterNet's speech enhancement is pushing peaks to
or just past the maximum amplitude (1.0). The values are typically
very close to the limit (1.000–1.001) and the distortion is not
audible. The pipeline's peak-normalize step runs after deep-filter
and brings levels back to -1 dB, so the final output is clean.

The before/after audio analysis logged during preprocessing shows
the clipping ratio — if it's near zero after processing, no action
is needed.

## Cost

The summariser uses the model set in `config` (~$0.007 per
meeting). It outputs `summary.txt` alongside the transcript.
