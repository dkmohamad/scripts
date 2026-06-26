#!/usr/bin/env bash
# _aec_loopback_test.sh - Regression test for the echo-canceller passthrough.
#
# The far-end (teacher) must keep reaching the real speakers while AEC is
# active. A past bug muted it: _move_inputs_to moved the canceller's own
# "Echo-Cancel Playback" stream onto the echo-cancel sink, so audio reached the
# recording tee but never the speakers.
#
# This loads AEC via audio-setup.sh, plays a test tone through the canceller,
# and measures whether it reaches BOTH the recording tee (control) and the real
# output sink (passthrough). Run it once after changing MIC_DEVICE/OUTPUT_SINK
# or the AEC_* format in config. AEC is always torn down on exit.
#
# Usage: _aec_loopback_test.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="recorder"
source "$SCRIPT_DIR/../shared/env.sh"
source "$SCRIPT_DIR/config"

require_command ffmpeg
require_command paplay
require_command parec

OUT="${OUTPUT_SINK:?set OUTPUT_SINK in recorder/config}"
TMP="$(mktemp -d)"
TONE="$TMP/tone.wav"
PIDS=()

cleanup() {
    for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
    "$SCRIPT_DIR/audio-setup.sh" off >/dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap cleanup EXIT

ffmpeg -y -f lavfi -i "sine=frequency=440:duration=3" -ar 48000 -ac 2 \
    "$TONE" -loglevel error </dev/null

"$SCRIPT_DIR/audio-setup.sh" on </dev/null

# Drive the capture side like the real recorder, and capture both the real
# output's monitor (passthrough) and the canceller's monitor (control).
parec -d echo-cancel-source --rate=48000 --channels=2 --format=s16le \
    >/dev/null </dev/null & PIDS+=($!)
parec -d "${OUT}.monitor" --rate=48000 --channels=2 --format=s16le \
    >"$TMP/out.raw" </dev/null & PIDS+=($!)
parec -d "echo-cancel-sink.monitor" --rate=48000 --channels=2 --format=s16le \
    >"$TMP/ctl.raw" </dev/null & PIDS+=($!)

paplay "$TONE" </dev/null
kill "${PIDS[@]}" 2>/dev/null || true
wait 2>/dev/null || true

# mean_volume in dB (defaulting silence to a clearly-failing floor).
vol() {
    local v
    v="$(ffmpeg -f s16le -ar 48000 -ac 2 -i "$1" -af volumedetect -f null - \
        </dev/null 2>&1 | awk -F': ' '/mean_volume/{gsub(/ dB/,"",$2); print $2}')"
    [[ -z "$v" || "$v" == *inf* ]] && v="-99"
    printf '%s' "$v"
}

ctl="$(vol "$TMP/ctl.raw")"
out="$(vol "$TMP/out.raw")"
log_info "control (echo-cancel-sink.monitor): ${ctl} dB"
log_info "passthrough (${OUT}.monitor):        ${out} dB"

# Pass if the speaker output is within ~10 dB of the recording tee (audio is
# actually flowing); fail loud if it is effectively silent.
if awk -v o="$out" -v c="$ctl" 'BEGIN { exit !(o > c - 10) }'; then
    log_info "PASS: far-end reaches the speakers."
else
    log_error "FAIL: far-end is NOT reaching the speakers (passthrough muted)."
    exit 1
fi
