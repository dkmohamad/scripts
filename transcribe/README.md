# Push-to-Talk Voice Dictation

Voice dictation using whisper.cpp with a keyboard hotkey.

## Requirements

```bash
sudo apt install -y build-essential cmake make git alsa-utils xdotool
```

## Setup

### 1. Install Python dependencies

```bash
uv sync
```

### 2. Build whisper.cpp

```bash
cd vendor/whisper.cpp

# CPU only
cmake -B build && cmake --build build -j$(nproc)

# With CUDA (recommended)
sudo apt install nvidia-cuda-toolkit
cmake -B build -DGGML_CUDA=ON && cmake --build build -j$(nproc)
```

### 3. Download models

```bash
cd vendor/whisper.cpp/models
./download-ggml-model.sh base.en      # English PTT (fast)
./download-ggml-model.sh large-v3     # Meeting transcription
./download-vad-model.sh silero-v6.2.0
```

| Model | Used by | Notes |
|-------|---------|-------|
| `base.en` | Push-to-talk | Fast, English-only |
| `large-v3` | Meeting transcription | Accurate, multilingual, fewer hallucinations |

VAD (Voice Activity Detection) filters trailing silence to prevent
hallucinations like "you" or "Thank you for watching".

### 4. Add user to input group

The evdev daemon reads `/dev/input/*` directly, which requires the
`input` group. Add your user and re-login:

```bash
sudo usermod -aG input $USER
# Log out and back in for the group change to take effect
```

Verify after re-login:

```bash
groups | grep input
```

### 5. Start the PTT daemon

```bash
./transcribe/ptt-setup.sh
```

This kills any stale processes and starts the evdev PTT daemon in
the background. The daemon monitors all keyboards for Ctrl+Menu
press/release and calls `ptt-start.sh` / `ptt-stop.sh`.

### 6. Autostart

Add to your desktop session autostart (e.g. `~/.xsessionrc`):

```bash
/path/to/scripts/transcribe/ptt-setup.sh
```

## Usage

1. Focus target window
2. Hold `Ctrl+Menu` and speak
3. Release -> text typed

## Troubleshooting

**No text appears:**
```bash
ls -la /tmp/whisper_ptt.wav                    # Recording exists?
aplay /tmp/whisper_ptt.wav                     # Mic working?
./vendor/whisper.cpp/build/bin/whisper-cli \
  -m vendor/whisper.cpp/models/ggml-base.en.bin \
  -f /tmp/whisper_ptt.wav                      # Whisper working?
```

**Hotkey not triggering:**
```bash
# Test evdev key detection
.venv/bin/python transcribe/ptt-evdev.py --test

# Check the daemon is running
pgrep -f ptt-evdev

# Restart the daemon
./transcribe/ptt-setup.sh
```

**Permission denied on /dev/input:**
```bash
groups | grep input     # Are you in the input group?
# If not: sudo usermod -aG input $USER, then log out and back in
```

**Empty output (whisper error):**
Whisper stderr is logged to the journal. Check for errors:
```bash
journalctl -t whisper-ptt -p err --since "5 min ago"
```

**Empty recordings (rapid start/stop in logs):**
```bash
journalctl -t whisper-ptt -p err --since "5 min ago"
```

## Logs

```bash
journalctl -t whisper-ptt --since "10 min ago"    # Recent logs
journalctl -t whisper-ptt -f                       # Follow live
journalctl -t whisper-ptt -p err                   # Errors only
```

Example output:
```
START pid=12345
STOP duration=2.3s size=45K mem=4.2GB gpu=1200MB/8192MB
WHISPER exit=0 time=0.8s
TYPED chars=42
```

Error (empty recording):
```
STOP duration=0.1s size=128B (recording empty - no audio captured)
```

## Known Issues

**CUDA crashes with rapid triggers:** Lock file prevents concurrent
whisper processes. 30s timeout kills hung transcriptions.

```bash
journalctl -b -1 | grep -i "whisper\|coredump"    # Check past crashes
```
