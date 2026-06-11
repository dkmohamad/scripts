#!/bin/bash
# ptt-setup.sh - Install and (re)start the PTT systemd user service.
#
# Generates the ptt-evdev systemd --user unit, enables it so it starts at
# login, and restarts it now. The service has Restart=always and the daemon
# survives keyboard unplug/re-enumerate, so PTT no longer dies on a USB
# replug or resume-from-suspend (it just logs and recovers). View its logs
# with: journalctl --user -u ptt-evdev -f
#
# Requires input group membership (sudo usermod -aG input $USER).

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

VENV_PYTHON="$SCRIPT_DIR/../.venv/bin/python"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/ptt-evdev.service"

mkdir -p "$UNIT_DIR"
cat >"$UNIT" <<EOF
[Unit]
Description=PTT (push-to-talk) evdev hotkey daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
# Clear stale recorder and lock/temp files left by a previous crash.
ExecStartPre=-/usr/bin/pkill -f ffmpeg.*whisper_ptt.wav
ExecStartPre=-/usr/bin/rm -f $LOCKFILE $TMP $TMP_TEXT $TIMEFILE $PIDFILE
ExecStart=$VENV_PYTHON $SCRIPT_DIR/ptt-evdev.py
Restart=always
RestartSec=2

[Install]
WantedBy=graphical-session.target
EOF

# Stop any daemon started the old way (manual background launch).
pkill -f "ptt-evdev.py" 2>/dev/null

# NOTE: the old xbindkeys hotkey mechanism must be disabled by hand - if
# xbindkeys is still bound to Ctrl+Menu in ~/.xbindkeysrc it fires
# ptt-start.sh on every key-repeat and fights this daemon over the lock,
# producing empty recordings. See transcribe/README.md.

systemctl --user daemon-reload
systemctl --user enable ptt-evdev.service
systemctl --user restart ptt-evdev.service

log_info "PTT service installed and (re)started"
systemctl --user --no-pager status ptt-evdev.service | head -6
