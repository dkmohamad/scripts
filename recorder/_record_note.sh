#!/usr/bin/env bash
# _record_note.sh - Mic-only recording (voice notes, journal entries)
#
# Usage: _record_note.sh <session_dir>
# Launches ffmpeg for mic, prints JSON to stdout:
#   {"mic_pid": N}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="recorder"
source "$SCRIPT_DIR/../shared/env.sh"
source "$SCRIPT_DIR/config"

if [[ $# -lt 1 ]]; then
    echo "Usage: _record_note.sh <session_dir> [max_secs]" >&2
    exit 1
fi

session_dir="$1"
max_secs="${2:-}"
duration_args=()
if [[ -n "$max_secs" ]]; then
    duration_args=(-t "$max_secs")
fi
mkdir -p "$session_dir"

require_command ffmpeg
require_command pactl "sudo apt install pulseaudio-utils"

source_dev="$(pactl get-default-source)"
mic_file="$session_dir/$MIC_FILE"

log_info "Starting note recording: mic=$source_dev"

ffmpeg -nostdin -f pulse -i "$source_dev" \
    "${duration_args[@]}" \
    -ac 1 -ar 16000 -sample_fmt s16 -y "$mic_file" \
    </dev/null &>"$session_dir/ffmpeg-mic.log" &
mic_pid=$!

sleep 0.5
if ! kill -0 "$mic_pid" 2>/dev/null; then
    echo "Failed to start mic recording." >&2
    exit 1
fi

echo "{\"mic_pid\": $mic_pid}"
