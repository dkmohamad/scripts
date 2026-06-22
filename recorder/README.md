# Meeting Recorder

Record calls as a single echo-cancelled mono mix (your mic + the far-end),
transcribe with Speechmatics (Arabic ASR + speaker diarization), and
summarise with Claude Haiku 4.5 via the Anthropic API.

Also supports processing pre-recorded voice notes from Notion
(e.g. recordings made with Google Recorder on a Pixel phone).

## Pipeline

```bash
capture start              # record (mic + far-end) mixed to one mono file
capture status             # check recording
capture stop               # stop + transcribe + summarise + compress + Notion push
capture stop --cleanup     # denoise + normalize audio before transcription
capture stop --skip-summary
capture stop --skip-notion # skip pushing to Notion
capture stop --keep-wav    # keep the original WAV file
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
transcription accuracy. The cleanup step:

- Removes background noise with DeepFilterNet (neural speech enhancement)
- Resamples to 16kHz mono
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
| **cleanup** | analyse + denoise recording.wav + analyse (`--cleanup`) | analyse + denoise downloaded file + analyse (`--cleanup`) |
| **transcribe** | one file, speaker-diarized (`Speaker N`) | same |
| **summarise** | Claude Haiku summary (`--skip-summary` to skip) | same |
| **compress** | WAV → MP3 (`--keep-wav` to retain) | WAV → MP3 |
| **notify** | create new Notion page (`--skip-notion`) | update existing Notion page (`--skip-notion`) |

Stages in `[brackets]` are optional. If any stage fails, the full
traceback is logged to `capture.log` inside the session directory.

## Design notes

The rationale lives in the module docs:

- **One clean mono mix at capture** (`recorder/audio-setup.sh`,
  `shared/record.sh`). On open speakers the far-end (teacher) bleeds into the
  webcam mic, so the recorder runs the mic through PipeWire's WebRTC
  echo-canceller for the duration of a capture — enabled by `capture start`,
  torn down by `capture stop` — the same AEC a browser applies to its uplink.
  Your clean mic and the clean far-end are then mixed into a single mono file
  by one ffmpeg process. Every input — meeting, phone note, call recording —
  is therefore one audio file, so there is a single transcription path.
- **Speechmatics for ASR + diarization** (`recorder/stt.py`). Chosen for
  diacritised Arabic and language-agnostic speaker diarization; whisper.cpp,
  Google STT, and pyannote/WhisperX were rejected (see the module docstring
  for why). Speakers come out anonymous (`[Speaker 1]`/`[Speaker 2]`); a
  single-speaker recording is rendered as plain text.

## Output Structure

Each recording creates its own session directory:

```
~/Recordings/
└── capture-20260607-143000/
    ├── recording.mp3
    ├── transcript.txt
    ├── title.txt
    └── summary.txt
```

Use `--keep-wav` to retain the original WAV alongside the MP3
(e.g. for re-transcription with different settings).

## Setup

### Requirements

- Python 3.12+ with a project-level venv (see root README)
- `ffmpeg` and PulseAudio utilities for recording
- PipeWire with `module-echo-cancel` (WebRTC AEC) for clean mic capture
- A Speechmatics API key (batch ASR + diarization)
- An Anthropic API key (summaries)

```bash
cp .env.template .env
# Add your keys to .env:
#   SPEECHMATICS_API_KEY=...
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
| `stt.py` | Speechmatics batch transcription engine (ASR + diarization) |
| `transcribe.py` | Diarized (`Speaker N`) or plain transcript from Segments |
| `preprocess.py` | Denoise + normalize audio (console script: `preprocess`) |
| `summarise.py` | Summarise transcript via Anthropic API |
| `notion_push.py` | Push session to Notion database (new page) |
| `lib.py` | Shared utilities for Python scripts |
| `config` | Pipeline configuration (models, filenames, Speechmatics) |
| `audio-setup.sh` | Toggle the WebRTC echo-cancelled mic (run by start/stop) |
| `_record_meeting.sh` | Internal: record you + far-end mixed to one mono file, with AEC |
| `_stop.sh` | Internal: stop the recorder + disable AEC |
| `_compress.sh` | Internal: convert WAV to MP3 |
| `_notion_fetch.py` | Internal: download audio from a Notion page |
| `_notion_update.py` | Internal: update an existing Notion page |

## Logging

The capture pipeline writes a `capture.log` file inside each
session directory. The log covers every stage that runs after
`capture stop` or `capture process` (transcription, summarisation,
compression, Notion push).

```bash
cat ~/Recordings/capture-20260607-143000/capture.log
```

Recording and echo-cancellation log to the systemd journal under the
`recorder` tag:

```bash
journalctl -t recorder --since "1 hour ago"
```

## Limitations

### Speakers are anonymous

Every recording is transcribed as one diarized stream, so speakers are
labelled `[Speaker 1]` / `[Speaker 2]` (in order of appearance), not by
name. There is no `[You]`/`[Them]` mapping: the capture is mixed to mono,
so the separate source tracks that could identify you aren't kept. The
Claude summary can still attribute roles from context, and a single-speaker
recording is written as plain text.

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

- **Transcription**: Speechmatics batch (enhanced) is billed per hour
  of audio — check your plan.
- **Summary**: the model set in `config` (~$0.007 per meeting),
  written to `summary.txt` alongside the transcript.
