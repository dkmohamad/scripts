#!/usr/bin/env bash
# ptt-stop.sh - Stop recording and transcribe
#
# Called on hotkey release. Stops recording, acquires lock, transcribes
# audio with whisper.cpp, and types the result into the focused window.

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
source "$SHARED_DIR/record.sh"

# Stop the recording (harmless if not running)
if [[ -f "$PIDFILE" ]]; then
  stop_recording "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
fi

# Acquire lock (waits if ptt-start is still cleaning up)
if ! acquire_lock; then
  acquire_lock_wait 2 || {
    log_info "STOP skipped (lock timeout)"
    exit 0
  }
fi

DURATION=$(get_duration)

# Check for valid audio
if [ ! -s "$TMP" ]; then
  log_info "STOP duration=${DURATION}s (no audio file)"
  exit 0
fi

# Get actual file size in bytes
SIZE_BYTES=$(stat -c%s "$TMP" 2>/dev/null || echo 0)
SIZE=$(du -h "$TMP" | cut -f1)

# WAV header is 44 bytes; at 16kHz 16-bit mono, meaningful audio needs more
# Anything under ~1000 bytes is basically empty (header + minimal data)
if [ "$SIZE_BYTES" -lt 1000 ]; then
  log_error "STOP dur=${DURATION}s size=${SIZE_BYTES}B (empty recording)"
  rm -f "$TMP"
  exit 0
fi
log_info "STOP dur=${DURATION}s size=${SIZE} mem=$(get_mem_avail) gpu=$(get_gpu_mem)"

# Transcribe with timeout (VAD filters trailing silence to prevent hallucinations)
WHISPER_START=$(date +%s.%N)
RAW=$(timeout "$WHISPER_TIMEOUT" "$WHISPER_BIN" \
  -m "$WHISPER_MODEL" -f "$TMP" -np -nt -sns \
  --vad -vm "$VAD_MODEL" 2>/dev/null)
WHISPER_EXIT=$?
WHISPER_TIME=$(echo "$(date +%s.%N) - $WHISPER_START" | bc | xargs printf "%.1f")

if [ $WHISPER_EXIT -eq 124 ]; then
  log_error "WHISPER timeout after ${WHISPER_TIMEOUT}s"
  exit 1
elif [ $WHISPER_EXIT -ne 0 ]; then
  log_error "WHISPER exit=${WHISPER_EXIT} time=${WHISPER_TIME}s (failed)"
  exit 1
fi

log_info "WHISPER exit=0 time=${WHISPER_TIME}s"

# Clean up text: strip control chars (Ctrl+C/D/Z, ESC, etc.) that whisper may
# hallucinate and xdotool would send as keypresses, killing the terminal session
TEXT=$(echo "$RAW" \
  | tr '\n\r\t' ' ' \
  | tr -d '[:cntrl:]' \
  | tr -s ' ' \
  | sed 's/^ *//; s/ *$//')

if [ -n "$TEXT" ]; then
  # Write to temp file for xdotool (handles special chars like apostrophes)
  printf '%s ' "$TEXT" > "$TMP_TEXT"
  xdotool type --clearmodifiers --delay "$XDOTOOL_DELAY" --file "$TMP_TEXT"
  log_info "TYPED chars=${#TEXT}"
else
  log_info "TYPED chars=0 (empty)"
fi
