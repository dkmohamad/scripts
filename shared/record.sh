#!/usr/bin/env bash
# record.sh - Shared audio recording functions (ffmpeg + PulseAudio)
#
# Source this file after env.sh to get recording helpers.
# All functions produce mono 16 kHz 16-bit signed WAV output.
#
# Usage:
#   source "$SHARED_DIR/record.sh"
#   pid=$(record_audio "$(pactl get-default-source)" /tmp/mic.wav 60)
#   stop_recording "$pid"

# Ensure dependencies are available
require_command ffmpeg
require_command pactl "sudo apt install pulseaudio-utils"

# record_audio <pulse_source> <output_file> [max_secs] [log_file]
#
# Record from a PulseAudio source/monitor device. Launches ffmpeg in
# the background and prints its PID to stdout. ffmpeg stderr is sent
# to log_file (defaults to /dev/null).
record_audio() {
    local source_dev="$1"
    local output="$2"
    local max_secs="${3:-}"
    local log_file="${4:-/dev/null}"
    local duration_args=()
    if [[ -n "$max_secs" ]]; then
        duration_args=(-t "$max_secs")
    fi

    log_info "record_audio: device=$source_dev output=$output"

    ffmpeg -nostdin -f pulse -i "$source_dev" \
        "${duration_args[@]}" \
        -ac 1 -ar 16000 -sample_fmt s16 -y "$output" \
        </dev/null &>"$log_file" &
    local pid=$!

    sleep 0.3
    if ! kill -0 "$pid" 2>/dev/null; then
        log_error "record_audio: ffmpeg failed (device=$source_dev)"
        return 1
    fi
    echo "$pid"
}

# stop_recording <pid>
#
# Gracefully stop an ffmpeg recording process. Sends SIGINT so ffmpeg
# finalises the file header, then waits for exit.
stop_recording() {
    local pid="$1"
    if kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid" 2>/dev/null
        wait "$pid" 2>/dev/null || true
    fi
}
