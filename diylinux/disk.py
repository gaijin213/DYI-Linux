"""Partitioning, formatting, LUKS and mounting. Produces a Layout the backends consume."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from .profile import DiskPlan
from .run import DRY, log, run

TARGET = "/mnt/diy-linux"
BTRFS_SUBVOLS = {"@": "/", "@home": "/home", "@log": "/var/log", "@snapshots": "/.snapshots"}


@dataclass
class Layout:
    esp: str                     # partition device
    boot: str                    # separate /boot partition (GRUB bases); "" when ESP is mounted at /boot (systemd-boot)
    root: str                    # partition device (LUKS container if encrypted)
    root_mapper: str             # /dev/mapper/cryptroot or same as root
    filesystem: str
    swap: str = ""
    luks_uuid: str = ""
    root_uuid: str = ""
    esp_uuid: str = ""
    boot_uuid: str = ""
    swap_uuid: str = ""
    home: str = ""               # separate /home partition (manual mode only)
    home_uuid: str = ""
    home_fstype: str = ""
    esp_mount: str = "/boot/efi"
    mountpoints: dict[str, str] = field(default_factory=dict)  # mountpoint -> device


def _part(dev: str, n: int) -> str:
    return f"{dev}p{n}" if dev[-1].isdigit() else f"{dev}{n}"


def _uuid(dev: str) -> str:
    if DRY:
        return f"UUID-OF-{os.path.basename(dev)}"
    return subprocess.run(["blkid", "-s", "UUID", "-o", "value", dev], capture_output=True, text=True).stdout.strip()


def _settle() -> None:
    run(["udevadm", "settle"], check=False, quiet=True)


def prepare(plan: DiskPlan, bootloader: str = "grub") -> Layout:
    """Partition (wipe mode), encrypt, format and mount everything under TARGET.

    wipe + GRUB:          ESP 512M (/boot/efi) + /boot 1G ext4 + [swap] + root
    wipe + systemd-boot:  ESP 1G (/boot) + [swap] + root
    manual:               the partitions named in the plan; root (and /boot if given) are formatted,
                          the ESP only when plan.format_esp, /home only when plan.format_home
    """
    separate_boot = bootloader == "grub"
    boot = home = ""
    format_esp = format_home = True
    if not plan.manual:
        if plan.mode == "guided":
            esp, boot, root, swap = _guided_partition(plan, separate_boot)
        else:
            esp, boot, root, swap = _wipe_and_partition(plan, separate_boot)
    else:
        esp, root, swap, home = plan.esp_partition, plan.root_partition, plan.swap_partition, plan.home_partition
        boot = plan.boot_partition
        format_esp, format_home = plan.format_esp, plan.format_home
        log(f"manual layout: ESP={esp} ({'format' if format_esp else 'keep'}) root={root} (format {plan.filesystem})"
            + (f" boot={boot} (format ext4)" if boot else "") + (f" swap={swap}" if swap else "")
            + (f" home={home} ({'format' if format_home else 'keep'})" if home else ""))
        for dev in (esp, root, boot, swap, home):
            if dev:
                run(["umount", dev], check=False, quiet=True)
        if boot:
            separate_boot = True
    _settle()

    root_dev = root
    luks_uuid = ""
    if plan.encrypt:
        log("setting up LUKS2 on root")
        run(["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--key-file", "-", root],
            input=plan.passphrase)
        run(["cryptsetup", "open", "--key-file", "-", root, "cryptroot"], input=plan.passphrase)
        luks_uuid = _uuid(root)
        root_dev = "/dev/mapper/cryptroot"

    if format_esp:
        run(["mkfs.vfat", "-F", "32", "-n", "EFI", esp])
    elif not DRY and _fstype(esp) != "vfat":
        raise RuntimeError(f"{esp} is not a FAT filesystem; tick 'format the EFI partition' or format it yourself")
    if boot:
        run(["mkfs.ext4", "-F", "-L", "boot", boot])
    _mkfs(plan.filesystem, root_dev, "root")
    if home and format_home:
        _mkfs(plan.filesystem, home, "home")
    if swap:
        run(["mkswap", "-L", "swap", swap])
    _settle()

    lay = Layout(esp=esp, boot=boot, root=root, root_mapper=root_dev, filesystem=plan.filesystem, swap=swap,
                 luks_uuid=luks_uuid, root_uuid=_uuid(root_dev), esp_uuid=_uuid(esp),
                 boot_uuid=_uuid(boot) if boot else "", swap_uuid=_uuid(swap) if swap else "",
                 home=home, home_uuid=_uuid(home) if home else "",
                 home_fstype=(plan.filesystem if format_home else _fstype(home)) if home else "",
                 esp_mount="/boot/efi" if separate_boot else "/boot")
    mount_all(lay)
    return lay


def _mkfs(fs: str, dev: str, label: str) -> None:
    if fs == "ext4":
        run(["mkfs.ext4", "-F", "-L", label, dev])
    elif fs == "xfs":
        run(["mkfs.xfs", "-f", "-L", label, dev])
    elif fs == "btrfs":
        run(["mkfs.btrfs", "-f", "-L", label, dev])
    else:
        raise ValueError(fs)


def _fstype(dev: str) -> str:
    if DRY:
        return "ext4"
    return subprocess.run(["blkid", "-s", "TYPE", "-o", "value", dev], capture_output=True, text=True).stdout.strip()


def _subvols(lay: Layout) -> dict[str, str]:
    """btrfs subvolumes to create; @home is skipped when a separate /home partition exists."""
    return {sv: mp for sv, mp in BTRFS_SUBVOLS.items() if not (lay.home and mp == "/home")}


def _guided_partition(plan: DiskPlan, separate_boot: bool) -> tuple[str, str, str, str]:
    """Guided mode: wipe the disk and create partitions with user-chosen sizes (ESP, /boot, swap, rest=root)."""
    dev = plan.device
    esp_size_mb = max(64, int(plan.esp_size_mb or 512))
    boot_size_mb = max(0, int(plan.boot_size_mb or 0))
    log(f"wiping {dev} and creating GPT: ESP {esp_size_mb}M, "
        + (f"/boot {boot_size_mb}M, " if (separate_boot and boot_size_mb) else "")
        + (f"swap {plan.swap_gb}G, " if plan.swap_gb else "") + "root (rest)")
    run(["wipefs", "-a", dev])
    run(["sgdisk", "--zap-all", dev])
    cmd = ["sgdisk", "-n", f"1:0:+{esp_size_mb}M", "-t", "1:ef00", "-c", "1:EFI"]
    n = 2
    boot = ""
    if separate_boot and boot_size_mb:
        cmd += ["-n", f"{n}:0:+{boot_size_mb}M", "-t", f"{n}:ea00", "-c", f"{n}:boot"]
        boot = _part(dev, n)
        n += 1
    if plan.swap_gb:
        cmd += ["-n", f"{n}:0:+{plan.swap_gb}G", "-t", f"{n}:8200", "-c", f"{n}:swap"]
        n += 1
    cmd += ["-n", f"{n}:0:0", "-t", f"{n}:8304" if not plan.encrypt else f"{n}:8309", "-c", f"{n}:root", dev]
    run(cmd)
    run(["partprobe", dev], check=False)
    _settle()
    esp = _part(dev, 1)
    swap = _part(dev, n - 1) if plan.swap_gb else ""
    root = _part(dev, n)
    return esp, boot, root, swap


def _wipe_and_partition(plan: DiskPlan, separate_boot: bool) -> tuple[str, str, str, str]:
    dev = plan.device
    log(f"wiping {dev} and creating GPT: ESP, {'/boot, ' if separate_boot else ''}{'swap, ' if plan.swap_gb else ''}root")
    run(["wipefs", "-a", dev])
    run(["sgdisk", "--zap-all", dev])
    esp_size = "+512M" if separate_boot else "+1G"
    cmd = ["sgdisk", "-n", f"1:0:{esp_size}", "-t", "1:ef00", "-c", "1:EFI"]
    n = 2
    boot = ""
    if separate_boot:
        cmd += ["-n", f"{n}:0:+1G", "-t", f"{n}:ea00", "-c", f"{n}:boot"]
        boot = _part(dev, n)
        n += 1
    if plan.swap_gb:
        cmd += ["-n", f"{n}:0:+{plan.swap_gb}G", "-t", f"{n}:8200", "-c", f"{n}:swap"]
        n += 1
    cmd += ["-n", f"{n}:0:0", "-t", f"{n}:8304" if not plan.encrypt else f"{n}:8309", "-c", f"{n}:root", dev]
    run(cmd)
    run(["partprobe", dev], check=False)
    _settle()
    esp = _part(dev, 1)
    swap = _part(dev, n - 1) if plan.swap_gb else ""
    root = _part(dev, n)
    return esp, boot, root, swap


def mount_all(lay: Layout) -> None:
    run(["mkdir", "-p", TARGET])
    if lay.filesystem == "btrfs":
        run(["mount", lay.root_mapper, TARGET])
        for sv in _subvols(lay):
            run(["btrfs", "subvolume", "create", f"{TARGET}/{sv}"])
        run(["umount", TARGET])
        opts = "compress=zstd:1,noatime"
        for sv, mp in _subvols(lay).items():
            target = TARGET + mp.rstrip("/")
            run(["mkdir", "-p", target])
            run(["mount", "-o", f"{opts},subvol={sv}", lay.root_mapper, target])
            lay.mountpoints[mp] = lay.root_mapper
    else:
        run(["mount", lay.root_mapper, TARGET])
        lay.mountpoints["/"] = lay.root_mapper
    if lay.home:
        run(["mkdir", "-p", f"{TARGET}/home"])
        run(["mount", lay.home, f"{TARGET}/home"])
        lay.mountpoints["/home"] = lay.home
    if lay.boot:
        run(["mkdir", "-p", f"{TARGET}/boot"])
        run(["mount", lay.boot, f"{TARGET}/boot"])
        lay.mountpoints["/boot"] = lay.boot
    run(["mkdir", "-p", f"{TARGET}{lay.esp_mount}"])
    run(["mount", lay.esp, f"{TARGET}{lay.esp_mount}"])
    lay.mountpoints[lay.esp_mount] = lay.esp
    if lay.swap:
        run(["swapon", lay.swap], check=False)


def fstab(lay: Layout) -> str:
    lines = ["# generated by diylinux", "# <device>  <mount>  <type>  <options>  <dump> <pass>"]
    if lay.filesystem == "btrfs":
        for sv, mp in _subvols(lay).items():
            lines.append(f"UUID={lay.root_uuid}  {mp}  btrfs  compress=zstd:1,noatime,subvol={sv}  0 0")
    else:
        lines.append(f"UUID={lay.root_uuid}  /  {lay.filesystem}  defaults,noatime  0 1")
    if lay.home:
        opts = "compress=zstd:1,noatime" if lay.home_fstype == "btrfs" else "defaults,noatime"
        lines.append(f"UUID={lay.home_uuid}  /home  {lay.home_fstype or 'auto'}  {opts}  0 2")
    if lay.boot:
        lines.append(f"UUID={lay.boot_uuid}  /boot  ext4  defaults,noatime  0 2")
    lines.append(f"UUID={lay.esp_uuid}  {lay.esp_mount}  vfat  umask=0077  0 2")
    if lay.swap:
        lines.append(f"UUID={lay.swap_uuid}  none  swap  sw  0 0")
    return "\n".join(lines) + "\n"


def unmount_all(lay: Layout | None = None) -> None:
    run(["umount", "-R", TARGET], check=False)
    if lay and lay.luks_uuid:
        run(["cryptsetup", "close", "cryptroot"], check=False)
    if lay and lay.swap:
        run(["swapoff", lay.swap], check=False)
