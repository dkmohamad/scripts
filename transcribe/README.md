# Push-to-Talk Voice Dictation

Voice dictation using whisper.cpp with a keyboard hotkey.

## Requirements

```bash
sudo apt install -y build-essential cmake make git alsa-utils xdotool
```

Typing is session-aware: `type_text` in `env.sh` picks the tool from
`XDG_SESSION_TYPE` at runtime and fails loud on anything else.

- **X11**: `xdotool` (XTEST events). The apt package above is enough.
- **Wayland**: the vendored **ydotool** (kernel-level uinput injection —
  xdotool's XTEST events never reach native Wayland windows). This needs
  `ydotool` **built from source** (step 5): the daemon runs `ydotoold`, which
  holds one persistent uinput keyboard so the compositor enumerates it once.
  Do **not** use Ubuntu's apt `ydotool` (0.1.8) — it ships no `ydotoold`, and
  its daemonless mode creates/destroys a virtual keyboard per keystroke faster
  than GNOME's mutter can enumerate it, so keystrokes land nowhere.

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

### 5. Build ydotool and grant uinput access (Wayland only)

Build the vendored ydotool client + daemon:

```bash
cd vendor/ydotool
cmake -B build -DBUILD_DOCS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)      # produces build/ydotool and build/ydotoold
```

`ydotoold` opens `/dev/uinput`, which is root-only by default. Grant the
`input` group access (step 4 already put you in it):

```bash
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/60-uinput-input-group.rules
sudo udevadm control --reload-rules && sudo udevadm trigger --sysname-match=uinput
ls -l /dev/uinput    # should show root:input 0660
```

`ptt-setup.sh` (step 7) installs `ydotoold` as a systemd **user service**
(`Restart=always`, socket at `$XDG_RUNTIME_DIR/.ydotool_socket`) and makes
`ptt-evdev` require it, so the persistent typing device is always up.

### 6. Disable the old xbindkeys hotkey

> **Important:** PTT was previously driven by `xbindkeys`. The evdev daemon
> replaces it. If `xbindkeys` is still bound to `Ctrl+Menu` it will run
> *alongside* the daemon and fire `ptt-start.sh` on every key-repeat,
> fighting the daemon over the lock and producing empty recordings.

If `~/.xbindkeysrc` contains only the PTT bindings, just remove it and stop
the running instance:

```bash
rm ~/.xbindkeysrc        # or remove only the c:135 / m:0x4 PTT blocks
pkill -x xbindkeys
```

xbindkeys is autostarted via `xbindkeys_autostart`, which only launches
xbindkeys when a config file exists (`/etc/xbindkeysrc`, `~/.xbindkeysrc`,
or `~/.xbindkeysrc.scm`). With no config present it won't start at login,
so removing the file is enough — no autostart override needed. If you use
xbindkeys for other bindings, just delete the PTT entries instead.

### 7. Install and start the PTT service

```bash
./transcribe/ptt-setup.sh
```

This installs a `ptt-evdev` **systemd user service** (`Restart=always`),
enables it so it starts automatically at login, and (re)starts it now. The
daemon monitors all keyboards for Ctrl+Menu press/release and calls
`ptt-start.sh` / `ptt-stop.sh`. It survives keyboard unplug/re-enumeration
and resume-from-suspend. No separate autostart entry is needed.

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

# Check the service is running
systemctl --user status ptt-evdev

# Restart it
systemctl --user restart ptt-evdev    # or: ./transcribe/ptt-setup.sh
```

**Transcription works but no text is typed (`TYPE failed` in logs):**
```bash
echo "$XDG_SESSION_TYPE"                       # wayland or x11?
```
On Wayland the typing path is the vendored ydotool + ydotoold:
```bash
systemctl --user status ydotoold               # daemon running?
ls -l "$XDG_RUNTIME_DIR/.ydotool_socket"       # socket present (srw-------)?
ls -l /dev/uinput                              # must be root:input 0660 (step 5)
grep ydotoold /sys/class/input/event*/device/name   # persistent device exists?
```
If keystrokes land nowhere but `ydotoold` is up, confirm you are running the
**vendored** client (`vendor/ydotool/build/ydotool`), not the apt `ydotool`
0.1.8 — the latter ignores the daemon and loses keystrokes to the
ephemeral-device race (see Requirements).

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

**Empty recordings (rapid start/stop, "operation in progress" / "lock
timeout" floods in logs):** almost always a second hotkey handler firing
alongside the daemon. Check that xbindkeys isn't still bound to Ctrl+Menu
(see setup step 6):
```bash
pgrep -ax xbindkeys                   # should print nothing
journalctl -t whisper-ptt --since "5 min ago" | grep "START skipped"
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
