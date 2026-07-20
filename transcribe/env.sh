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
PIDFILE=/tmp/whisper_ptt.pid

# Timeouts (seconds)
MAX_RECORD_SECS=120
WHISPER_TIMEOUT=30

# xdotool typing delay (ms between keystrokes). Higher values prevent crashes
# in some terminal apps (e.g., Claude CLI's React UI with rapid input).
XDOTOOL_DELAY=5

# ydotool per-key timing (ms), applied as BOTH --key-hold (down->up) and
# --key-delay (between keys). ydotool defaults each to 20ms, so leaving them
# unset costs ~40ms/char - the dominant typing latency. The Wayland path uses
# the vendored ydotool client talking to a persistent ydotoold daemon (see
# ptt-setup.sh), which holds one long-lived uinput keyboard the compositor
# enumerates once, so no device-settle delay is needed either. 0 = type as
# fast as the daemon can inject; raise it only if a target app (e.g. the
# Claude CLI React UI) drops characters on rapid input.
YDOTOOL_KEY_DELAY=0
YDOTOOL_BIN="$VENDOR_DIR/ydotool/build/ydotool"
YDOTOOLD_BIN="$VENDOR_DIR/ydotool/build/ydotoold"

# Socket shared by the ydotool client and the ydotoold daemon. The daemon unit
# (ptt-setup.sh) binds it at %t/$YDOTOOL_SOCKET_NAME, where systemd's %t is the
# user runtime dir - i.e. $XDG_RUNTIME_DIR. Deriving both sides from this one
# name keeps them from drifting. No /tmp fallback: if XDG_RUNTIME_DIR is unset
# the socket path won't resolve and type_text fails loud rather than typing
# into a socket the daemon isn't listening on.
YDOTOOL_SOCKET_NAME=".ydotool_socket"
export YDOTOOL_SOCKET="${XDG_RUNTIME_DIR}/${YDOTOOL_SOCKET_NAME}"

# Whisper paths
WHISPER_BIN="$VENDOR_DIR/whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL="$VENDOR_DIR/whisper.cpp/models/ggml-base.en.bin"
WHISPER_MODEL_MULTI="$VENDOR_DIR/whisper.cpp/models/ggml-large-v3.bin"
VAD_MODEL="$VENDOR_DIR/whisper.cpp/models/ggml-silero-v6.2.0.bin"

# Transcribe a WAV file with whisper.cpp. Raw output on stdout.
whisper_transcribe() {
    "$WHISPER_BIN" \
        -m "$WHISPER_MODEL" -f "$1" -np -nt -sns \
        --vad -vm "$VAD_MODEL" 2> >(tee >(logger -t "$LOG_TAG" -p user.err) >&2)
}

# Transcribe a WAV file with the multilingual model (auto-detects language).
whisper_transcribe_multi() {
    "$WHISPER_BIN" \
        -m "$WHISPER_MODEL_MULTI" -f "$1" -np -nt -sns \
        --language auto -mc 0 \
        --vad -vm "$VAD_MODEL" 2> >(tee >(logger -t "$LOG_TAG" -p user.err) >&2)
}

# ------------------------------------------------------------------------------
# Typing
# ------------------------------------------------------------------------------

# Type the contents of a file into the focused window. Dispatches on session
# type: xdotool's XTEST events only reach X11/XWayland apps, so Wayland needs
# ydotool (kernel-level uinput injection). Returns non-zero on unknown session
# type or tool failure.
type_text() {
    local file="$1"
    case "${XDG_SESSION_TYPE:-}" in
        wayland)
            if [[ ! -S "$YDOTOOL_SOCKET" ]]; then
                log_error "type_text: ydotoold socket missing at \
'$YDOTOOL_SOCKET' (is ydotoold.service running?)"
                return 1
            fi
            # --escape 0: type text literally (don't interpret backslashes),
            # matching xdotool's behaviour on the X11 path.
            "$YDOTOOL_BIN" type --key-hold "$YDOTOOL_KEY_DELAY" \
                --key-delay "$YDOTOOL_KEY_DELAY" --escape 0 --file "$file"
            ;;
        x11)
            xdotool type --clearmodifiers --delay "$XDOTOOL_DELAY" \
                --file "$file"
            ;;
        *)
            log_error "type_text: XDG_SESSION_TYPE='${XDG_SESSION_TYPE:-}' \
(expected wayland|x11)"
            return 1
            ;;
    esac
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
