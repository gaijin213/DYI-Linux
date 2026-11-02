from __future__ import annotations

from ..disk import TARGET
from ..run import run, write_file
from .base import Backend


class OpenSUSEBackend(Backend):
    base = "opensuse"
    sudo_group = "wheel"
    kernel_cmdline_extra = "quiet"

    def _zypper(self, *args: str, **kw) -> None:
        run(["zypper", f"--root={TARGET}", "--non-interactive", "--gpg-auto-import-keys", *args], **kw)

    def _repos(self) -> dict[str, str]:
        m = self.cap["meta"]
        mirror = self.p.mirror or m["default_mirror"]
        table = m["repos"] if self.arch == "x86_64" else m["repos_ports"]
        return {name: url.format(mirror=mirror, susearch=self.susearch) for name, url in table.items()}

    def bootstrap(self) -> None:
        for name, url in self._repos().items():
            self._zypper("addrepo", "--refresh", "--check", url, f"repo-{name}")
        self._zypper("refresh")
        write_file(self.t("/etc/machine-id"), self.machine_id + "\n")
        self.mount_pseudo()  # rpm scriptlets (kernel symlinks, pam-config) need /proc, /dev, /sys
        # The kernel scriptlet prints "ERROR: cannot create symlinks /boot/Image and /boot/initrd" because
        # no initrd exists yet (we run dracut later). It skips that check in a kiwi build env, so pose as one.
        write_file(self.t("/.buildenv"), "")
        self._zypper("install", "--auto-agree-with-licenses", *self.sub(self.cap["base"]["packages"]))
        run(["rm", "-f", self.t("/.buildenv")])

    def configure_locale(self) -> None:
        write_file(self.t("/etc/sysconfig/language"), f'RC_LANG="{self.p.locale}"\nROOT_USES_LANG="ctype"\n')

    def install_selections(self) -> None:
        for name, url in self.option("graphics").get("zypper_repos", {}).items():
            self._zypper("addrepo", "--refresh", url, name)
            self._zypper("refresh")
        super().install_selections()

    def install_packages(self, pkgs: list[str]) -> None:
        if pkgs:
            self._zypper("install", "--auto-agree-with-licenses", *pkgs)

    def remove_packages(self, pkgs: list[str]) -> None:
        self._zypper("remove", *pkgs, check=False)

    def kernel_initramfs(self) -> None:
        self.chroot(["dracut", "--regenerate-all", "--force"])

    def grub(self) -> None:
        run(["sed", "-i", f's|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT="{self.kernel_cmdline()}"|',
             self.t("/etc/default/grub")], check=False)
        write_file(self.t("/etc/sysconfig/bootloader"), 'LOADER_TYPE="grub2-efi"\nSECURE_BOOT="yes"\n')
        # shim-install puts the signed shim + grub on the ESP and registers the NVRAM entry
        self.chroot(["shim-install", "--config-file=/boot/grub2/grub.cfg"])
        self.chroot(["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])

    def users(self) -> None:
        super().users()
        # openSUSE's default sudoers asks for root's password; make it behave like the other bases
        write_file(self.t("/etc/sudoers.d/00-diylinux-defaults"), "Defaults !targetpw\n", 0o440)

    def enable_display_manager(self, dm: str) -> None:
        write_file(self.t("/etc/sysconfig/displaymanager"), f'DISPLAYMANAGER="{dm}"\nDISPLAYMANAGER_AUTOLOGIN=""\n')
        self.chroot(["update-alternatives", "--set", "default-displaymanager", f"/usr/lib/X11/displaymanagers/{dm}"], check=False)
        run(["systemctl", f"--root={TARGET}", "enable", "display-manager.service"], check=False)
