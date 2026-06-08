#!/usr/bin/env bash
# _record_meeting.sh - Dual-track recording (mic + system audio)
#
# Usage: _record_meeting.sh <session_dir> [max_secs]
# Launches ffmpeg for mic + system, prints JSON to stdout:
#   {"mic_pid": N, "sys_pid": N}

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

source_dev="$(pactl get-default-source)"
sink_dev="$(pactl get-default-sink).monitor"
mic_file="$session_dir/$MIC_FILE"
sys_file="$session_dir/$SYS_FILE"

log_info "Starting meeting recording: mic=$source_dev system=$sink_dev"

mic_pid=$(record_audio "$source_dev" "$mic_file" "$max_secs" \
    "$session_dir/ffmpeg-mic.log") || {
    echo "Failed to start mic recording." >&2
    exit 1
}
sys_pid=$(record_audio "$sink_dev" "$sys_file" "$max_secs" \
    "$session_dir/ffmpeg-sys.log") || {
    echo "Failed to start system audio recording." >&2
    kill "$mic_pid" 2>/dev/null || true
    exit 1
}

echo "{\"mic_pid\": $mic_pid, \"sys_pid\": $sys_pid}"
