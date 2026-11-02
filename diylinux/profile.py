"""The neutral install profile: everything the TUI asks, in one JSON document."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROFILE_VERSION = 1

# Question steps, in the order the TUI asks them. Each maps to a capability table.
OPTION_STEPS = [
    ("bootloader", "Bootloader"),
    ("desktop", "Desktop environment / window manager"),
    ("graphics", "Graphics driver"),
    ("power", "Power management"),
    ("firewall", "Firewall"),
    ("audio", "Audio"),
    ("network", "Network manager"),
]


@dataclass
class DiskPlan:
    device: str = ""            # e.g. /dev/nvme0n1
    mode: str = "wipe"          # wipe (erase the disk, partition automatically) | manual (use my partitions)
    filesystem: str = "ext4"    # ext4 | btrfs | xfs, for the root filesystem
    encrypt: bool = False       # LUKS2 on root; manual mode needs a separate /boot partition for this
    passphrase: str = ""
    swap_gb: int = 0            # wipe/guided mode: swap partition size, 0 = none
    esp_size_mb: int = 512     # guided mode: EFI system partition size in MiB
    boot_size_mb: int = 1024   # guided mode: separate /boot size in MiB (0 = none)
    # manual mode: existing partitions (made with cfdisk or any other tool)
    esp_partition: str = ""     # required; vfat, type "EFI System"
    root_partition: str = ""    # required; always formatted with `filesystem`
    boot_partition: str = ""    # optional separate /boot (ext4, formatted); required with encryption
    swap_partition: str = ""    # optional
    home_partition: str = ""    # optional, mounted at /home
    format_esp: bool = True     # false keeps other bootloaders already on the ESP (dual boot)
    format_home: bool = False   # false keeps the data on the /home partition

    @property
    def manual(self) -> bool:
        # "existing" from older profiles means the same thing as manual
        return self.mode not in ("wipe", "guided")


@dataclass
class Profile:
    version: int = PROFILE_VERSION
    base: str = ""              # arch | debian | ubuntu | fedora | opensuse
    disk: DiskPlan = field(default_factory=DiskPlan)
    bootloader: str = "grub"
    desktop: str = "gnome"
    graphics: str = "mesa"
    power: str = "ppd"
    firewall: str = "none"
    audio: str = "pipewire"
    network: str = "networkmanager"
    hostname: str = "diylinux"
    username: str = ""
    password: str = ""
    root_password: str = ""      # empty = root locked, user has sudo
    locale: str = "en_US.UTF-8"
    keymap: str = "us"           # console keymap (vconsole.conf)
    xkb_layout: str = ""         # keyboard layout for X11/Wayland; empty = derived from keymap
    timezone: str = "UTC"
    mirror: str = ""             # empty = distro default
    secure_boot_acknowledged: bool = False
    after: str = "stay"          # unattended runs: stay | reboot | poweroff

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Profile":
        d = dict(d)
        disk = d.pop("disk", {}) or {}
        p = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        p.disk = DiskPlan(**{k: v for k, v in disk.items() if k in DiskPlan.__dataclass_fields__})
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def redacted(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("password", "root_password"):
            if d.get(k):
                d[k] = "********"
        if d["disk"].get("passphrase"):
            d["disk"]["passphrase"] = "********"
        return d
