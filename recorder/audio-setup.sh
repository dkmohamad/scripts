#!/usr/bin/env bash
# audio-setup.sh - Toggle a WebRTC echo-cancelled mic for clean lesson capture.
#
# On open speakers the far-end (teacher) plays into the room and the webcam mic
# re-captures it, so mic.wav ends up containing both voices. This loads
# PipeWire's module-echo-cancel (the same WebRTC AEC the browser uses on its
# uplink) to subtract the played far-end from the mic, leaving your voice.
#
# It creates two virtual nodes:
#   echo-cancel-source  - your mic, echo-cancelled  (recorded as mic.wav)
#   echo-cancel-sink    - far-end plays here; its .monitor is the clean teacher
#                         track (recorded as system.wav)
# makes them the defaults, and moves any already-playing streams onto the sink
# so the canceller has its reference. `capture start` then records both clean
# tracks with no extra steps (it reads pactl get-default-source / -sink.monitor).
#
# The recorder calls this automatically: `capture start` runs `on`, `capture
# stop` runs `off`. So the mic is only held open (and the AEC only active) for
# the duration of a recording - no always-on background processing. You can
# also run it by hand for debugging:
#   audio-setup.sh on | off | status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="recorder"
source "$SCRIPT_DIR/../shared/env.sh"
# Capture-device overrides (MIC_DEVICE / OUTPUT_SINK) live here.
source "$SCRIPT_DIR/config"

# Fixed module-echo-cancel identifiers (not user config): the virtual node
# names we pass to load-module, plus the media.name PipeWire assigns the
# module's own playback stream (which _move_inputs_to must never relocate).
SOURCE_NAME="echo-cancel-source"
SINK_NAME="echo-cancel-sink"
AEC_PLAYBACK_NAME="Echo-Cancel Playback"
STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/recorder-aec.state"

# ===== Public commands ======================================================

# cmd_on: load the canceller and route audio through it.
# Loads module-echo-cancel (unless already loaded), makes the virtual nodes the
# defaults so the recorder and new app streams use them automatically, and pulls
# already-playing audio onto the sink so it forms the AEC reference. Saves the
# real defaults first so `off` can restore exactly what was there.
cmd_on() {
    if _aec_loaded; then
        log_info "Echo-cancel already loaded; ensuring defaults are set."
    else
        # Devices and canceller format are pinned in config for this machine
        # (MIC_DEVICE / OUTPUT_SINK / AEC_*), verified once via
        # _aec_loopback_test.sh. The format is set explicitly rather than via
        # use_master_format=1 so the canceller's node shape is deterministic.
        # (The HDMI-muting bug itself is fixed in _move_inputs_to, which no
        # longer relocates the module's own playback stream.) Headphones are
        # intentionally unsupported — set OUTPUT_SINK to the headphone sink if
        # you ever switch.
        if [[ -z "$MIC_DEVICE" || -z "$OUTPUT_SINK" ]]; then
            log_error "MIC_DEVICE and OUTPUT_SINK must be set in recorder/config."
            exit 1
        fi

        # Save the real defaults so `off` restores exactly what was there.
        local real_src real_sink
        real_src="$(pactl get-default-source)"
        real_sink="$(pactl get-default-sink)"
        printf 'REAL_SOURCE=%s\nREAL_SINK=%s\n' "$real_src" "$real_sink" \
            >"$STATE_FILE"

        log_info "Loading module-echo-cancel (webrtc): mic=$MIC_DEVICE sink=$OUTPUT_SINK rate=$AEC_RATE ch=$AEC_CHANNELS fmt=$AEC_FORMAT"
        pactl load-module module-echo-cancel \
            aec_method=webrtc \
            source_name="$SOURCE_NAME" \
            sink_name="$SINK_NAME" \
            source_master="$MIC_DEVICE" \
            sink_master="$OUTPUT_SINK" \
            rate="$AEC_RATE" \
            channels="$AEC_CHANNELS" \
            format="$AEC_FORMAT" >/dev/null
    fi

    pactl set-default-source "$SOURCE_NAME"
    pactl set-default-sink "$SINK_NAME"
    _move_inputs_to "$SINK_NAME"

    # Basic check only: the canceller's sink must have come up, else tear down
    # and fail loud rather than hand back a muted default. The full audio
    # passthrough check lives in recorder/_aec_loopback_test.sh (run it after
    # changing devices/format in config).
    if ! pactl list short sinks | awk '{print $2}' | grep -qxF "$SINK_NAME"; then
        log_error "echo-cancel sink '$SINK_NAME' did not come up; tearing down."
        cmd_off
        exit 1
    fi

    log_info "AEC active. Default mic=$SOURCE_NAME, default sink=$SINK_NAME."
}

# cmd_off: tear the canceller down and restore the real devices. Safe no-op
# when AEC was never turned on, so the recorder can call it unconditionally on
# stop.
cmd_off() {
    # Nothing to undo if AEC was never turned on.
    if ! _aec_loaded && [[ ! -f "$STATE_FILE" ]]; then
        return 0
    fi

    # Recover the real devices cmd_on saved; fall back to hardware if the state
    # file is gone (e.g. a module left loaded after a crash).
    local real_src real_sink
    if [[ -f "$STATE_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$STATE_FILE"
    fi
    real_src="${REAL_SOURCE:-$(_first_real_source)}"
    real_sink="${REAL_SINK:-$(_first_real_sink)}"

    # Restore the defaults, pull any streams back onto the real sink, unload.
    pactl set-default-sink "$real_sink" 2>/dev/null || true
    pactl set-default-source "$real_src" 2>/dev/null || true
    _move_inputs_to "$real_sink"
    local id
    for id in $(_aec_module_ids); do
        pactl unload-module "$id" 2>/dev/null || true
    done
    rm -f "$STATE_FILE"

    log_info "AEC off. Default mic=$real_src, sink=$real_sink."
}

# cmd_status: report whether AEC is loaded and what the current defaults are.
# For eyeballing state when debugging by hand.
cmd_status() {
    if _aec_loaded; then
        echo "echo-cancel: LOADED (module id $(_aec_module_ids | tr '\n' ' '))"
    else
        echo "echo-cancel: not loaded"
    fi
    echo "default source: $(pactl get-default-source)"
    echo "default sink:   $(pactl get-default-sink)"
}

# ===== Private helpers ======================================================

# _aec_module_ids: print the module id(s) of any loaded recorder echo-cancel
# instance, one per line. Matches on our source_name so we never touch an
# unrelated module-echo-cancel the user may have loaded themselves.
_aec_module_ids() {
    pactl list short modules \
        | awk -v s="source_name=$SOURCE_NAME" '$0 ~ s { print $1 }'
}

# _aec_loaded: true if our echo-cancel module is currently loaded.
_aec_loaded() {
    [[ -n "$(_aec_module_ids)" ]]
}

# _first_real_sink: print the first non-virtual hardware sink. Used as a
# fallback restore target when the saved state file is missing.
_first_real_sink() {
    pactl list short sinks | awk '$2 !~ /echo-cancel/ { print $2; exit }'
}

# _first_real_source: print the first real (non-virtual, non-monitor) source.
# Fallback restore target when the saved state file is missing.
_first_real_source() {
    pactl list short sources \
        | awk '$2 !~ /echo-cancel/ && $2 !~ /\.monitor$/ { print $2; exit }'
}

# _move_inputs_to <sink>: move active playback streams onto <sink>, EXCEPT the
# canceller's own "Echo-Cancel Playback" stream. That stream's job is to carry
# the far-end to sink_master (the real speakers); moving it onto the echo-cancel
# sink loops it back and silently mutes output — this was the HDMI-muting bug.
# On `on` this pulls already-playing app audio through the canceller as its
# reference; on `off` it pushes apps back out to the real sink.
_move_inputs_to() {
    local target="$1" sid aec_ids
    aec_ids=" $(_aec_playback_input_ids | tr '\n' ' ')"
    for sid in $(pactl list sink-inputs short | awk '{print $1}'); do
        [[ "$aec_ids" == *" $sid "* ]] && continue
        pactl move-sink-input "$sid" "$target" 2>/dev/null || true
    done
}

# _aec_playback_input_ids: print the pactl sink-input id(s) of the canceller's
# own playback stream (media.name = AEC_PLAYBACK_NAME), one per line. Empty if
# AEC is not loaded. _move_inputs_to skips these so it never relocates the
# stream that feeds the far-end to the real speakers.
_aec_playback_input_ids() {
    pactl list sink-inputs | awk -v want="media.name = \"$AEC_PLAYBACK_NAME\"" '
        /^Sink Input #/ { id = substr($3, 2) }
        index($0, want) { print id }
    '
}

# ===== Entry point ==========================================================

main() {
    local action="${1:-on}"
    case "$action" in
        on)     cmd_on ;;
        off)    cmd_off ;;
        status) cmd_status ;;
        *)
            echo "Usage: audio-setup.sh {on|off|status}" >&2
            exit 1
            ;;
    esac
}

main "$@"
