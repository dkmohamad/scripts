# Scripts

A collection of utility scripts for Linux.

## Tools

| Tool | Description |
|------|-------------|
| [transcribe](transcribe/) | Push-to-talk voice dictation |
| [recorder](recorder/) | Record, transcribe & summarise meetings |
| [gdrive-mount](gdrive-mount/) | Mount Google Drive as FUSE filesystem via rclone |

## Structure

```
scripts/
├── shared/         # Common utilities (logging, helpers)
├── transcribe/     # Push-to-talk voice dictation
├── recorder/       # Meeting recording, transcription & summarisation
├── gdrive-mount/   # Google Drive mounting
└── vendor/         # Third-party dependencies (submodules)
```

## Shared Utilities

All tools source `shared/env.sh` which provides:

- **Logging** - `log_info`, `log_warn`, `log_error` write to systemd journal
- **Recording** - `record_audio`, `stop_recording` (ffmpeg + PulseAudio)
- **Helpers** - `require_command`, `get_mem_avail`, `get_gpu_mem`
- **Paths** - `SCRIPTS_ROOT`, `SHARED_DIR`, `VENDOR_DIR`

Each tool has its own `env.sh` for tool-specific configuration.

## Setup

Clone with submodules:

```bash
git clone --recurse-submodules git@github.com:dkmohamad/scripts.git
```

Install Python dependencies (requires [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
```

Copy the environment template and fill in your keys:

```bash
cp .env.template .env
# Edit .env with your API keys (gitignored, never committed)
```

### System dependencies

```bash
sudo apt install ffmpeg pulseaudio-utils
```

### Vendor binaries

The `vendor/` directory contains third-party binaries:

- **whisper.cpp** — speech-to-text (git submodule, built from source)
- **ydotool** — Wayland keystroke injection for push-to-talk dictation
  (git submodule, built from source; see [transcribe/](transcribe/))
- **deep-filter** — DeepFilterNet neural speech enhancement

To build ydotool (client + `ydotoold` daemon):

```bash
cd vendor/ydotool
cmake -B build -DBUILD_DOCS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
```

To download the deep-filter binary:

```bash
gh release download v0.5.6 --repo Rikorose/DeepFilterNet \
  --pattern "deep-filter-0.5.6-x86_64-unknown-linux-musl" \
  --dir vendor/deep-filter
mv vendor/deep-filter/deep-filter-0.5.6-x86_64-unknown-linux-musl \
  vendor/deep-filter/deep-filter
chmod +x vendor/deep-filter/deep-filter
```

See individual tool READMEs for setup instructions.
