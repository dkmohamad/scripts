#!/usr/bin/env bash
# record.sh - Record both sides of a call from the Linux desktop
#
# Captures system audio (speaker) and microphone as separate WAV tracks
# at 16kHz mono, suitable for Whisper transcription.
#
# Usage:
#   record.sh start [output_dir]   Start recording (default: ~/Recordings)
#   record.sh stop                 Stop recording
#   record.sh status               Check if recording is in progress

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/../shared"
LOG_TAG="recorder"
source "$SHARED_DIR/env.sh"

META_FILE="/tmp/recorder.meta"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

require_recording() {
    if [[ ! -f "$META_FILE" ]]; then
        echo "No recording in progress." >&2
        exit 1
    fi
}

human_duration() {
    local secs="$1"
    printf "%02d:%02d:%02d" \
        $((secs / 3600)) $(((secs % 3600) / 60)) $((secs % 60))
}

human_size() {
    numfmt --to=iec-i --suffix=B "$1"
}

# ------------------------------------------------------------------
# start [output_dir]
# ------------------------------------------------------------------

cmd_start() {
    if [[ -f "$META_FILE" ]]; then
        echo "Recording already in progress (see: record.sh status)" >&2
        exit 1
    fi

    require_command ffmpeg
    require_command pactl "sudo apt install pulseaudio-utils"

    local output_dir="${1:-$HOME/Recordings}"
    mkdir -p "$output_dir"

    local sink source ts mic_file sys_file
    sink="$(pactl get-default-sink).monitor"
    source="$(pactl get-default-source)"
    ts="$(datestamp)"
    mic_file="$output_dir/meeting-${ts}-mic.wav"
    sys_file="$output_dir/meeting-${ts}-system.wav"

    log_info "Starting recording: mic=$source system=$sink"

    # Launch ffmpeg for mic
    ffmpeg -nostdin -f pulse -i "$source" \
        -ac 1 -ar 16000 -sample_fmt s16 -y "$mic_file" \
        </dev/null 2> >(logger -t "$LOG_TAG" -p user.debug) &
    local mic_pid=$!

    # Launch ffmpeg for system audio
    ffmpeg -nostdin -f pulse -i "$sink" \
        -ac 1 -ar 16000 -sample_fmt s16 -y "$sys_file" \
        </dev/null 2> >(logger -t "$LOG_TAG" -p user.debug) &
    local sys_pid=$!

    # Verify processes started
    sleep 0.5
    if ! kill -0 "$mic_pid" 2>/dev/null; then
        echo "Failed to start mic recording." >&2
        kill "$sys_pid" 2>/dev/null || true
        exit 1
    fi
    if ! kill -0 "$sys_pid" 2>/dev/null; then
        echo "Failed to start system audio recording." >&2
        kill "$mic_pid" 2>/dev/null || true
        exit 1
    fi

    # Persist state
    cat > "$META_FILE" <<EOF
MIC_PID=$mic_pid
SYS_PID=$sys_pid
MIC_FILE=$mic_file
SYS_FILE=$sys_file
START_EPOCH=$(date +%s)
EOF

    log_info "Recording started (mic_pid=$mic_pid sys_pid=$sys_pid)"
    echo "Recording started."
    echo "  Mic:    $mic_file (pid $mic_pid)"
    echo "  System: $sys_file (pid $sys_pid)"
}

# ------------------------------------------------------------------
# stop
# ------------------------------------------------------------------

cmd_stop() {
    require_recording
    source "$META_FILE"

    log_info "Stopping recording"

    # Send SIGINT so ffmpeg finalises WAV headers
    local failed=0
    for pid in "$MIC_PID" "$SYS_PID"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -INT "$pid"
        else
            log_warn "PID $pid already exited"
            failed=1
        fi
    done

    # Wait for processes to finish
    wait "$MIC_PID" 2>/dev/null || true
    wait "$SYS_PID" 2>/dev/null || true

    rm -f "$META_FILE"

    local now duration
    now=$(date +%s)
    duration=$((now - START_EPOCH))

    echo "Recording stopped."
    echo "  Duration: $(human_duration "$duration")"
    for f in "$MIC_FILE" "$SYS_FILE"; do
        if [[ -f "$f" ]]; then
            echo "  $(basename "$f"): $(human_size "$(stat -c%s "$f")")"
        else
            echo "  $(basename "$f"): MISSING" >&2
            failed=1
        fi
    done

    if [[ "$failed" -eq 0 ]]; then
        local dir
        dir="$(dirname "$MIC_FILE")"
        echo ""
        echo "Transcribe with:"
        echo "  transcribe/transcribe-meeting.sh \"$dir\""
    fi

    log_info "Recording stopped (duration=${duration}s)"
}

# ------------------------------------------------------------------
# status
# ------------------------------------------------------------------

cmd_status() {
    if [[ ! -f "$META_FILE" ]]; then
        echo "No recording in progress."
        return
    fi

    source "$META_FILE"

    local now duration mic_alive sys_alive
    now=$(date +%s)
    duration=$((now - START_EPOCH))
    mic_alive="dead"
    sys_alive="dead"
    kill -0 "$MIC_PID" 2>/dev/null && mic_alive="running"
    kill -0 "$SYS_PID" 2>/dev/null && sys_alive="running"

    echo "Recording in progress: $(human_duration "$duration")"
    echo "  Mic:    $MIC_FILE (pid $MIC_PID, $mic_alive)"
    echo "  System: $SYS_FILE (pid $SYS_PID, $sys_alive)"
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

case "${1:-}" in
    start)  cmd_start "${2:-}" ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    *)
        echo "Usage: record.sh {start [output_dir]|stop|status}" >&2
        exit 1
        ;;
esac
