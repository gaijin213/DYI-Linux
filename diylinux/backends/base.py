"""Shared install pipeline. Subclasses only override what genuinely differs per distro."""
from __future__ import annotations

import os
import uuid
from typing import Any

from .. import capabilities, choices
from ..disk import TARGET, BTRFS_SUBVOLS, Layout, fstab
from ..profile import OPTION_STEPS, Profile
from ..run import DRY, log, run, write_file, append_file

ARCH_MAP = {
    # diylinux arch -> (debarch, fedora efiarch, suse arch, grub target, suse grub arch)
    "x86_64": ("amd64", "x64", "x86_64", "x86_64-efi", "x86_64"),
    "aarch64": ("arm64", "aa64", "aarch64", "arm64-efi", "arm64"),
}
X86_ONLY = {"intel-microcode", "amd64-microcode", "intel-ucode", "amd-ucode", "ucode-intel", "ucode-amd", "microcode_ctl"}


class Backend:
    base = ""
    sudo_group = "wheel"
    kernel_cmdline_extra = ""

    def __init__(self, profile: Profile, layout: Layout, arch: str):
        self.p = profile
        self.lay = layout
        self.arch = arch
        self.cap = capabilities.load(self.base)
        self.debarch, self.efiarch, self.susearch, self.grub_target, self.susegrub = ARCH_MAP[arch]
        self.machine_id = uuid.uuid4().hex

    # ---------- the pipeline (same order for every base) ----------
    def steps(self) -> list[tuple[str, Any]]:
        return [
            ("Bootstrapping base system", self.bootstrap),
            ("Writing fstab, hostname, locale, time zone", self.configure_system),
            ("Installing your selected packages", self.install_selections),
            ("Setting up kernel and initramfs", self.kernel_initramfs),
            ("Installing bootloader", self.bootloader),
            ("Creating user account", self.users),
            ("Enabling services", self.services),
            ("Running post-install hooks", self.post_hooks),
            ("Finishing", self.finish),
        ]

    # ---------- helpers ----------
    def sub(self, pkgs: list[str]) -> list[str]:
        """Substitute {debarch}/{efiarch}/{susearch}/{release} placeholders."""
        rel = self.cap["meta"]["release"]
        out = [p.format(debarch=self.debarch, efiarch=self.efiarch, susearch=self.susearch, susegrub=self.susegrub, release=rel)
               for p in pkgs]
        if self.arch != "x86_64":
            out = [p for p in out if p not in X86_ONLY]
        return out

    def option(self, step: str) -> dict[str, Any]:
        return self.cap[step][getattr(self.p, step)]

    def selected_packages(self) -> list[str]:
        pkgs: list[str] = []
        for step, _ in OPTION_STEPS:
            pkgs += self.option(step).get("packages", [])
        return self.sub(pkgs)

    def removed_packages(self) -> list[str]:
        pkgs: list[str] = []
        for step, _ in OPTION_STEPS:
            pkgs += self.option(step).get("remove", [])
        return self.sub(pkgs)

    def selected_services(self) -> list[str]:
        svcs = list(self.cap["base"].get("services", []))
        for step, _ in OPTION_STEPS:
            svcs += self.option(step).get("services", [])
        return svcs

    def display_manager(self) -> str:
        return self.option("desktop").get("dm", "")

    def xkb(self) -> tuple[str, str]:
        """(layout, variant) for X11/Wayland, from the profile's xkb_layout or derived from the console keymap."""
        return choices.xkb_parts(self.p.xkb_layout or choices.xkb_for_console(self.p.keymap))

    def t(self, path: str) -> str:
        return TARGET + path

    def chroot(self, cmd: list[str], **kw) -> str:
        self._ensure_dns()
        return run(["chroot", TARGET] + cmd, **kw)

    def _ensure_dns(self) -> None:
        """Packages like systemd-resolved replace /etc/resolv.conf with a symlink into /run that does not
        exist inside the chroot; keep a real copy of the live system's resolver there until we finish."""
        run(["rm", "-f", self.t("/etc/resolv.conf")], quiet=True, check=False)
        run(["cp", "-L", "/etc/resolv.conf", self.t("/etc/resolv.conf")], check=False, quiet=True)

    def mount_pseudo(self) -> None:
        for src, dst in (("/dev", "/dev"), ("/dev/pts", "/dev/pts"), ("/proc", "/proc"), ("/sys", "/sys"), ("/run", "/run")):
            run(["mkdir", "-p", self.t(dst)], quiet=True)
            run(["mount", "--bind", src, self.t(dst)], quiet=True, check=False)
        if os.path.isdir("/sys/firmware/efi/efivars"):
            run(["mount", "-t", "efivarfs", "efivarfs", self.t("/sys/firmware/efi/efivars")], quiet=True, check=False)
        self._ensure_dns()

    def umount_pseudo(self) -> None:
        for d in ("/sys/firmware/efi/efivars", "/run", "/sys", "/proc", "/dev/pts", "/dev"):
            run(["umount", "-l", self.t(d)], check=False, quiet=True)

    def kernel_cmdline(self) -> str:
        parts = [f"root=UUID={self.lay.root_uuid}", "rw"]
        if self.lay.filesystem == "btrfs":
            parts.append("rootflags=subvol=@")
        if self.lay.luks_uuid:
            parts.append(f"rd.luks.uuid=luks-{self.lay.luks_uuid}")
        if self.lay.swap:
            parts.append(f"resume=UUID={self.lay.swap_uuid}")
        if self.kernel_cmdline_extra:
            parts.append(self.kernel_cmdline_extra)
        return " ".join(parts)

    # ---------- steps: shared parts ----------
    def bootstrap(self) -> None:
        raise NotImplementedError

    def configure_system(self) -> None:
        self.mount_pseudo()
        write_file(self.t("/etc/fstab"), fstab(self.lay))
        write_file(self.t("/etc/hostname"), self.p.hostname + "\n")
        write_file(self.t("/etc/hosts"), f"127.0.0.1 localhost\n127.0.1.1 {self.p.hostname}\n::1 localhost\n")
        write_file(self.t("/etc/machine-id"), self.machine_id + "\n")
        write_file(self.t("/etc/vconsole.conf"), f"KEYMAP={self.p.keymap}\n")
        layout, variant = self.xkb()
        write_file(self.t("/etc/X11/xorg.conf.d/00-keyboard.conf"),
                   '# Written by diylinux, same format as systemd-localed\nSection "InputClass"\n'
                   '        Identifier "system-keyboard"\n        MatchIsKeyboard "on"\n'
                   f'        Option "XkbLayout" "{layout}"\n' + (f'        Option "XkbVariant" "{variant}"\n' if variant else "")
                   + "EndSection\n")
        write_file(self.t("/etc/locale.conf"), f"LANG={self.p.locale}\n")
        run(["ln", "-sf", f"/usr/share/zoneinfo/{self.p.timezone}", self.t("/etc/localtime")])
        if self.lay.luks_uuid:
            write_file(self.t("/etc/crypttab"), f"cryptroot UUID={self.lay.luks_uuid} none luks,discard\n")
        self.configure_locale()

    def configure_locale(self) -> None:
        """glibc locale generation differs: Arch/Debian use locale.gen, Fedora/SUSE ship langpacks."""
        gen = self.t("/etc/locale.gen")
        if os.path.exists(gen) or DRY:
            append_file(gen, f"{self.p.locale} UTF-8\n")
            self.chroot(["locale-gen"], check=False)

    def install_selections(self) -> None:
        self.install_packages(self.selected_packages())
        rm = self.removed_packages()
        if rm:
            self.remove_packages(rm)

    def install_packages(self, pkgs: list[str]) -> None:
        raise NotImplementedError

    def remove_packages(self, pkgs: list[str]) -> None:
        raise NotImplementedError

    def kernel_initramfs(self) -> None:
        raise NotImplementedError

    def bootloader(self) -> None:
        if self.p.bootloader == "grub":
            self.grub()
        elif self.p.bootloader == "systemd-boot":
            self.systemd_boot()
        self.efi_fallback()

    def grub(self) -> None:
        raise NotImplementedError

    def systemd_boot(self) -> None:
        raise NotImplementedError

    def efi_fallback(self) -> None:
        """Copy the first-stage loader to EFI/BOOT so the firmware fallback path works
        even when the NVRAM entry is lost (common on removable or buggy firmware)."""
        esp = self.t(self.lay.esp_mount)
        suffix = self.efiarch.upper()
        candidates = [f"{esp}/EFI/{d}/shim{self.efiarch}.efi" for d in ("debian", "ubuntu", "fedora", "opensuse")]
        candidates += [f"{esp}/EFI/{d}/grub{self.efiarch}.efi" for d in ("arch", "GRUB")]
        candidates += [f"{esp}/EFI/systemd/systemd-boot{self.efiarch}.efi"]
        if DRY:
            log(f"would copy first-stage loader to EFI/BOOT/BOOT{suffix}.EFI")
            return
        for c in candidates:
            if os.path.exists(c):
                run(["mkdir", "-p", f"{esp}/EFI/BOOT"])
                run(["cp", c, f"{esp}/EFI/BOOT/BOOT{suffix}.EFI"])
                src_dir = os.path.dirname(c)
                for extra in ("grub" + self.efiarch + ".efi", "mm" + self.efiarch + ".efi", "grub.cfg"):
                    if os.path.exists(f"{src_dir}/{extra}") and not os.path.exists(f"{esp}/EFI/BOOT/{extra}"):
                        run(["cp", f"{src_dir}/{extra}", f"{esp}/EFI/BOOT/{extra}"])
                return

    def users(self) -> None:
        self.chroot(["useradd", "-m", "-G", self.sudo_group, "-s", "/bin/bash", self.p.username])
        self.chroot(["chpasswd"], input=f"{self.p.username}:{self.p.password}\n", quiet=True)
        if self.p.root_password:
            self.chroot(["chpasswd"], input=f"root:{self.p.root_password}\n", quiet=True)
        else:
            self.chroot(["passwd", "-l", "root"], check=False)
        write_file(self.t(f"/etc/sudoers.d/10-{self.sudo_group}"), f"%{self.sudo_group} ALL=(ALL:ALL) ALL\n", 0o440)

    def services(self) -> None:
        for svc in self.selected_services():
            run(["systemctl", f"--root={TARGET}", "enable", svc], check=False)
        dm = self.display_manager()
        if dm:
            self.enable_display_manager(dm)
            run(["systemctl", f"--root={TARGET}", "set-default", "graphical.target"])
        if self.option("network").get("networkd_dhcp"):
            write_file(self.t("/etc/systemd/network/20-dhcp.network"),
                       "[Match]\nName=en* eth* wl*\n\n[Network]\nDHCP=yes\nIPv6PrivacyExtensions=yes\n")
            run(["ln", "-sf", "/run/systemd/resolve/stub-resolv.conf", self.t("/etc/resolv.conf")])
        if self.option("firewall").get("ufw_enable"):
            run(["sed", "-i", "s/^ENABLED=no/ENABLED=yes/", self.t("/etc/ufw/ufw.conf")], check=False)
        if self.p.power == "tlp":
            run(["systemctl", f"--root={TARGET}", "mask", "power-profiles-daemon.service"], check=False)

    def enable_display_manager(self, dm: str) -> None:
        run(["systemctl", f"--root={TARGET}", "enable", f"{dm}.service"], check=False)

    def post_hooks(self) -> None:
        for step, _ in OPTION_STEPS:
            for cmd in self.option(step).get("post", []):
                self.chroot(["sh", "-c", cmd], check=False)

    def finish(self) -> None:
        # hand resolv.conf back to systemd-resolved where it is enabled; otherwise leave the plain file
        # (NetworkManager rewrites it on first boot anyway)
        enabled = run(["systemctl", f"--root={TARGET}", "is-enabled", "systemd-resolved"], check=False, capture=True, quiet=True)
        if DRY or enabled.strip() == "enabled":
            run(["ln", "-sf", "../run/systemd/resolve/stub-resolv.conf", self.t("/etc/resolv.conf")])
        self.umount_pseudo()
