#!/usr/bin/env bash
# _record_meeting.sh - Dual-track recording (mic + system audio)
#
# Usage: _record_meeting.sh <session_dir> [max_secs]
# Records mic + system in one ffmpeg process, prints JSON to stdout:
#   {"mic_pid": N, "output_port": "...", "headphones": bool, "aec": bool}
# (mic_pid is the single recorder process; it owns both output files.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="recorder"
source "$SCRIPT_DIR/../shared/env.sh"
source "$SHARED_DIR/record.sh"
source "$SCRIPT_DIR/config"

if [[ $# -lt 1 ]]; then
    echo "Usage: _record_meeting.sh <session_dir> [max_secs]" >&2
    exit 1
fi

session_dir="$1"
max_secs="${2:-}"
mkdir -p "$session_dir"

rec_file="$session_dir/$RECORDING_FILE"

# Detect the active output port of the default sink. Headphones/headset = no
# acoustic loop; speaker/HDMI/line-out = the far-end bleeds into the mic.
default_sink="$(pactl get-default-sink)"
active_port="$(pactl list sinks | awk -v want="$default_sink" '
    /^\tName: / { name = $2 }
    /^\tActive Port: / && name == want { print $3; exit }
')"
if [[ -z "$active_port" ]]; then
    # pactl failed or the sink reports no active port. Warn rather than
    # silently assume headphones (which would suppress the speaker warning).
    active_port="unknown"
    headphones=false
    log_warn "Could not read active output port for sink '$default_sink'"
else
    case "${active_port,,}" in
        *headphone*|*headset*) headphones=true ;;
        *)                     headphones=false ;;
    esac
fi
# Logged to the journal (tag: recorder) for debugging the detection itself.
log_info "Output: sink=$default_sink port=$active_port headphones=$headphones"

# Turn on live echo-cancellation for the duration of this recording: the mic is
# captured through a WebRTC canceller so the far-end (teacher) does not bleed
# into mic.wav, even on open speakers. _stop.sh turns it back off. We read the
# capture devices AFTER this, so they resolve to the echo-cancel virtual nodes.
# If it fails its own validation/startup checks it has already torn itself
# down; abort cleanly rather than record against the wrong devices.
"$SCRIPT_DIR/audio-setup.sh" on || {
    log_error "Failed to enable echo cancellation."
    "$SCRIPT_DIR/audio-setup.sh" off
    exit 1
}

source_dev="$(pactl get-default-source)"
sink_dev="$(pactl get-default-sink).monitor"

log_info "Starting meeting recording: mic=$source_dev system=$sink_dev"

# Record you + far-end mixed into one mono file in a single ffmpeg process, so
# both start together and land aligned in the mix. The single PID owns the file.
# record_mixed writes the PID to a file rather than echoing it for a command
# substitution to capture (which could hang - see shared/record.sh).
rec_pidfile="$session_dir/ffmpeg.pid"
record_mixed "$source_dev" "$sink_dev" "$rec_file" "$rec_pidfile" \
    "$max_secs" "$session_dir/ffmpeg.log" || {
    echo "Failed to start recording." >&2
    "$SCRIPT_DIR/audio-setup.sh" off
    exit 1
}
rec_pid=$(cat "$rec_pidfile")

echo "{\"mic_pid\": $rec_pid,\
 \"output_port\": \"$active_port\", \"headphones\": $headphones, \"aec\": true}"
