#!/usr/bin/env bash
# record.sh - Shared audio recording functions (ffmpeg + PulseAudio)
#
# Source this file after env.sh to get recording helpers.
# All functions produce mono 16 kHz 16-bit signed WAV output.
#
# Usage:
#   source "$SHARED_DIR/record.sh"
#   record_audio "$(pactl get-default-source)" /tmp/mic.wav /tmp/mic.pid 60
#   record_mixed "$mic_src" "$sys_src" /tmp/mix.wav /tmp/mix.pid 60
#   stop_recording "$(cat /tmp/mic.pid)"
#
# The recorders write the ffmpeg PID to a caller-supplied file rather than
# echoing it for a command substitution to capture - see _spawn_ffmpeg.

# Ensure dependencies are available
require_command ffmpeg
require_command pactl "sudo apt install pulseaudio-utils"

# record_audio <pulse_source> <output_file> <pidfile> [max_secs] [log_file]
#
# Record from a single PulseAudio source/monitor device. Launches ffmpeg in
# the background and writes its PID to <pidfile>. Returns non-zero if ffmpeg
# fails to start.
record_audio() {
    local source_dev="$1"
    local output="$2"
    local pidfile="$3"
    local max_secs="${4:-}"
    local log_file="${5:-}"
    local duration_args=()
    if [[ -n "$max_secs" ]]; then
        duration_args=(-t "$max_secs")
    fi

    log_info "record_audio: device=$source_dev output=$output"

    _spawn_ffmpeg "$pidfile" "$log_file" "record_audio (device=$source_dev)" \
        ffmpeg -nostdin -hide_banner -loglevel warning -nostats \
        -f pulse -i "$source_dev" "${duration_args[@]}" \
        -ac 1 -ar 16000 -sample_fmt s16 -y "$output"
}

# record_mixed <src1> <src2> <out> <pidfile> [max_secs] [log_file]
#
# Record TWO PulseAudio sources in a SINGLE ffmpeg process and mix them down to
# one mono file. One process opening both inputs keeps them aligned, then amix
# sums them into a single track - so a meeting (you + far-end) is captured as
# one clean mixed recording that goes straight to transcription. Writes the PID
# to <pidfile>.
#
# normalize=0 keeps each source at full level (turn-taking means little overlap;
# switch to amix's default normalisation if double-talk ever clips).
record_mixed() {
    local src1="$1" src2="$2" out="$3" pidfile="$4"
    local max_secs="${5:-}" log_file="${6:-}"
    local duration_args=()
    if [[ -n "$max_secs" ]]; then
        duration_args=(-t "$max_secs")
    fi

    log_info "record_mixed: $src1 + $src2 -> $out"

    _spawn_ffmpeg "$pidfile" "$log_file" "record_mixed" \
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
# overstays). Callers stop an ffmpeg started by a DIFFERENT process (e.g.
# ptt-stop.sh stops the recorder ptt-start.sh launched), so ffmpeg is not the
# caller's child and `wait` would fail instantly; poll on kill -0 instead.
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

# _spawn_ffmpeg <pidfile> <log_file> <label> <ffmpeg> [args...]
#
# Launch an ffmpeg command in the background, route its stderr to log_file (or
# the journal via logger when no log_file is given, so failures are never
# silently discarded), write its PID to <pidfile>, confirm it survived startup,
# and return 0. Shared by record_audio and record_mixed so the
# background/logging/health-check logic lives in exactly one place.
#
# The PID goes to a file rather than stdout on purpose: when the caller used a
# command substitution to capture an echoed PID, the logger process
# substitution above could inherit and hold that $()-capture pipe open for the
# entire recording, so the substitution never saw EOF. The caller hung with the
# lock held, the PID was never recorded, and ffmpeg was orphaned until its
# safety cap - wedging push-to-talk until a manual restart. Writing the PID to
# a file lets callers invoke the recorders without a command substitution.
_spawn_ffmpeg() {
    local pidfile="$1" log_file="$2" label="$3"
    shift 3
    local pid
    if [[ -n "$log_file" ]]; then
        "$@" </dev/null &>"$log_file" &
        pid=$!
    else
        "$@" </dev/null >/dev/null \
            2> >(logger -t "${LOG_TAG:-record}" -p user.err) &
        pid=$!
    fi
    # Fail loud if the PID can't be recorded: the caller drives stop/wait off
    # this file, so a silent write failure (read-only or full target, a stale
    # root-owned pidfile) would leave ffmpeg orphaned and the caller acting on
    # a bogus PID. Kill the ffmpeg we just started rather than leak it.
    if ! echo "$pid" >"$pidfile"; then
        log_error "$label: could not write PID to $pidfile"
        kill "$pid" 2>/dev/null
        rm -f "$pidfile"
        return 1
    fi

    sleep 0.3
    if ! kill -0 "$pid" 2>/dev/null; then
        log_error "$label: ffmpeg failed to start"
        rm -f "$pidfile"
        return 1
    fi
}
