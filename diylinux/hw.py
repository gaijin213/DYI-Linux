"""Hardware facts the TUI needs: Secure Boot state, firmware mode, disks, CPU arch."""
from __future__ import annotations

import glob
import json
import os
import platform
import subprocess
from dataclasses import dataclass

from .run import DRY


@dataclass
class Disk:
    path: str
    size_bytes: int
    model: str
    transport: str
    removable: bool

    @property
    def size_human(self) -> str:
        n = float(self.size_bytes)
        for unit in ("B", "K", "M", "G", "T"):
            if n < 1024 or unit == "T":
                return f"{n:.0f}{unit}" if unit in "BKM" else f"{n:.1f}{unit}"
            n /= 1024
        return f"{n:.1f}T"


def arch() -> str:
    m = platform.machine()
    return {"arm64": "aarch64", "AMD64": "x86_64"}.get(m, m)


def is_uefi() -> bool:
    return DRY or os.path.isdir("/sys/firmware/efi")


def secure_boot_enabled() -> bool | None:
    """True/False from the firmware variable, None if unknown (no UEFI, or non-Linux dry run)."""
    if os.environ.get("DIYLINUX_FAKE_SECUREBOOT"):
        return os.environ["DIYLINUX_FAKE_SECUREBOOT"] == "1"
    matches = glob.glob("/sys/firmware/efi/efivars/SecureBoot-*")
    if not matches:
        return None
    try:
        with open(matches[0], "rb") as f:
            data = f.read()
        return len(data) >= 5 and data[4] == 1
    except OSError:
        return None


def live_device() -> str:
    """Block device the live medium is mounted from, so we can hide it from the disk list."""
    try:
        out = subprocess.run(["findmnt", "-no", "SOURCE", "/run/live/medium"], capture_output=True, text=True)
        src = out.stdout.strip()
        if src.startswith("/dev/"):
            pk = subprocess.run(["lsblk", "-no", "PKNAME", src], capture_output=True, text=True).stdout.strip()
            return f"/dev/{pk}" if pk else src
    except FileNotFoundError:
        pass
    return ""


def disks() -> list[Disk]:
    if DRY or platform.system() != "Linux":
        return [
            Disk("/dev/nvme0n1", 1_000_204_886_016, "Samsung SSD 980 PRO 1TB", "nvme", False),
            Disk("/dev/sda", 500_107_862_016, "CT500MX500SSD1", "sata", False),
            Disk("/dev/sdb", 61_530_439_680, "SanDisk Ultra USB", "usb", True),
        ]
    out = subprocess.run(["lsblk", "-J", "-b", "-d", "-o", "PATH,SIZE,MODEL,TRAN,RM,TYPE"],
                         capture_output=True, text=True, check=True).stdout
    live = live_device()
    result = []
    for d in json.loads(out)["blockdevices"]:
        if d.get("type") != "disk" or d["path"] == live:
            continue
        if d["path"].startswith(("/dev/loop", "/dev/zram", "/dev/sr")):
            continue
        result.append(Disk(d["path"], int(d["size"] or 0), (d.get("model") or "").strip(),
                           d.get("tran") or "", bool(d.get("rm"))))
    return result


def partitions(disk: str) -> list[dict]:
    """Partitions of a disk: path, size, fstype, parttype (human name), label, mountpoint."""
    if DRY or platform.system() != "Linux":
        return [{"path": f"{disk}p1", "size": "512M", "fstype": "vfat", "parttype": "EFI System", "label": "EFI", "mountpoint": ""},
                {"path": f"{disk}p2", "size": "1G", "fstype": "ext4", "parttype": "Linux extended boot", "label": "boot", "mountpoint": ""},
                {"path": f"{disk}p3", "size": "8G", "fstype": "swap", "parttype": "Linux swap", "label": "", "mountpoint": ""},
                {"path": f"{disk}p4", "size": "300G", "fstype": "ext4", "parttype": "Linux root (x86-64)", "label": "", "mountpoint": ""},
                {"path": f"{disk}p5", "size": "620G", "fstype": "", "parttype": "Linux filesystem", "label": "", "mountpoint": ""}]
    out = subprocess.run(["lsblk", "-J", "-o", "NAME,PATH,SIZE,FSTYPE,TYPE,PARTTYPENAME,LABEL,MOUNTPOINT", disk],
                         capture_output=True, text=True).stdout
    try:
        devs = json.loads(out).get("blockdevices", []) or []
        children = list(devs)
        for d in devs:
            children.extend(d.get("children", []) or [])
    except (ValueError, IndexError, KeyError):
        return []
    return [{"path": c["path"], "size": c.get("size") or "", "fstype": c.get("fstype") or "",
             "parttype": c.get("parttypename") or "", "label": c.get("label") or "", "mountpoint": c.get("mountpoint") or ""}
            for c in children if c.get("type") == "part"]


def partition_label(p: dict) -> str:
    """One line for the pickers: /dev/sda1  512M  vfat  EFI System  [EFI]."""
    bits = [p["path"], p["size"], p["fstype"] or "(empty)", p["parttype"]]
    if p.get("label"):
        bits.append(f"[{p['label']}]")
    return "  ".join(b for b in bits if b)


def rescan(disk: str) -> None:
    """Make the kernel re-read the partition table after an external editor (cfdisk) changed it."""
    if DRY or platform.system() != "Linux":
        return
    import time
    subprocess.run(["partprobe", disk], capture_output=True)
    subprocess.run(["blockdev", "--rereadpt", disk], capture_output=True)
    subprocess.run(["partx", "-u", disk], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)
    time.sleep(0.3)
    subprocess.run(["udevadm", "settle"], capture_output=True)


def has_network() -> bool:
    if DRY:
        return True
    try:
        r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=2)
        if r.stdout.strip():
            return True
        a = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global", "up"], capture_output=True, text=True, timeout=2)
        if a.stdout.strip():
            return True
    except Exception:
        pass
    try:
        import socket
        socket.create_connection(("deb.debian.org", 443), timeout=2).close()
        return True
    except OSError:
        return False
