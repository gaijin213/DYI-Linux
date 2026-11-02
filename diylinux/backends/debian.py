from __future__ import annotations

import os

from ..disk import TARGET
from ..run import DRY, log, run, write_file
from .base import Backend

DEBOOTSTRAP_SCRIPTS = "/usr/share/debootstrap/scripts"

SOURCES_DEBIAN = """Types: deb
URIs: {mirror}
Suites: {rel} {rel}-updates
Components: {components}
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: http://security.debian.org/debian-security
Suites: {rel}-security
Components: {components}
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
"""

SOURCES_UBUNTU = """Types: deb
URIs: {mirror}
Suites: {rel} {rel}-updates {rel}-security {rel}-backports
Components: {components}
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""


class DebianBackend(Backend):
    base = "debian"
    sudo_group = "sudo"
    sources_tpl = SOURCES_DEBIAN
    keyring = "/usr/share/keyrings/debian-archive-keyring.gpg"
    bootloader_id = "debian"
    kernel_cmdline_extra = "quiet"

    def _mirror(self) -> str:
        return self.p.mirror or self.cap["meta"]["default_mirror"]

    def _apt(self, *args: str, **kw) -> None:
        self.chroot(["apt-get", "-y", "-o", "Dpkg::Options::=--force-confnew", *args],
                    env={"DEBIAN_FRONTEND": "noninteractive"}, **kw)

    generic_script = "sid"      # debootstrap's Debian scripts are all links to this one

    def _ensure_debootstrap_script(self, rel: str) -> None:
        """debootstrap on the ISO predates releases newer than the ISO: point the codename at the generic script."""
        if DRY or os.path.exists(f"{DEBOOTSTRAP_SCRIPTS}/{rel}"):
            return
        log(f"debootstrap has no script for '{rel}', using the generic '{self.generic_script}' one")
        run(["ln", "-sf", self.generic_script, f"{DEBOOTSTRAP_SCRIPTS}/{rel}"])

    def bootstrap(self) -> None:
        rel = self.cap["meta"]["release"]
        self._ensure_debootstrap_script(rel)
        comps = ",".join(self.cap["meta"]["components"])
        run(["debootstrap", f"--arch={self.debarch}", f"--components={comps}", f"--keyring={self.keyring}",
             "--include=ca-certificates,apt-utils,gnupg", rel, TARGET, self._mirror()])
        run(["rm", "-f", self.t("/etc/apt/sources.list")], check=False)
        write_file(self.t("/etc/apt/sources.list.d/diylinux.sources"),
                   self.sources_tpl.format(mirror=self._mirror(), rel=rel, components=" ".join(self.cap["meta"]["components"])))

    def configure_system(self) -> None:
        super().configure_system()
        layout, variant = self.xkb()
        write_file(self.t("/etc/default/keyboard"),
                   f'XKBMODEL="pc105"\nXKBLAYOUT="{layout}"\nXKBVARIANT="{variant}"\nXKBOPTIONS=""\nBACKSPACE="guess"\n')
        write_file(self.t("/etc/default/locale"), f"LANG={self.p.locale}\n")
        self._apt("update")
        # base packages go in here (after fstab/crypttab exist) so initramfs-tools sees the real layout
        self._apt("install", *self.sub(self.cap["base"]["packages"]))
        # 'locales' only exists now, so generate the locale here rather than in configure_locale()
        from ..run import append_file
        append_file(self.t("/etc/locale.gen"), f"{self.p.locale} UTF-8\n")
        self.chroot(["locale-gen"])

    def configure_locale(self) -> None:
        pass  # done at the end of configure_system, after the locales package is installed

    def install_packages(self, pkgs: list[str]) -> None:
        if pkgs:
            self._apt("install", *pkgs)

    def remove_packages(self, pkgs: list[str]) -> None:
        self._apt("purge", *pkgs, check=False)

    def kernel_initramfs(self) -> None:
        self.chroot(["update-initramfs", "-u", "-k", "all"])

    def grub(self) -> None:
        run(["sed", "-i", f's|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT="{self.kernel_cmdline_extra}"|',
             self.t("/etc/default/grub")])
        self.chroot(["grub-install", f"--target={self.grub_target}", f"--efi-directory={self.lay.esp_mount}",
                     f"--bootloader-id={self.bootloader_id}", "--uefi-secure-boot", "--recheck"])
        self.chroot(["update-grub"])

    def finish(self) -> None:
        self._apt("clean", check=False)
        super().finish()


class UbuntuBackend(DebianBackend):
    base = "ubuntu"
    sources_tpl = SOURCES_UBUNTU
    generic_script = "gutsy"    # every Ubuntu debootstrap script is a link to this one
    keyring = "/usr/share/keyrings/ubuntu-archive-keyring.gpg"
    bootloader_id = "ubuntu"

    def _mirror(self) -> str:
        if self.p.mirror:
            return self.p.mirror
        return self.cap["meta"]["default_mirror" if self.arch == "x86_64" else "default_mirror_ports"]
