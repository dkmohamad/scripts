#!/usr/bin/env bash
# _stop.sh - Stop ffmpeg recording processes
#
# Usage: _stop.sh <mic_pid> [sys_pid]
# Sends SIGINT to ffmpeg processes, waits for clean exit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="recorder"
source "$SCRIPT_DIR/../shared/env.sh"

if [[ $# -lt 1 ]]; then
    echo "Usage: _stop.sh <mic_pid> [sys_pid]" >&2
    exit 1
fi

failed=0

for pid in "$@"; do
    if kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid"
        log_info "Sent SIGINT to pid $pid"
    else
        log_warn "PID $pid already exited"
        failed=1
    fi
done

for pid in "$@"; do
    wait "$pid" 2>/dev/null || true
done

# Tear down the echo-canceller enabled by _record_meeting.sh and restore the
# real default devices. Safe no-op if AEC was never turned on.
"$SCRIPT_DIR/audio-setup.sh" off

exit $failed
