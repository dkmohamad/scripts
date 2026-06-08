#!/usr/bin/env bash
# ptt-start.sh - Start PTT voice recording
#
# Called on hotkey press. Acquires lock, starts recording, and holds lock
# until killed by ptt-stop.sh. Only one recording/transcription can run at
# a time due to the exclusive lock.

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
source "$SHARED_DIR/record.sh"

if ! acquire_lock; then
  log_info "START skipped (operation in progress)"
  exit 0
fi

# Kill any stray recorder and clean up
if [[ -f "$PIDFILE" ]]; then
  stop_recording "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
fi
rm -f "$TMP"

start_timer

# Start recording (safety limit from env.sh)
FFMPEG_PID=$(record_audio "$(pactl get-default-source)" "$TMP" "$MAX_RECORD_SECS")
echo "$FFMPEG_PID" > "$PIDFILE"

log_info "START pid=$FFMPEG_PID"

# Wait for ffmpeg - keeps lock held until ptt-stop kills us
wait "$FFMPEG_PID"
