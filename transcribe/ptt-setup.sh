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

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VENV_PYTHON="$SCRIPT_DIR/../.venv/bin/python"

# Install and (re)start the ydotoold user service. The daemon holds one
# persistent uinput keyboard (socket at %t/$YDOTOOL_SOCKET_NAME, i.e.
# $XDG_RUNTIME_DIR/$YDOTOOL_SOCKET_NAME, matching YDOTOOL_SOCKET in env.sh) so
# the compositor enumerates the virtual keyboard once instead of racing a new
# device on every keystroke. Wayland only.
install_ydotoold_service() {
    local unit="$UNIT_DIR/ydotoold.service"
    mkdir -p "$UNIT_DIR"
    cat >"$unit" <<EOF
[Unit]
Description=ydotoold - persistent uinput device for ydotool typing
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$YDOTOOLD_BIN --socket-path=%t/$YDOTOOL_SOCKET_NAME --socket-perm=0600
Restart=always
RestartSec=2

[Install]
WantedBy=graphical-session.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable ydotoold.service
    systemctl --user restart ydotoold.service
}

# ptt-evdev [Unit] extra lines - on Wayland the typing path needs ydotoold up
# first, so make it a dependency. Left empty on X11 (xdotool needs no daemon).
PTT_UNIT_DEPS=""

# Validate the typing path for the current session before installing anything,
# so a broken environment fails here with a pointer instead of silently
# discarding transcriptions at dictation time. On Wayland this also installs
# the ydotoold daemon that holds the persistent uinput device.
case "${XDG_SESSION_TYPE:-}" in
    wayland)
        if [[ ! -x "$YDOTOOL_BIN" || ! -x "$YDOTOOLD_BIN" ]]; then
            echo "Error: vendored ydotool not built at $YDOTOOL_BIN." >&2
            echo "Fix: build it (Ubuntu's apt ydotool lacks ydotoold):" >&2
            echo "  cd $VENDOR_DIR/ydotool && cmake -B build -DBUILD_DOCS=OFF" \
                "-DCMAKE_BUILD_TYPE=Release && cmake --build build -j\$(nproc)" >&2
            exit 1
        fi
        if [[ ! -w /dev/uinput ]]; then
            echo "Error: /dev/uinput is not writable; ydotoold cannot type." >&2
            echo "Fix: add a udev rule granting the input group access:" >&2
            echo '  echo '\''KERNEL=="uinput", GROUP="input", MODE="0660",' \
                'OPTIONS+="static_node=uinput"'\'' |' \
                'sudo tee /etc/udev/rules.d/60-uinput-input-group.rules' >&2
            echo "  sudo udevadm control --reload-rules &&" \
                "sudo udevadm trigger --sysname-match=uinput" >&2
            echo "and ensure you are in the input group (re-login after)." >&2
            exit 1
        fi
        install_ydotoold_service
        PTT_UNIT_DEPS=$'Requires=ydotoold.service\nAfter=ydotoold.service'
        ;;
    x11)
        require_command xdotool "sudo apt install xdotool"
        ;;
    *)
        echo "Error: XDG_SESSION_TYPE='${XDG_SESSION_TYPE:-}' is neither" \
            "wayland nor x11; cannot pick a typing tool." >&2
        exit 1
        ;;
esac

UNIT="$UNIT_DIR/ptt-evdev.service"
mkdir -p "$UNIT_DIR"
cat >"$UNIT" <<EOF
[Unit]
Description=PTT (push-to-talk) evdev hotkey daemon
After=graphical-session.target
PartOf=graphical-session.target
$PTT_UNIT_DEPS

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
