#!/usr/bin/env python3
"""PTT evdev daemon - push-to-talk via Ctrl+Menu.

Monitors keyboard input devices for Ctrl+Menu press/release events and
calls ptt-start.sh / ptt-stop.sh accordingly. Detects release regardless
of modifier ordering (fixes the xbindkeys race condition where releasing
Ctrl before Menu drops the event).

Usage:
    ./ptt-evdev.py          # run in foreground
    ./ptt-evdev.py --test   # print events without calling scripts

Requires input group membership to read /dev/input/*.
"""

import os
import select
import signal
import subprocess
import sys

import evdev
from evdev import InputDevice, KeyEvent, ecodes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PTT_START = os.path.join(SCRIPT_DIR, "ptt-start.sh")
PTT_STOP = os.path.join(SCRIPT_DIR, "ptt-stop.sh")

# Keys to monitor
KEY_MENU = ecodes.KEY_COMPOSE  # 127 - Menu/Compose key
KEY_CTRL_L = ecodes.KEY_LEFTCTRL
KEY_CTRL_R = ecodes.KEY_RIGHTCTRL

# Key event values
KEY_DOWN = KeyEvent.key_down  # 1
KEY_UP = KeyEvent.key_up  # 0


def find_keyboards():
    """Find all keyboard input devices."""
    keyboards = []
    for path in evdev.list_devices():
        dev = InputDevice(path)
        caps = dev.capabilities(verbose=False)
        if ecodes.EV_KEY in caps:
            keys = caps[ecodes.EV_KEY]
            if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                keyboards.append(dev)
    return keyboards


def ptt_start():
    """Launch ptt-start.sh in the background."""
    return subprocess.Popen(
        [PTT_START],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ptt_stop():
    """Launch ptt-stop.sh in the background."""
    subprocess.Popen(
        [PTT_STOP],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def kill_start_proc(proc):
    """Terminate a running ptt-start.sh process."""
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait()


def monitor(keyboards, test_mode=False):
    """Monitor keyboards for Ctrl+Menu press/release."""
    ctrl_held = False
    menu_held = False
    combo_active = False
    start_proc = None

    def shutdown(*_):
        kill_start_proc(start_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    mode = "TEST" if test_mode else "DAEMON"
    print(f"[{mode}] Monitoring {len(keyboards)} keyboard(s):")
    for kb in keyboards:
        print(f"  {kb.path}: {kb.name}")
    print(flush=True)

    while True:
        r, _, _ = select.select(keyboards, [], [])
        for dev in r:
            for event in dev.read():
                if event.type != ecodes.EV_KEY:
                    continue

                key = event.code
                value = event.value

                # Track Ctrl state
                if key in (KEY_CTRL_L, KEY_CTRL_R):
                    if value == KEY_DOWN:
                        ctrl_held = True
                    elif value == KEY_UP:
                        ctrl_held = False

                # Track Menu state
                if key == KEY_MENU:
                    if value == KEY_DOWN:
                        menu_held = True
                    elif value == KEY_UP:
                        menu_held = False

                # Detect combo press: both keys now held
                if ctrl_held and menu_held and not combo_active:
                    combo_active = True
                    if test_mode:
                        print(">>> PTT START (Ctrl+Menu pressed)")
                    else:
                        start_proc = ptt_start()

                # Detect combo release: either key released
                if combo_active and not (ctrl_held and menu_held):
                    combo_active = False
                    if test_mode:
                        print(">>> PTT STOP  (Ctrl+Menu released)")
                    else:
                        kill_start_proc(start_proc)
                        start_proc = None
                        ptt_stop()


def main():
    test_mode = "--test" in sys.argv

    keyboards = find_keyboards()
    if not keyboards:
        print("No keyboard devices found.", file=sys.stderr)
        print(
            "Add your user to the input group and re-login.",
            file=sys.stderr,
        )
        sys.exit(1)

    monitor(keyboards, test_mode=test_mode)


if __name__ == "__main__":
    main()
