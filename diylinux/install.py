"""Install orchestrator: profile -> disk -> backend steps, with progress events.

Usable from the TUI (callbacks) or standalone:  diylinux-install profile.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Callable

from . import capabilities, disk, hw, releases
from .backends import get as get_backend
from .profile import Profile
from .run import CommandError, set_logger


@dataclass
class Event:
    kind: str            # step | log | done | error
    text: str
    index: int = 0
    total: int = 0


def run_install(profile: Profile, emit: Callable[[Event], None]) -> bool:
    problems = capabilities.validate(profile)
    if problems:
        emit(Event("error", "profile is not installable:\n  " + "\n  ".join(problems)))
        return False
    set_logger(lambda m: emit(Event("log", m)))
    layout = None
    try:
        # disk first, then the backend pipeline
        from . import __version__
        emit(Event("log", f"DIY Linux {__version__} ({hw.arch()})"))
        # newest release of the chosen base (network); the TUI may have done this already
        emit(Event("log", releases.status(profile.base) or releases.resolve(profile.base)))
        emit(Event("step", "Preparing disk", 1, 10))
        layout = disk.prepare(profile.disk, profile.bootloader)
        backend = get_backend(profile, layout, hw.arch())
        steps = backend.steps()
        total = len(steps) + 1
        for i, (title, fn) in enumerate(steps, start=2):
            emit(Event("step", title, i, total))
            fn()
        disk.unmount_all(layout)
        emit(Event("done", f"{backend.cap['meta']['name']} is installed on {profile.disk.device or profile.disk.root_partition}. Remove the USB stick and reboot."))
        return True
    except CommandError as e:
        emit(Event("error", str(e)))
    except Exception as e:  # noqa: BLE001
        emit(Event("error", f"{e}\n{traceback.format_exc()}"))
    try:
        if layout:
            disk.unmount_all(layout)
    except Exception:  # noqa: BLE001
        pass
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run an diylinux install from a saved profile (no TUI).")
    ap.add_argument("profile")
    ap.add_argument("--json", action="store_true", help="emit JSON lines instead of text")
    a = ap.parse_args(argv)
    profile = Profile.load(a.profile)

    def emit(ev: Event) -> None:
        if a.json:
            print(json.dumps(ev.__dict__), flush=True)
        elif ev.kind == "step":
            print(f"\n==> [{ev.index}/{ev.total}] {ev.text}", flush=True)
        elif ev.kind == "log":
            print(ev.text, flush=True)
        else:
            print(f"\n{ev.kind.upper()}: {ev.text}", flush=True)

    ok = run_install(profile, emit)
    if ok and profile.after in ("reboot", "poweroff") and not os.environ.get("DIYLINUX_DRYRUN"):
        os.system(f"systemctl {profile.after}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
