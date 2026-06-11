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
# the background and prints its PID to stdout. ffmpeg stderr goes to
# log_file if given; otherwise it is routed to the journal via logger
# (tagged with LOG_TAG) so failures are never silently discarded.
record_audio() {
    local source_dev="$1"
    local output="$2"
    local max_secs="${3:-}"
    local log_file="${4:-}"
    local duration_args=()
    if [[ -n "$max_secs" ]]; then
        duration_args=(-t "$max_secs")
    fi

    log_info "record_audio: device=$source_dev output=$output"

    local ff=(ffmpeg -nostdin -hide_banner -loglevel warning -nostats
        -f pulse -i "$source_dev" "${duration_args[@]}"
        -ac 1 -ar 16000 -sample_fmt s16 -y "$output")
    local pid
    if [[ -n "$log_file" ]]; then
        "${ff[@]}" </dev/null &>"$log_file" &
        pid=$!
    else
        "${ff[@]}" </dev/null >/dev/null \
            2> >(logger -t "${LOG_TAG:-record}" -p user.err) &
        pid=$!
    fi

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
# finalises the WAV header, then polls until it exits (force-killing if it
# overstays). ffmpeg is usually launched in a subshell so it is NOT a child
# of the caller; `wait` would fail instantly and we would read a half-written
# file, so we poll on kill -0 instead.
stop_recording() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null || return 0
    kill -INT "$pid" 2>/dev/null
    local i
    for ((i = 0; i < 50; i++)); do
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.1
    done
    kill -KILL "$pid" 2>/dev/null
}
