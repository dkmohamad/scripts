#!/usr/bin/env bash
# record.sh - Shared audio recording functions (ffmpeg + PulseAudio)
#
# Source this file after env.sh to get recording helpers.
# All functions produce mono 16 kHz 16-bit signed WAV output.
#
# Usage:
#   source "$SHARED_DIR/record.sh"
#   pid=$(record_audio "$(pactl get-default-source)" /tmp/mic.wav 60)
#   pid=$(record_dual "$mic_src" /tmp/mic.wav "$sys_src" /tmp/sys.wav 60)
#   stop_recording "$pid"

# Ensure dependencies are available
require_command ffmpeg
require_command pactl "sudo apt install pulseaudio-utils"

# record_audio <pulse_source> <output_file> [max_secs] [log_file]
#
# Record from a single PulseAudio source/monitor device. Launches ffmpeg in
# the background and prints its PID to stdout.
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

    _spawn_ffmpeg "$log_file" "record_audio (device=$source_dev)" \
        ffmpeg -nostdin -hide_banner -loglevel warning -nostats \
        -f pulse -i "$source_dev" "${duration_args[@]}" \
        -ac 1 -ar 16000 -sample_fmt s16 -y "$output"
}

# record_mixed <src1> <src2> <out> [max_secs] [log_file]
#
# Record TWO PulseAudio sources in a SINGLE ffmpeg process and mix them down to
# one mono file. One process opening both inputs keeps them aligned, then amix
# sums them into a single track - so a meeting (you + far-end) is captured as
# one clean mixed recording that goes straight to transcription. Prints the PID.
#
# normalize=0 keeps each source at full level (turn-taking means little overlap;
# switch to amix's default normalisation if double-talk ever clips).
record_mixed() {
    local src1="$1" src2="$2" out="$3"
    local max_secs="${4:-}" log_file="${5:-}"
    local duration_args=()
    if [[ -n "$max_secs" ]]; then
        duration_args=(-t "$max_secs")
    fi

    log_info "record_mixed: $src1 + $src2 -> $out"

    _spawn_ffmpeg "$log_file" "record_mixed" \
        ffmpeg -nostdin -hide_banner -loglevel warning -nostats \
        -f pulse -i "$src1" -f pulse -i "$src2" \
        -filter_complex "[0:a][1:a]amix=inputs=2:normalize=0" \
        "${duration_args[@]}" \
        -ac 1 -ar 16000 -sample_fmt s16 -y "$out"
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

# -- Private helpers ---------------------------------------------------------

# _spawn_ffmpeg <log_file> <label> <ffmpeg> [args...]
#
# Launch an ffmpeg command in the background, route its stderr to log_file (or
# the journal via logger when no log_file is given, so failures are never
# silently discarded), confirm it survived startup, and print its PID. Shared
# by record_audio and record_dual so the background/logging/health-check logic
# lives in exactly one place.
_spawn_ffmpeg() {
    local log_file="$1" label="$2"
    shift 2
    local pid
    if [[ -n "$log_file" ]]; then
        "$@" </dev/null &>"$log_file" &
        pid=$!
    else
        "$@" </dev/null >/dev/null \
            2> >(logger -t "${LOG_TAG:-record}" -p user.err) &
        pid=$!
    fi

    sleep 0.3
    if ! kill -0 "$pid" 2>/dev/null; then
        log_error "$label: ffmpeg failed to start"
        return 1
    fi
    echo "$pid"
}
