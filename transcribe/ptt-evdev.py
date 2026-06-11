#!/usr/bin/env python3
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownParameterType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportMissingTypeArgument=false
# pyright: reportMissingImports=false
# (evdev has no type stubs — relax unknown-type rules for this file)
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

import logging
import os
import select
import signal
import subprocess
import sys
import time

import evdev
from evdev import InputDevice, KeyEvent, ecodes

# Seconds between keyboard re-scans (picks up hotplugged/re-enumerated
# devices and recovers if all keyboards have gone away).
RESCAN_SECS = 5

# Logs to stderr; when run as a systemd --user service this is captured
# by the journal (journalctl --user -u ptt-evdev).
log = logging.getLogger("ptt-evdev")

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


def find_keyboards() -> list[InputDevice]:
    """Find all keyboard input devices.

    Skips devices that vanish mid-scan: during a USB re-enumerate a path
    from list_devices() can disappear before InputDevice() opens it, which
    would otherwise raise OSError and crash the daemon.
    """
    keyboards: list[InputDevice] = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities(verbose=False)
        except OSError:
            log.debug(f"skipping {path} (vanished mid-scan)", exc_info=True)
            continue
        if ecodes.EV_KEY in caps:
            keys = caps[ecodes.EV_KEY]
            if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                keyboards.append(dev)
    return keyboards


def ptt_start() -> subprocess.Popen[bytes]:
    """Launch ptt-start.sh in the background."""
    return subprocess.Popen(
        [PTT_START],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ptt_stop() -> None:
    """Launch ptt-stop.sh in the background."""
    subprocess.Popen(
        [PTT_STOP],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def kill_start_proc(proc: subprocess.Popen[bytes] | None) -> None:
    """Terminate a running ptt-start.sh process."""
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait()


def close_keyboards(keyboards: list[InputDevice]) -> None:
    """Close all keyboard devices, logging any already-gone fds."""
    for kb in keyboards:
        try:
            kb.close()
        except OSError:
            log.debug(f"error closing {kb.path}", exc_info=True)


def monitor(test_mode: bool = False) -> None:
    """Monitor keyboards for Ctrl+Menu press/release.

    Survives keyboard unplug/re-enumeration: a dead device fd is dropped
    and keyboards are periodically re-discovered, so the daemon no longer
    dies on a USB replug or resume-from-suspend.
    """
    ctrl_held = False
    menu_held = False
    combo_active = False
    start_proc: subprocess.Popen[bytes] | None = None
    keyboards: list[InputDevice] = []

    def shutdown(*_: object) -> None:
        kill_start_proc(start_proc)
        close_keyboards(keyboards)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    mode = "TEST" if test_mode else "DAEMON"
    known_paths: set[str] = set()

    while True:
        keyboards, known_paths = _rediscover_keyboards(
            keyboards, known_paths, mode
        )

        if not keyboards:
            log.warning(f"no keyboards found; re-scanning in {RESCAN_SECS}s")
            time.sleep(RESCAN_SECS)
            continue

        try:
            r, _, _ = select.select(keyboards, [], [], RESCAN_SECS)
        except OSError:
            log.warning("select() failed; rediscovering keyboards",
                        exc_info=True)
            keyboards = []
            continue

        for dev in r:
            try:
                events = list(dev.read())
            except OSError:
                # Device went away (unplug/re-enumerate). Log the error,
                # reset combo state, drop the dead fd, and rediscover.
                log.warning(
                    f"read from {dev.path} failed (device unplug/"
                    f"re-enumerate?); recovering",
                    exc_info=True,
                )
                if combo_active and not test_mode:
                    kill_start_proc(start_proc)
                    start_proc = None
                    ptt_stop()
                ctrl_held = menu_held = combo_active = False
                keyboards = []
                break

            for event in events:
                if event.type != ecodes.EV_KEY:
                    continue

                key = event.code
                value = event.value

                if key in (KEY_CTRL_L, KEY_CTRL_R, KEY_MENU):
                    log.debug(
                        f"key={key} value={value} dev={dev.path} "
                        f"ctrl={ctrl_held} menu={menu_held}"
                    )

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
                    log.info("PTT START (Ctrl+Menu pressed)")
                    if not test_mode:
                        start_proc = ptt_start()

                # Detect combo release: either key released
                if combo_active and not (ctrl_held and menu_held):
                    combo_active = False
                    log.info("PTT STOP (Ctrl+Menu released)")
                    if not test_mode:
                        kill_start_proc(start_proc)
                        start_proc = None
                        ptt_stop()


def main() -> None:
    """Listen for PTT hotkey events and trigger recording."""
    level = logging.DEBUG if os.environ.get("PTT_DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    test_mode = "--test" in sys.argv

    if not find_keyboards():
        log.error(
            "no keyboard devices found; add your user to the input "
            "group and re-login"
        )
        sys.exit(1)

    monitor(test_mode=test_mode)


def _rediscover_keyboards(
    keyboards: list[InputDevice], known_paths: set[str], mode: str
) -> tuple[list[InputDevice], set[str]]:
    """Re-open keyboards when the device set changed or we have none.

    Returns the refreshed (keyboards, known_paths). This is where the
    daemon recovers from a USB replug/re-enumerate: stale fds are closed
    and the current devices re-opened.
    """
    current_paths = set(evdev.list_devices())
    if keyboards and current_paths == known_paths:
        return keyboards, known_paths

    close_keyboards(keyboards)
    keyboards = find_keyboards()
    if keyboards:
        names = ", ".join(f"{kb.path} ({kb.name})" for kb in keyboards)
        log.info(f"[{mode}] monitoring {len(keyboards)} keyboard(s): {names}")
    return keyboards, current_paths


if __name__ == "__main__":
    main()
