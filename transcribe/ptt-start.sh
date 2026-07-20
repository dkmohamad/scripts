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
# record_audio routes ffmpeg stderr to the journal (tag whisper-ptt). It writes
# the ffmpeg PID straight to PIDFILE - no command substitution to capture it,
# which could hang and orphan ffmpeg (see shared/record.sh).
if ! record_audio "$(pactl get-default-source)" "$TMP" "$PIDFILE" \
  "$MAX_RECORD_SECS"; then
  log_error "START failed (ffmpeg did not start)"
  exit 1
fi
FFMPEG_PID=$(cat "$PIDFILE")

log_info "START pid=$FFMPEG_PID"

# Hold the lock until recording stops. ffmpeg is now a child of this shell
# (record_audio ran in-process, not a subshell), so wait for it directly -
# this also reaps it, avoiding a zombie that a kill -0 poll would spin on
# forever. ptt-stop kills ffmpeg on release (or it self-stops at
# MAX_RECORD_SECS), and the daemon SIGTERMs us on release too - either way the
# wait returns and the lock is released.
wait "$FFMPEG_PID" 2>/dev/null
