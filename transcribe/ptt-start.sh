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

# Start recording (safety limit from env.sh). No log file is passed, so
# record_audio routes ffmpeg stderr to the journal (tag whisper-ptt).
FFMPEG_PID=$(record_audio "$(pactl get-default-source)" "$TMP" \
  "$MAX_RECORD_SECS")
echo "$FFMPEG_PID" > "$PIDFILE"

log_info "START pid=$FFMPEG_PID"

# Hold the lock until recording stops. ffmpeg runs in record_audio's
# subshell, so it is NOT our child and `wait` returns instantly ("not a
# child of this shell"); poll on kill -0 instead. ptt-stop kills ffmpeg on
# release (or it self-stops at MAX_RECORD_SECS), and the daemon SIGTERMs us
# on release too - either way the loop ends and the lock is released.
while kill -0 "$FFMPEG_PID" 2>/dev/null; do
  sleep 0.2
done
