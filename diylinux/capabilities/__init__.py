"""Per-base capability matrices (TOML). Everything distro-specific that is *data* lives here."""
from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib import resources
from typing import Any

BASES = ["arch", "debian", "ubuntu", "fedora", "opensuse"]


@lru_cache
def load(base: str) -> dict[str, Any]:
    with resources.files(__package__).joinpath(f"{base}.toml").open("rb") as f:
        return tomllib.load(f)


def all_bases() -> dict[str, dict[str, Any]]:
    return {b: load(b) for b in BASES}


def options(base: str, step: str) -> dict[str, dict[str, Any]]:
    """Options the base supports for a step, as {id: {label, packages, services, ...}}."""
    return load(base).get(step, {})


def validate(profile) -> list[str]:
    """Return a list of human readable problems. Empty list means the profile is installable."""
    from ..profile import OPTION_STEPS
    problems: list[str] = []
    if profile.base not in BASES:
        return [f"unknown base '{profile.base}'"]
    cap = load(profile.base)
    for step, _ in OPTION_STEPS:
        choice = getattr(profile, step)
        if choice not in cap.get(step, {}):
            problems.append(f"{profile.base} does not support {step}={choice}")
    if profile.disk.filesystem not in cap["disk"]["filesystems"]:
        problems.append(f"{profile.base} does not support filesystem {profile.disk.filesystem}")
    d = profile.disk
    if not d.manual:
        if not d.device:
            problems.append("no target disk selected")
    else:
        if not d.esp_partition:
            problems.append("manual partitioning needs an EFI system partition")
        if not d.root_partition:
            problems.append("manual partitioning needs a root partition")
        chosen = [x for x in (d.esp_partition, d.root_partition, d.boot_partition, d.swap_partition, d.home_partition) if x]
        if len(set(chosen)) != len(chosen):
            problems.append("the same partition is selected for two purposes")
        if d.encrypt and not d.boot_partition:
            problems.append("encryption needs a separate unencrypted /boot partition in manual mode")
        if profile.bootloader == "systemd-boot" and d.boot_partition:
            problems.append("systemd-boot mounts the EFI partition at /boot: do not pick a separate /boot partition")
    if profile.disk.encrypt and not profile.disk.passphrase:
        problems.append("encryption enabled but no passphrase")
    if not profile.username:
        problems.append("no user name")
    if not profile.password:
        problems.append("no user password")
    if profile.power == "tlp" and profile.desktop in ("gnome", "kde") and "ppd" in cap.get("power", {}):
        # Not an error, but worth knowing: GNOME/KDE integrate with power-profiles-daemon.
        pass
    return problems
