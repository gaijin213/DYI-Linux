"""diylinux TUI: the same question flow and the same install screen for every base."""
from __future__ import annotations

import os
import sys
import threading
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, Checkbox, Footer, Header, Input, Label, OptionList, ProgressBar,
                             RadioButton, RadioSet, RichLog, Select, Static)
from textual.widgets.option_list import Option

from .. import capabilities, choices, hw, releases
from ..install import Event, run_install
from ..profile import OPTION_STEPS, Profile
from . import console

CSS = """
Screen { align: center top; background: black; color: white; }
#panel { width: 100; max-width: 100%; height: auto; margin: 1 2; padding: 1 2; border: round white; background: black; color: white; }
.title { text-style: bold; color: white; margin-bottom: 1; }
.hint { color: white; margin-top: 1; }
.warn { background: $error 20%; color: white; padding: 1 2; margin: 1 0; border: heavy $error; text-style: bold; }
.info { background: black; padding: 1 2; margin: 1 0; }
OptionList { height: auto; max-height: 18; border: tall white; }
RadioSet { height: auto; width: 100%; }
Input { margin-bottom: 1; color: white; background: black; }
Horizontal.buttons { height: auto; margin-top: 1; align: right middle; }
Horizontal.buttons #log { color: white; background: black; }
Horizontal.buttons Button { margin-left: 2; color: white; background: black; }
#log { height: 16; border: tall white; color: white; background: black; }
ProgressBar { margin: 1 0; width: 100%; }
#facts { color: white; }
Label.field { margin-top: 1; color: white; }
Picker { height: auto; margin-bottom: 1; }
Picker Input { margin-bottom: 0; }
Picker OptionList { max-height: 8; }
Picker .current { color: $success; text-style: bold; padding: 0 1; }
Select { margin-bottom: 1; color: white; background: black; }
SelectCurrent { color: white; background: black; }
SelectOverlay { color: white; background: black; border: tall white; }
#manual, #auto { height: auto; }
"""
if console.is_console():
    CSS += console.apply()

ARCH_SB_WARNING = (
    "[b]SECURE BOOT IS ENABLED ON THIS MACHINE AND YOU CHOSE ARCH LINUX.[/b]\n\n"
    "[b]Arch has no Microsoft-signed bootloader. If you do not want to tinker with Secure Boot on Arch, "
    "you must DISABLE SECURE BOOT in your firmware (BIOS/UEFI setup) before the first reboot, "
    "or the installed system WILL NOT BOOT.[/b]\n\n"
    "Alternatively pick Debian, Ubuntu, Fedora or openSUSE Tumbleweed, which boot with Secure Boot on."
)


# ----------------------------------------------------------------- helpers
class StepScreen(Screen):
    """A question screen. Subclasses fill compose_body() and apply()."""
    BINDINGS = [Binding("escape", "back", "Back")]
    title_text = ""

    @property
    def profile(self) -> Profile:
        return self.app.profile  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="panel"):
            yield Static(self.title_text, classes="title")
            yield from self.compose_body()
            with Horizontal(classes="buttons"):
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")
        yield Footer()

    def compose_body(self) -> ComposeResult:
        yield from ()

    def apply(self) -> str | None:
        """Store answers into the profile. Return an error string to stay on the screen."""
        return None

    @on(Button.Pressed, "#back")
    def _back_pressed(self) -> None:
        self.action_back()

    def action_back(self) -> None:
        self.app.prev_step()  # type: ignore[attr-defined]

    @on(Button.Pressed, "#next")
    def _next_pressed(self) -> None:
        # @on binds the decorated function itself, so subclasses override on_next(), not this
        self.on_next()

    def on_next(self) -> None:
        err = self.apply()
        if err:
            self.notify(err, severity="error", timeout=6)
            return
        self.app.next_step()  # type: ignore[attr-defined]


class ConfirmModal(ModalScreen[bool]):
    def __init__(self, text: str, yes: str, no: str, warn: bool = False):
        super().__init__()
        self.text, self.yes, self.no, self.warn = text, yes, no, warn

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Static(self.text, classes="warn" if self.warn else "info")
            with Horizontal(classes="buttons"):
                yield Button(self.no, id="no", variant="primary")
                yield Button(self.yes, id="yes", variant="error" if self.warn else "success")

    @on(Button.Pressed)
    def done(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "yes")


class Picker(Vertical):
    """Search box + filtered list for long choice lists (time zones, locales, keyboard layouts).

    items: [(value, label)]. The highlighted row is the selection; typing in the box narrows the list.
    """

    def __init__(self, items: list[tuple[str, str]], value: str, placeholder: str, id: str):
        super().__init__(id=id)
        self.items = items
        self.value = value if any(v == value for v, _ in items) else (items[0][0] if items else "")
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        yield Input(placeholder=self.placeholder, id="search")
        yield OptionList(id="list")
        yield Static("", classes="current", id="current")

    def on_mount(self) -> None:
        self._fill("")

    def _fill(self, needle: str) -> None:
        ol = self.query_one("#list", OptionList)
        words = needle.lower().split()
        shown = [(v, l) for v, l in self.items if all(w in (v + " " + l).lower() for w in words)][:300]
        ol.clear_options()
        ol.add_options([Option(l, id=v) for v, l in shown])
        if shown:
            idx = next((i for i, (v, _) in enumerate(shown) if v == self.value), 0)
            ol.highlighted = idx
            self.value = shown[idx][0]
        self._show()

    def _show(self) -> None:
        label = next((l for v, l in self.items if v == self.value), self.value)
        self.query_one("#current", Static).update(f"Selected: {label}" if self.value else "Nothing matches - keep typing or clear the search")

    @on(Input.Changed, "#search")
    def _changed(self, ev: Input.Changed) -> None:
        self._fill(ev.value)

    @on(Input.Submitted, "#search")
    def _submitted(self) -> None:
        self.query_one("#list", OptionList).focus()

    @on(OptionList.OptionHighlighted, "#list")
    def _highlighted(self, ev: OptionList.OptionHighlighted) -> None:
        if ev.option.id is not None:
            self.value = ev.option.id
            self._show()

    @on(OptionList.OptionSelected, "#list")
    def _selected(self, ev: OptionList.OptionSelected) -> None:
        if ev.option.id is not None:
            self.value = ev.option.id
            self._show()
            self.screen.focus_next()


# ----------------------------------------------------------------- screens
class Welcome(StepScreen):
    title_text = "DIY Linux installer"

    def _facts_text(self) -> str:
        sb = hw.secure_boot_enabled()
        sb_txt = {True: "[b red]ON[/]", False: "off", None: "unknown"}[sb]
        net = "yes" if hw.has_network() else "[b red]NO - connect first (nmtui in another console)[/]"
        return (
            f"Architecture: {hw.arch()}    Firmware: {'UEFI' if hw.is_uefi() else '[b red]BIOS (unsupported)[/]'}    "
            f"Secure Boot: {sb_txt}    Network: {net}"
        )

    def compose_body(self) -> ComposeResult:
        yield Static(self._facts_text(), id="facts")
        yield Static("\nSelect a base and continue.", classes="hint")
        if os.environ.get("DIYLINUX_DRYRUN") == "1":
            yield Static("DRY RUN: commands are printed, nothing is executed.", classes="info")

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_facts)

    def _refresh_facts(self) -> None:
        try:
            self.query_one("#facts", Static).update(self._facts_text())
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="panel"):
            yield Static(self.title_text, classes="title")
            yield from self.compose_body()
            with Horizontal(classes="buttons"):
                yield Button("Help me choose a base", id="quiz")
                yield Button("Start", id="next", variant="primary")
        yield Footer()

    @on(Button.Pressed, "#quiz")
    def quiz(self) -> None:
        self.app.push_screen(Quiz())


class Quiz(StepScreen):
    title_text = "Which base suits you? Four quick questions."
    QUESTIONS = [
        ("release", "How do you want updates?", [("point", "Stable releases, upgrade once or twice a year"),
                                                   ("rolling", "Rolling, always the newest versions")]),
        ("effort", "How much do you want to maintain yourself?", [("low", "As little as possible"),
                                                                   ("high", "I like to understand and tune my system")]),
        ("prop", "Do you need proprietary drivers (NVIDIA, Broadcom) to just work?", [("yes", "Yes"), ("no", "No / I can set them up")]),
        ("sb", "Will Secure Boot stay enabled?", [("yes", "Yes, keep it on"), ("no", "I can turn it off")]),
    ]

    def compose_body(self) -> ComposeResult:
        for key, q, opts in self.QUESTIONS:
            yield Label(q, classes="field")
            with RadioSet(id=f"q-{key}"):
                for val, label in opts:
                    yield RadioButton(label, id=f"{key}-{val}", value=val == opts[0][0])

    def apply(self) -> str | None:
        ans = {}
        for key, _, _ in self.QUESTIONS:
            rs = self.query_one(f"#q-{key}", RadioSet)
            ans[key] = (rs.pressed_button.id or "").split("-", 1)[1] if rs.pressed_button else ""
        if ans["release"] == "rolling":
            rec = "opensuse" if (ans["sb"] == "yes" or ans["effort"] == "low") else "arch"
        else:
            if ans["prop"] == "yes":
                rec = "ubuntu"
            elif ans["effort"] == "high":
                rec = "debian"
            else:
                rec = "fedora"
        self.app.recommended = rec  # type: ignore[attr-defined]
        self.notify(f"Recommended: {capabilities.load(rec)['meta']['name']}", timeout=6)
        return None

    def on_next(self) -> None:
        self.apply()
        self.app.pop_screen()
        self.app.next_step()  # type: ignore[attr-defined]


class BaseChoice(StepScreen):
    title_text = "Choose the base distribution"

    @staticmethod
    def label(b: str) -> str:
        m = capabilities.load(b)["meta"]
        rel = "rolling" if m["rolling"] else m.get("release_label", m["release"])
        if not m["rolling"] and not releases.status(b):
            rel += ", checking for newer..."
        label = f"[b]{m['name']}[/b]  ({rel}, Secure Boot: {'yes' if m['secure_boot'] else '[b red]no[/]'})"
        if hw.arch() not in m["arches"]:
            label += f"  [dim]not available on {hw.arch()}[/]"
        return label

    def compose_body(self) -> ComposeResult:
        arch = hw.arch()
        ol = OptionList(id="bases")
        for b, cap in capabilities.all_bases().items():
            ol.add_option(Option(self.label(b), id=b, disabled=arch not in cap["meta"]["arches"]))
        yield ol
        yield Static("", id="blurb", classes="hint")
        yield Static("", id="sbwarn")
        yield Static("Releases: the installer always installs the newest stable release of the base you pick "
                     "(checked online when this screen opens).", classes="hint", id="relnote")

    def refresh_labels(self) -> None:
        ol = self.query_one("#bases", OptionList)
        hl = ol.highlighted
        ol.clear_options()
        for b, cap in capabilities.all_bases().items():
            ol.add_option(Option(self.label(b), id=b, disabled=hw.arch() not in cap["meta"]["arches"]))
        ol.highlighted = hl

    def on_mount(self) -> None:
        ol = self.query_one("#bases", OptionList)
        rec = getattr(self.app, "recommended", None) or self.profile.base or "fedora"
        ol.highlighted = next((i for i, o in enumerate(ol._options) if o.id == rec), 0)
        ol.focus()

    @on(OptionList.OptionHighlighted)
    def show(self, ev: OptionList.OptionHighlighted) -> None:
        if ev.option.id is None:
            return
        cap = capabilities.load(ev.option.id)
        self.query_one("#blurb", Static).update(cap["meta"]["blurb"])
        warn = self.query_one("#sbwarn", Static)
        if ev.option.id == "arch" and hw.secure_boot_enabled():
            warn.update(ARCH_SB_WARNING)
            warn.set_classes("warn")
        else:
            warn.update("")
            warn.set_classes("")

    @on(OptionList.OptionSelected)
    def pick(self, ev: OptionList.OptionSelected) -> None:
        self.on_next()

    def apply(self) -> str | None:
        ol = self.query_one("#bases", OptionList)
        if ol.highlighted is None:
            return "pick a base"
        base = ol.get_option_at_index(ol.highlighted).id or ""
        if base != self.profile.base:
            # reset per-base choices to that base's defaults
            cap = capabilities.load(base)
            for step, _ in OPTION_STEPS:
                if getattr(self.profile, step) not in cap[step]:
                    setattr(self.profile, step, next(iter(cap[step])))
            if self.profile.disk.filesystem not in cap["disk"]["filesystems"]:
                self.profile.disk.filesystem = cap["disk"]["filesystems"][0]
        self.profile.base = base
        return None

    def on_next(self) -> None:
        err = self.apply()
        if err:
            self.notify(err, severity="error")
            return
        if self.profile.base == "arch" and hw.secure_boot_enabled() and not self.profile.secure_boot_acknowledged:
            def cb(ok: bool | None) -> None:
                if ok:
                    self.profile.secure_boot_acknowledged = True
                    self.app.next_step()  # type: ignore[attr-defined]
            self.app.push_screen(ConfirmModal(ARCH_SB_WARNING, "I will disable Secure Boot - continue with Arch",
                                              "Choose another base", warn=True), cb)
            return
        self.app.next_step()  # type: ignore[attr-defined]


class DiskChoice(StepScreen):
    title_text = "Disk"
    ROLES = [("esp", "EFI system partition (required; vfat, type 'EFI System')"),
             ("root", "Root partition / (required; will be formatted)"),
             ("boot", "Separate /boot partition (optional; ext4, formatted)"),
             ("swap", "Swap partition (optional)"),
             ("home", "/home partition (optional)")]

    def compose_body(self) -> ComposeResult:
        d = self.profile.disk
        yield Label("Target disk", classes="field")
        ol = OptionList(id="disks")
        for disk in hw.disks():
            ol.add_option(Option(f"{disk.path}  {disk.size_human}  {disk.model}  [{disk.transport}{', removable' if disk.removable else ''}]", id=disk.path))
        yield ol
        yield Label("Partitioning", classes="field")
        with RadioSet(id="mode"):
            yield RadioButton("Erase the whole disk and partition it automatically (recommended)", id="mode-wipe", value=not d.manual)
            yield RadioButton("Manual: I partition the disk myself and choose which partition is used for what", id="mode-manual", value=d.manual)
        fss = capabilities.load(self.profile.base)["disk"]["filesystems"]
        yield Label("Root filesystem", classes="field")
        with RadioSet(id="fs"):
            for fs in fss:
                yield RadioButton({"ext4": "ext4 (simple, robust)", "btrfs": "btrfs (snapshots, compression)",
                                   "xfs": "xfs (large files)"}[fs], id=f"fs-{fs}", value=fs == d.filesystem)
        with Vertical(id="auto"):
            yield Label("Swap partition size in GB (0 = none)", classes="field")
            yield Input(value=str(d.swap_gb), id="swap", type="integer")
        with Vertical(id="manual"):
            yield Static("Create or change partitions with the editor below (cfdisk: arrow keys, then the New, Type, Write "
                         "and Quit menu items), or use partitions you already have. Then say which partition plays which "
                         "role. Only the root partition, a chosen /boot partition and anything you tick to format are erased.\n"
                         "Suggested sizes: EFI 512M or more, /boot 1G, root 30G or more.", classes="hint")
            yield Button("Open partition editor (cfdisk) on the selected disk", id="cfdisk")
            for role, label in self.ROLES:
                yield Label(label, classes="field")
                yield Select([], prompt="none" if role in ("boot", "swap", "home") else "choose a partition",
                             allow_blank=True, id=f"p-{role}")
            yield Checkbox("Format the EFI system partition (untick to keep other operating systems' bootloaders on it)",
                           id="fmt-esp", value=d.format_esp)
            yield Checkbox("Format the /home partition (untick to keep its files)", id="fmt-home", value=d.format_home)

    def on_mount(self) -> None:
        ol = self.query_one("#disks", OptionList)
        if ol.option_count:
            ol.highlighted = next((i for i, o in enumerate(ol._options) if o.id == self.profile.disk.device), 0)
        ol.focus()
        self._mode_changed()
        self._refresh_partitions()

    def _disk(self) -> str:
        ol = self.query_one("#disks", OptionList)
        return (ol.get_option_at_index(ol.highlighted).id or "") if ol.highlighted is not None else ""

    def _manual(self) -> bool:
        rs = self.query_one("#mode", RadioSet)
        return bool(rs.pressed_button and rs.pressed_button.id == "mode-manual")

    @on(RadioSet.Changed, "#mode")
    def _mode_changed(self) -> None:
        manual = self._manual()
        self.query_one("#auto").display = not manual
        self.query_one("#manual").display = manual

    @on(OptionList.OptionHighlighted, "#disks")
    def _disk_changed(self) -> None:
        self._refresh_partitions()

    def _refresh_partitions(self) -> None:
        disk = self._disk()
        parts = hw.partitions(disk) if disk else []
        opts = [(hw.partition_label(p), p["path"]) for p in parts]
        d = self.profile.disk
        for role, _ in self.ROLES:
            sel = self.query_one(f"#p-{role}", Select)
            prev = sel.value if isinstance(sel.value, str) else ""
            sel.set_options(opts)
            want = prev or getattr(d, f"{role}_partition")
            if want and any(v == want for _, v in opts):
                sel.value = want
            elif not want and role == "esp":   # pre-pick the obvious EFI partition
                esp = next((p["path"] for p in parts if "efi" in p["parttype"].lower() or p["fstype"] == "vfat"), None)
                if esp:
                    sel.value = esp

    @on(Button.Pressed, "#cfdisk")
    def _cfdisk(self) -> None:
        disk = self._disk()
        if not disk:
            self.notify("select a disk first", severity="error")
            return
        if os.environ.get("DIYLINUX_DRYRUN") == "1":
            self.notify("dry run: would open cfdisk " + disk)
            return
        import subprocess
        with self.app.suspend():
            subprocess.call(["cfdisk", disk])
        hw.rescan(disk)
        self._refresh_partitions()
        self.notify("partition table re-read")

    def apply(self) -> str | None:
        d = self.profile.disk
        d.device = self._disk()
        if not d.device:
            return "select a disk"
        d.mode = "manual" if self._manual() else "wipe"
        rs = self.query_one("#fs", RadioSet)
        d.filesystem = (rs.pressed_button.id or "fs-ext4").split("-", 1)[1] if rs.pressed_button else "ext4"
        d.encrypt = False
        d.passphrase = ""
        if not d.manual:
            try:
                d.swap_gb = max(0, int(self.query_one("#swap", Input).value or 0))
            except ValueError:
                return "swap must be a whole number"
            d.esp_partition = d.root_partition = d.boot_partition = d.swap_partition = d.home_partition = ""
            d.encrypt = False
            d.passphrase = ""
            return None
        parts = {p["path"]: p for p in hw.partitions(d.device)}
        for role, _ in self.ROLES:
            v = self.query_one(f"#p-{role}", Select).value
            setattr(d, f"{role}_partition", v if isinstance(v, str) else "")   # Select.NULL when blank
        d.format_esp = self.query_one("#fmt-esp", Checkbox).value
        d.format_home = self.query_one("#fmt-home", Checkbox).value
        if not d.esp_partition:
            return "choose the EFI system partition (make one with cfdisk: 512M or more, type 'EFI System')"
        if not d.root_partition:
            return "choose the root partition"
        chosen = [x for x in (d.esp_partition, d.root_partition, d.boot_partition, d.swap_partition, d.home_partition) if x]
        if len(set(chosen)) != len(chosen):
            return "the same partition is selected twice"
        esp = parts.get(d.esp_partition, {})
        if esp and esp.get("parttype") and "efi" not in esp["parttype"].lower():
            return f"{d.esp_partition} has type '{esp['parttype']}'; set it to 'EFI System' in cfdisk"
        if esp and not d.format_esp and esp.get("fstype") != "vfat":
            return f"{d.esp_partition} is not FAT formatted; tick 'format the EFI system partition'"
        if d.encrypt and not d.boot_partition:
            return "encryption needs a separate /boot partition (1G ext4) so the bootloader can unlock the root"
        if self.profile.bootloader == "systemd-boot" and d.boot_partition:
            self.profile.bootloader = "grub"
        return None

    def on_next(self) -> None:
        err = self.apply()
        if err:
            self.notify(err, severity="error", timeout=8)
            return
        d = self.profile.disk
        if d.manual and d.home_partition and not d.format_home and hw.partitions(d.device) and \
                not next((p for p in hw.partitions(d.device) if p["path"] == d.home_partition), {}).get("fstype"):
            self.notify("the /home partition has no filesystem yet; it will be formatted", severity="warning")
            d.format_home = True
        self.app.next_step()  # type: ignore[attr-defined]


def disk_summary(d) -> tuple[str, str]:
    """(one-line description, what gets erased) for the summary and the final confirmation."""
    fs = d.filesystem + (", LUKS2 encrypted" if d.encrypt else "")
    if not d.manual:
        return (f"{d.device}  (erase whole disk, {fs}{f', {d.swap_gb}G swap' if d.swap_gb else ''})",
                f"everything on {d.device}")
    parts = [f"EFI {d.esp_partition} ({'format' if d.format_esp else 'keep'})", f"root {d.root_partition} (format {fs})"]
    erased = ([d.esp_partition] if d.format_esp else []) + [d.root_partition]
    if d.boot_partition:
        parts.append(f"/boot {d.boot_partition} (format ext4)"); erased.append(d.boot_partition)
    if d.swap_partition:
        parts.append(f"swap {d.swap_partition}"); erased.append(d.swap_partition)
    if d.home_partition:
        parts.append(f"/home {d.home_partition} ({'format' if d.format_home else 'keep files'})")
        if d.format_home:
            erased.append(d.home_partition)
    return f"{d.device}  manual: " + ", ".join(parts), "partitions " + ", ".join(erased) + f" on {d.device} (others untouched)"


class OptionChoice(StepScreen):
    """One screen per OPTION_STEPS entry, options filtered by the chosen base."""

    def __init__(self, step: str, title: str):
        super().__init__()
        self.step = step
        self.title_text = title

    def compose_body(self) -> ComposeResult:
        opts = capabilities.options(self.profile.base, self.step)
        current = getattr(self.profile, self.step)
        with RadioSet(id="opts"):
            for oid, o in opts.items():
                yield RadioButton(o["label"], id=f"o-{oid}", value=oid == current)
        yield Static(self.hint(), classes="hint")

    def hint(self) -> str:
        name = capabilities.load(self.profile.base)["meta"]["name"]
        notes = {
            "bootloader": "GRUB uses a separate /boot partition and works with encryption and Secure Boot. "
                          "systemd-boot (Arch only) mounts the ESP at /boot and is not Secure Boot signed.",
            "desktop": "Desktops come with their usual display manager. Window managers start from the console "
                       "after you log in, so you can add greetd or ly later if you want a login screen.",
            "graphics": "Mesa covers Intel, AMD and NVIDIA (via Nouveau). Pick the proprietary option only for NVIDIA GPUs.",
            "power": "GNOME and KDE integrate with power-profiles-daemon; TLP gives more battery on laptops but no desktop switcher. Never both.",
            "firewall": f"Default for {name} is pre-selected.",
            "audio": "PipeWire is what every base ships today. PulseAudio is listed only where it still works cleanly.",
            "network": "NetworkManager gives you Wi-Fi in the desktop. systemd-networkd + iwd is for minimal setups and servers.",
        }
        return notes.get(self.step, "")

    def on_mount(self) -> None:
        self.query_one("#opts", RadioSet).focus()

    def apply(self) -> str | None:
        rs = self.query_one("#opts", RadioSet)
        if not rs.pressed_button:
            return "pick one"
        setattr(self.profile, self.step, (rs.pressed_button.id or "").split("-", 1)[1])
        return None


class Account(StepScreen):
    title_text = "Your account and system settings"

    def compose_body(self) -> ComposeResult:
        p = self.profile
        yield Label("Hostname (this computer's name on the network)", classes="field"); yield Input(value=p.hostname, id="hostname")
        yield Label("User name (lowercase, no spaces)", classes="field"); yield Input(value=p.username, id="username")
        yield Label("Password", classes="field"); yield Input(password=True, id="pw1")
        yield Label("Repeat password", classes="field"); yield Input(password=True, id="pw2")
        yield Label("Root password (leave empty to lock root; your user gets sudo)", classes="field")
        yield Input(password=True, id="rootpw")
        yield Label("Language and region (locale) - type to search, e.g. 'german' or 'en_GB'", classes="field")
        yield Picker(choices.locales(), p.locale, "search languages or countries...", id="locale")
        yield Label("Keyboard layout - type to search, e.g. 'uk', 'french', 'dvorak'", classes="field")
        yield Picker(choices.keymaps(), p.xkb_layout or choices.xkb_for_console(p.keymap), "search keyboard layouts...", id="keymap")
        yield Label("Time zone - type your nearest big city, e.g. 'berlin', 'new york', 'tokyo'", classes="field")
        yield Picker(choices.timezones(), p.timezone, "search time zones...", id="tz")
        yield Label("Package mirror URL (leave empty for the distribution default - recommended)", classes="field")
        yield Input(value=p.mirror, id="mirror")

    def on_mount(self) -> None:
        self.query_one("#hostname", Input).focus()

    def apply(self) -> str | None:
        p = self.profile
        v = lambda i: self.query_one(f"#{i}", Input).value.strip()  # noqa: E731
        p.hostname = v("hostname") or "diylinux"
        p.username = v("username")
        if not p.username.isidentifier() or not p.username.islower():
            return "user name must be lowercase letters, digits or underscore"
        if len(v("pw1")) < 4:
            return "password too short"
        if v("pw1") != v("pw2"):
            return "passwords do not match"
        p.password = v("pw1")
        p.root_password = v("rootpw")
        p.locale = self.query_one("#locale", Picker).value
        p.xkb_layout = self.query_one("#keymap", Picker).value
        p.keymap = choices.console_keymap(p.xkb_layout)
        p.timezone = self.query_one("#tz", Picker).value
        p.mirror = v("mirror")
        if not p.locale or not p.timezone or not p.xkb_layout:
            return "pick a locale, a keyboard layout and a time zone"
        if os.path.isdir("/usr/share/zoneinfo") and not os.path.exists(f"/usr/share/zoneinfo/{p.timezone}"):
            return f"unknown time zone {p.timezone}"
        return None


class Summary(StepScreen):
    title_text = "Summary - nothing has been written yet"

    def compose_body(self) -> ComposeResult:
        p = self.profile
        cap = capabilities.load(p.base)
        disk_line, self.erased = disk_summary(p.disk)
        rel = "rolling" if cap["meta"]["rolling"] else cap["meta"].get("release_label", cap["meta"]["release"])
        rows = [("Base", f"{cap['meta']['name']} ({rel})"), ("Disk", disk_line)]
        for step, title in OPTION_STEPS:
            rows.append((title, cap[step][getattr(p, step)]["label"]))
        rows += [("Hostname", p.hostname), ("User", p.username + (" (root locked)" if not p.root_password else "")),
                 ("Language", choices.describe_locale(p.locale) + f" ({p.locale})"),
                 ("Keyboard", next((l for v, l in choices.keymaps() if v == (p.xkb_layout or p.keymap)), p.keymap)),
                 ("Time zone", p.timezone)]
        yield Static("\n".join(f"[b]{k:<36}[/b] {v}" for k, v in rows))
        problems = capabilities.validate(p)
        if problems:
            yield Static("Problems:\n" + "\n".join(f"- {x}" for x in problems), classes="warn")
        if p.base == "arch" and hw.secure_boot_enabled():
            yield Static(ARCH_SB_WARNING, classes="warn")
        if p.power == "tlp" and p.desktop in ("gnome", "kde"):
            yield Static("Note: TLP with GNOME/KDE means the desktop's power mode switcher will be disabled.", classes="info")
        yield Static(f"[b red]Pressing Install erases {self.erased}.[/]", classes="hint")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="panel"):
            yield Static(self.title_text, classes="title")
            yield from self.compose_body()
            with Horizontal(classes="buttons"):
                yield Button("Back", id="back")
                yield Button("Save profile", id="save")
                yield Button("Install", id="next", variant="error", disabled=bool(capabilities.validate(self.profile)))
        yield Footer()

    @on(Button.Pressed, "#save")
    def save(self) -> None:
        path = os.path.expanduser("~/diylinux-profile.json")
        self.profile.save(path)
        self.notify(f"saved to {path} (passwords included, keep it private)")

    def on_next(self) -> None:
        self.app.push_screen(ConfirmModal(f"Erase {disk_summary(self.profile.disk)[1]} and install "
                                          f"{capabilities.load(self.profile.base)['meta']['name']}?", "Erase and install", "Back", warn=True),
                             lambda ok: self.app.next_step() if ok else None)  # type: ignore[attr-defined]


class Install(Screen):
    BINDINGS = [Binding("ctrl+c", "noop", "disabled during install", show=False)]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="panel"):
            yield Static("Installing", classes="title", id="step")
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield RichLog(id="log", highlight=False, markup=False, wrap=True, max_lines=2000)
            with Horizontal(classes="buttons"):
                yield Button("Reboot", id="reboot", variant="success", disabled=True)
                yield Button("Open a shell", id="shell", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        name = capabilities.load(self.app.profile.base)["meta"]["name"]  # type: ignore[attr-defined]
        self.query_one("#step", Static).update(f"Installing {name} - preparing")
        self.run_install()

    @work(thread=True, exclusive=True)
    def run_install(self) -> None:
        app = self.app
        profile = app.profile  # type: ignore[attr-defined]

        def emit(ev: Event) -> None:
            app.call_from_thread(self.handle, ev)
        run_install(profile, emit)

    def handle(self, ev: Event) -> None:
        log = self.query_one("#log", RichLog)
        if ev.kind == "step":
            name = capabilities.load(self.app.profile.base)["meta"]["name"]  # type: ignore[attr-defined]
            self.query_one("#step", Static).update(f"Installing {name} - step {ev.index}/{ev.total}: {ev.text}")
            self.query_one("#bar", ProgressBar).update(progress=int(100 * (ev.index - 1) / ev.total))
            log.write(f"==> {ev.text}")
        elif ev.kind == "log":
            log.write(ev.text)
        elif ev.kind == "done":
            self.query_one("#bar", ProgressBar).update(progress=100)
            self.query_one("#step", Static).update("[b green]Done.[/] " + ev.text)
            log.write("DONE: " + ev.text)
            self.query_one("#reboot", Button).disabled = False
            self.query_one("#shell", Button).disabled = False
        elif ev.kind == "error":
            self.query_one("#step", Static).update("[b red]Install failed.[/] See the log; the full log is in /tmp/diylinux.log")
            log.write("ERROR: " + ev.text)
            self.query_one("#shell", Button).disabled = False

    @on(Button.Pressed, "#reboot")
    def reboot(self) -> None:
        self.app.exit(return_code=0, message="rebooting")
        if os.environ.get("DIYLINUX_DRYRUN") != "1":
            os.system("systemctl reboot")

    @on(Button.Pressed, "#shell")
    def shell(self) -> None:
        self.app.exit(return_code=2, message="Dropping to a shell. Run `diylinux` to start again.")


# ----------------------------------------------------------------- app
class DiyLinuxApp(App):
    CSS = CSS
    TITLE = "DIY Linux installer"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.profile = Profile()
        self.recommended: str | None = None
        self._log_lines: list[str] = []
        self.flow: list[Any] = [
            Welcome, BaseChoice, DiskChoice,
            *[(lambda s=s, t=t: OptionChoice(s, t)) for s, t in OPTION_STEPS],
            Account, Summary, Install,
        ]
        self.pos = 0

    def on_mount(self) -> None:
        self.push_screen(self._make(0))
        releases.resolve_all(lambda msgs: self.call_from_thread(self._releases_done, msgs))

    def _releases_done(self, msgs: dict[str, str]) -> None:
        if isinstance(self.screen, BaseChoice):
            self.screen.refresh_labels()

    def _make(self, i: int) -> Screen:
        return self.flow[i]()

    def next_step(self) -> None:
        if self.pos + 1 < len(self.flow):
            self.pos += 1
            self.switch_screen(self._make(self.pos))

    def prev_step(self) -> None:
        if self.pos > 0:
            self.pos -= 1
            self.switch_screen(self._make(self.pos))


def main() -> int:
    if os.geteuid() != 0 and os.environ.get("DIYLINUX_DRYRUN") != "1":
        print("DIY Linux must run as root (or set DIYLINUX_DRYRUN=1 to rehearse).", file=sys.stderr)
        return 1
    # mirror everything to a log file for post-mortem
    from .. import run as _run
    logf = open("/tmp/diylinux.log", "a")
    orig = _run._log

    def tee(m: str) -> None:
        logf.write(m + "\n"); logf.flush()
    _run.set_logger(tee)
    app = DiyLinuxApp()
    app.run()
    return app.return_code or 0


if __name__ == "__main__":
    sys.exit(main())
