#!/usr/bin/env bash
# env.sh - Environment for PTT voice transcription scripts
#
# Provides constants, logging, and lock management for push-to-talk
# transcription using whisper.cpp. Sourced by ptt-start.sh and ptt-stop.sh.

# ------------------------------------------------------------------------------
# Source shared utilities
# ------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/../shared"
LOG_TAG="whisper-ptt"
source "$SHARED_DIR/env.sh"

# ------------------------------------------------------------------------------
# Transcribe-specific constants
# ------------------------------------------------------------------------------

# Temp files
TMP=/tmp/whisper_ptt.wav
TMP_TEXT=/tmp/whisper_ptt.txt
LOCKFILE=/tmp/whisper_ptt.lock
TIMEFILE=/tmp/whisper_ptt.start

# Timeouts (seconds)
WHISPER_TIMEOUT=30

# xdotool typing delay (ms between keystrokes). Higher values prevent crashes
# in some terminal apps (e.g., Claude CLI's React UI with rapid input).
XDOTOOL_DELAY=20

# Whisper paths
WHISPER_BIN="$VENDOR_DIR/whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL="$VENDOR_DIR/whisper.cpp/models/ggml-base.en.bin"
VAD_MODEL="$VENDOR_DIR/whisper.cpp/models/ggml-silero-v6.2.0.bin"

# Transcribe a WAV file with whisper.cpp. Raw output on stdout.
whisper_transcribe() {
    "$WHISPER_BIN" \
        -m "$WHISPER_MODEL" -f "$1" -np -nt -sns \
        --vad -vm "$VAD_MODEL" 2>/dev/null
}

# ------------------------------------------------------------------------------
# Lock management
# ------------------------------------------------------------------------------

# Acquire exclusive lock (non-blocking). Returns 1 if already locked.
acquire_lock() {
    exec 9>"$LOCKFILE"
    flock -n 9
}

# Acquire exclusive lock with timeout (blocking). Returns 1 on timeout.
acquire_lock_wait() {
    local timeout=${1:-2}
    exec 9>"$LOCKFILE"
    flock -w "$timeout" 9
}

# ------------------------------------------------------------------------------
# Timer utilities
# ------------------------------------------------------------------------------

# Start a timer by writing current time to TIMEFILE
start_timer() {
    date +%s.%N > "$TIMEFILE"
}

# Get duration since timer start (returns "?" if no timer). Cleans up TIMEFILE.
get_duration() {
    if [ -f "$TIMEFILE" ]; then
        local start end
        start=$(cat "$TIMEFILE")
        end=$(date +%s.%N)
        rm -f "$TIMEFILE"
        echo "$end - $start" | bc | xargs printf "%.1f"
    else
        echo "?"
    fi
}
