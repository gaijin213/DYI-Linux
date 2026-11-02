from __future__ import annotations

import glob
import os

from ..disk import TARGET
from ..run import DRY, log, run, write_file
from .base import Backend

REPO = """[fedora]
name=Fedora $releasever
metalink={mirror}
enabled=1
gpgcheck=1
gpgkey={key}

[updates]
name=Fedora $releasever updates
metalink={updates}
enabled=1
gpgcheck=1
gpgkey={key}
"""

# Installed by the *host* dnf (Debian's dnf4). It segfaults on comps groups against Fedora repos, so this
# list is plain packages only: just enough to run Fedora's own dnf inside the chroot for everything else.
SEED = ["basesystem", "filesystem", "fedora-release", "fedora-repos", "fedora-gpg-keys", "bash", "coreutils",
        "glibc-langpack-en", "systemd", "util-linux", "rpm", "shadow-utils", "sudo", "passwd", "dnf", "ca-certificates"]


class FedoraBackend(Backend):
    base = "fedora"
    sudo_group = "wheel"
    reposdir = "/tmp/diylinux-fedora-repos"
    kernel_cmdline_extra = "rhgb quiet"

    def _host_dnf(self, *args: str, **kw) -> None:
        rel = self.cap["meta"]["release"]
        run(["dnf", "-y", f"--installroot={TARGET}", f"--releasever={rel}", f"--setopt=reposdir={self.reposdir}",
             "--setopt=install_weak_deps=False", "--setopt=tsflags=nocontexts", *args], **kw)

    def _dnf(self, *args: str, **kw) -> None:
        """Fedora's own dnf, inside the chroot (handles groups, kernel-install, BLS natively)."""
        self.chroot(["dnf", "-y", "--setopt=install_weak_deps=True", *args], **kw)

    def bootstrap(self) -> None:
        m = self.cap["meta"]
        write_file(f"{self.reposdir}/fedora.repo",
                   REPO.format(mirror=self.p.mirror or m["default_mirror"], updates=m["updates_mirror"], key=m["gpg_key"]))
        # kernel-install reads these while the kernel RPM is being installed, so they must exist first
        write_file(self.t("/etc/machine-id"), self.machine_id + "\n")
        write_file(self.t("/etc/kernel/cmdline"), self.kernel_cmdline() + "\n")
        # with no loader/entries yet, kernel-install would treat the ESP at /boot/efi as its boot root
        run(["mkdir", "-p", self.t("/boot/loader/entries")])
        self.mount_pseudo()
        self._host_dnf("install", *SEED)
        if self.p.mirror:
            write_file(self.t("/etc/yum.repos.d/diylinux-mirror.repo"),
                       REPO.format(mirror=self.p.mirror, updates=m["updates_mirror"], key="file:///etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-$releasever-$basearch"))
        self._dnf("install", *self.sub(self.cap["base"]["packages"]))

    def configure_locale(self) -> None:
        pass  # glibc-langpack-en + /etc/locale.conf is enough on Fedora

    def install_selections(self) -> None:
        for url in self.sub(self.option("graphics").get("repos", [])):
            self._dnf("install", url)
        super().install_selections()

    def install_packages(self, pkgs: list[str]) -> None:
        if pkgs:
            self._dnf("install", *pkgs)

    def remove_packages(self, pkgs: list[str]) -> None:
        self._dnf("remove", *pkgs, check=False)

    def kernel_initramfs(self) -> None:
        # The kernel RPM ran kernel-install before grub2-common (and its 20-grub plugin) was installed, so
        # nothing reached /boot yet. Re-run it now that every plugin is present: it copies vmlinuz, builds
        # the initramfs and rescue image, and writes the BLS entries - exactly what a normal Fedora does.
        versions = [os.path.basename(d) for d in sorted(glob.glob(self.t("/lib/modules/*")))] if not DRY else ["KVER"]
        for ver in versions:
            self.chroot(["kernel-install", "add", ver, f"/lib/modules/{ver}/vmlinuz"])
        # make sure every BLS entry carries our cmdline, whatever kernel-install picked up
        for entry in (glob.glob(self.t("/boot/loader/entries/*.conf")) if not DRY else []):
            run(["sed", "-i", f"s|^options .*|options {self.kernel_cmdline()}|", entry])

    def grub(self) -> None:
        # UEFI Fedora never runs grub2-install: the signed grubx64.efi comes from the grub2-efi package.
        write_file(self.t("/etc/default/grub"),
                   'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR="$(sed \'s, release .*$,,g\' /etc/system-release)"\n'
                   "GRUB_DEFAULT=saved\nGRUB_DISABLE_SUBMENU=true\nGRUB_TERMINAL_OUTPUT=\"console\"\n"
                   f'GRUB_CMDLINE_LINUX="{self.kernel_cmdline()}"\nGRUB_DISABLE_RECOVERY="true"\nGRUB_ENABLE_BLSCFG=true\n')
        self.chroot(["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])
        # Stub on the ESP that hands over to /boot/grub2/grub.cfg on the separate /boot partition
        boot_uuid = self.lay.boot_uuid or self.lay.root_uuid
        prefix = "/grub2" if self.lay.boot else ("/@/boot/grub2" if self.lay.filesystem == "btrfs" else "/boot/grub2")
        write_file(self.t(f"{self.lay.esp_mount}/EFI/fedora/grub.cfg"),
                   f"search --no-floppy --fs-uuid --set=dev {boot_uuid}\nset prefix=($dev){prefix}\nexport $prefix\nconfigfile $prefix/grub.cfg\n")
        self._efibootmgr("Fedora", f"\\EFI\\fedora\\shim{self.efiarch}.efi")

    def _efibootmgr(self, label: str, loader: str) -> None:
        esp = self.lay.esp
        disk = esp.rstrip("0123456789").removesuffix("p") if "nvme" in esp or "mmcblk" in esp else esp.rstrip("0123456789")
        part = esp[len(disk):].lstrip("p")
        run(["efibootmgr", "--create", "--disk", disk, "--part", part, "--label", label, "--loader", loader], check=False)

    def finish(self) -> None:
        # The live kernel has no SELinux, so rpm left every file unlabeled and systemd would fail on first
        # boot ("Failed to allocate manager object") before any autorelabel could run. Label the tree now
        # from inside the chroot (setfiles only needs xattrs, like mkosi does); skip pseudo mounts and vfat.
        self.chroot(["setfiles", "-m", "-F", "-e", "/proc", "-e", "/sys", "-e", "/dev", "-e", "/run",
                     "-e", self.lay.esp_mount, "/etc/selinux/targeted/contexts/files/file_contexts", "/"])
        super().finish()
