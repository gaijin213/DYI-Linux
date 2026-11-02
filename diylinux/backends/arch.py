from __future__ import annotations

from ..disk import TARGET
from ..run import DRY, log, run, write_file
from .base import Backend

PACMAN_CONF = """[options]
Architecture = {arch}
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
ParallelDownloads = 5

[core]
Server = {mirror}

[extra]
Server = {mirror}
"""


class ArchBackend(Backend):
    base = "arch"
    sudo_group = "wheel"
    host_conf = "/tmp/diylinux-pacman.conf"

    def _mirror(self) -> str:
        return self.p.mirror or self.cap["meta"]["default_mirror"]

    def bootstrap(self) -> None:
        write_file(self.host_conf, PACMAN_CONF.format(arch=self.arch, mirror=self._mirror()))
        # host keyring (Debian's pacman-package-manager + archlinux-keyring)
        run(["pacman-key", "--init"], check=False)
        run(["pacman-key", "--populate", "archlinux"], check=False)
        self._refresh_keyring()
        pkgs = self.sub(self.cap["base"]["packages"])
        run(["pacstrap", "-C", self.host_conf, "-K", TARGET] + pkgs)
        write_file(self.t("/etc/pacman.d/mirrorlist"), f"Server = {self._mirror()}\n")

    def _refresh_keyring(self) -> None:
        """Best effort: fetch today's archlinux-keyring package and populate the live keyring from it, so
        packages signed with keys added after the ISO was built still verify. Failure is not fatal."""
        cache = "/tmp/diylinux-keyring"
        run(["rm", "-rf", cache], quiet=True)
        run(["mkdir", "-p", f"{cache}/db"], quiet=True)
        try:
            run(["pacman", "--config", self.host_conf, "--cachedir", cache, "--dbpath", f"{cache}/db", "--noconfirm",
                 "-Syw", "archlinux-keyring"])
            pkg = run(["sh", "-c", f"ls {cache}/archlinux-keyring-*.pkg.tar.* 2>/dev/null | grep -v '\\.sig$' | head -1"],
                      capture=True).strip()
            if not pkg and not DRY:
                raise RuntimeError("keyring package not downloaded")
            # Debian's pacman-key imports from /usr/share/keyrings; the live overlay is writable
            run(["tar", "-C", "/usr/share/keyrings", "--strip-components=3", "-xf", pkg or f"{cache}/archlinux-keyring.pkg.tar.zst",
                 "--wildcards", "usr/share/pacman/keyrings/archlinux*"])
            run(["pacman-key", "--populate", "archlinux"])
            log("Arch keyring refreshed from the current archlinux-keyring package")
        except Exception as e:  # noqa: BLE001
            log(f"could not refresh the Arch keyring ({e}); continuing with the keyring shipped on the ISO")

    def install_packages(self, pkgs: list[str]) -> None:
        if pkgs:
            self.chroot(["pacman", "-S", "--noconfirm", "--needed"] + pkgs)

    def remove_packages(self, pkgs: list[str]) -> None:
        self.chroot(["pacman", "-Rns", "--noconfirm"] + pkgs, check=False)

    def kernel_initramfs(self) -> None:
        hooks = "base systemd autodetect microcode modconf kms keyboard sd-vconsole block"
        if self.lay.luks_uuid:
            hooks += " sd-encrypt"
            write_file(self.t("/etc/crypttab.initramfs"), f"cryptroot UUID={self.lay.luks_uuid} none luks,discard\n")
        hooks += " filesystems fsck"
        run(["sed", "-i", f"s/^HOOKS=.*/HOOKS=({hooks})/", self.t("/etc/mkinitcpio.conf")])
        self.chroot(["mkinitcpio", "-P"])

    def grub(self) -> None:
        self.chroot(["grub-install", f"--target={self.grub_target}", f"--efi-directory={self.lay.esp_mount}",
                     "--bootloader-id=arch", "--recheck"])
        run(["sed", "-i", f's|^GRUB_CMDLINE_LINUX=.*|GRUB_CMDLINE_LINUX="{self.kernel_cmdline()}"|',
             self.t("/etc/default/grub")])
        if self.lay.luks_uuid:
            run(["sed", "-i", "s/^#GRUB_ENABLE_CRYPTODISK=y/GRUB_ENABLE_CRYPTODISK=y/", self.t("/etc/default/grub")])
        self.chroot(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])

    def systemd_boot(self) -> None:
        self.chroot(["bootctl", "install"])
        write_file(self.t("/boot/loader/loader.conf"), "default arch.conf\ntimeout 3\nconsole-mode max\neditor no\n")
        ucode = "initrd /intel-ucode.img\ninitrd /amd-ucode.img\n" if self.arch == "x86_64" else ""
        write_file(self.t("/boot/loader/entries/arch.conf"),
                   f"title Arch Linux\nlinux /vmlinuz-linux\n{ucode}initrd /initramfs-linux.img\noptions {self.kernel_cmdline()}\n")
        write_file(self.t("/boot/loader/entries/arch-fallback.conf"),
                   f"title Arch Linux (fallback initramfs)\nlinux /vmlinuz-linux\n{ucode}initrd /initramfs-linux-fallback.img\noptions {self.kernel_cmdline()}\n")

    def services(self) -> None:
        super().services()
        run(["systemctl", f"--root={TARGET}", "enable", "fstrim.timer"], check=False)
