# Meeting Recorder

Record calls (mic + system audio), transcribe with whisper.cpp
(large-v3), and summarise with Claude Haiku 4.5 via the Anthropic API.

## Pipeline

```bash
capture start              # mic + system audio (dual-track)
capture status             # check recording
capture stop               # stop + transcribe + summarise + compress
capture stop --skip-summary
capture stop --keep-wav    # keep original WAV files
```

Stopping automatically transcribes, summarises, and compresses
WAV to MP3 (~10x size reduction). Recordings auto-stop after
90 minutes.

## Output Structure

Each recording creates its own session directory:

```
~/Recordings/
└── meeting-20260607-143000/
    ├── mic.mp3
    ├── system.mp3
    ├── transcript.txt
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
# Add your ANTHROPIC_API_KEY to .env
uv sync
```

## Scripts

| Script | Description |
|--------|-------------|
| `capture.py` | Main CLI: start/stop/status (console script: `capture`) |
| `transcribe.py` | Transcribe a session directory |
| `summarise.py` | Summarise transcript via Anthropic API |
| `lib.py` | Shared utilities for Python scripts |
| `config` | Pipeline configuration (model, filenames) |
| `_record_meeting.sh` | Internal: launch dual-track ffmpeg |
| `_stop.sh` | Internal: stop ffmpeg processes |
| `_compress.sh` | Internal: convert WAV to MP3 |

## Cost

The summariser uses the model set in `config` (~$0.007 per
meeting). It outputs `summary.txt` alongside the transcript.
