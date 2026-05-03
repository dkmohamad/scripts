#!/bin/bash
# ptt-setup.sh - Setup/reset PTT after login or keyboard replug
# Clears stale processes and starts the evdev PTT daemon.
#
# Requires input group membership (sudo usermod -aG input $USER).

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

# Kill stale processes
pkill -f "arecord.*whisper_ptt.wav" 2>/dev/null
pkill -f "ptt-evdev.py" 2>/dev/null

# Clear stale lock/temp files
rm -f "$LOCKFILE" "$TMP" "$TMP_TEXT"

# Start evdev PTT daemon in background
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
"$VENV_PYTHON" "$SCRIPT_DIR/ptt-evdev.py" &
disown

log_info "PTT setup complete (evdev daemon pid=$!)"
