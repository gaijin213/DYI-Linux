# DIY Linux

**DIY Linux** is a unified, minimal live ISO and terminal installer (TUI) that lets you install latest versions **five major Linux distributions** from a single bootable image with the exact desktop environment, drivers, and system components you want.

<img width="1386" height="755" alt="image" src="https://github.com/user-attachments/assets/d25ed163-04d2-4c45-817f-53d06e7609ec" />


> **Download the Live ISO:** Grab **`DIY-Linux.iso`** from the [**Releases**](https://github.com/gaijin213/DYI-Linux/releases/latest) page.

---

## Features

- **Five Linux Bases in One ISO**
  - **Arch Linux** *(rolling release)*
  - **Debian** *(stable release)*
  - **Ubuntu** *(latest release)*
  - **Fedora** *(latest release)*
  - **openSUSE Tumbleweed** *(rolling release with Secure Boot support)*
- **Pick Your Desktop Environment or Window Manager**
  - **GNOME**, **KDE Plasma**, **Xfce**, **Cinnamon**
  - **Sway**, **Hyprland**, **i3**
  - **None** *(minimal console-only / server install)*
- **Streamlined Disk Partitioning**
  - **Full-Disk Erase (Automatic):** Wipes the selected disk and automatically creates the EFI System Partition, `/boot`, optional swap, and root filesystem (`ext4`, `btrfs`, or `xfs`).
  - **Manual Partitioning (`cfdisk`):** Built-in `cfdisk` launcher to create or modify partitions and assign roles (`EFI`, `/`, `/boot`, `swap`, `/home`) while choosing whether to keep or format existing `/home` and EFI partitions.
- **Modular System Stack**
  - **Bootloader:** GRUB (Secure Boot compatible on supported bases) or `systemd-boot` (Arch)
  - **Graphics:** Open-source Mesa (Intel / AMD / Nouveau) or proprietary NVIDIA drivers
  - **Audio:** PipeWire (default) or PulseAudio
  - **Power Management:** `power-profiles-daemon`, `TLP`, or none
  - **Firewall:** `ufw`, `firewalld`, `nftables`, or none
  - **Networking:** `NetworkManager` or `systemd-networkd` + `iwd`
- **Built-in Base Recommendation Quiz**
  - Not sure which distribution base to pick? Use **"Help me choose a base"** on the Welcome screen to answer four quick questions.
- **Unattended / Reproducible Installs**
  - Save your answers to a `diylinux-profile.json` file on the Summary screen and replay them later with `diylinux-install profile.json`.

---

## Flashing & Booting the ISO

1. Download **`DIY-Linux.iso`** from [**Releases**](https://github.com/gaijin213/DYI-Linux/releases/latest).
2. Write the ISO to a USB drive (at least 2 GB) using **Ventoy**, **Rufus**, **BalenaEtcher**, or `dd`:
   ```bash
   sudo dd if="DIY Linux.iso" of=/dev/sdX bs=4M status=progress oflag=sync
   ```
3. Boot your machine or VM in **UEFI mode** (disable Secure Boot if you plan to install Arch Linux; Debian, Ubuntu, Fedora, and openSUSE support Secure Boot).
4. At the **DIY Linux** GRUB boot menu, press **Enter** on **`DIY Linux (amd64)`** (or wait 5 seconds for automatic boot). The installer launches automatically on `tty1`.

---

## How to Navigate the Installer

The installer uses a clean, high-contrast black-and-white Terminal User Interface (TUI). You can navigate entirely with the keyboard (or mouse in supported environments):

| Key | Action |
| :--- | :--- |
| **`Tab`** / **`Shift + Tab`** | Move forward / backward between fields, lists, and buttons |
| **`↑`** / **`↓`** (Arrow Keys) | Move through list items or radio buttons |
| **`Space`** | Select a radio button or toggle a checkbox |
| **`Enter`** | Activate a focused button, open a partition dropdown, or confirm a selection |
| **`Esc`** | Go back to the previous step |
| **`Ctrl + Q`** | Quit the installer to a root shell |

### Connecting to Wi-Fi (if not using Ethernet)

- Ethernet connections are configured automatically via DHCP before the Welcome screen appears.
- If you need to connect to **Wi-Fi**:
  1. Press **`Alt + F2`** (or `Ctrl + Alt + F2`) to switch to `tty2`.
  2. Run **`nmtui`** and connect to your wireless network.
  3. Press **`Alt + F1`** to return to the installer on `tty1` (the Welcome screen refreshes network status automatically every 2 seconds).

---

## Step-by-Step Walkthrough

1. **Welcome Screen**
   - Displays detected CPU architecture, UEFI firmware status, Secure Boot state, and live network connectivity.
   - Select **Start** (or **Help me choose a base** for a guided recommendation).
2. **Base Distribution**
   - Highlight **Arch Linux**, **Debian**, **Ubuntu**, **Fedora**, or **openSUSE Tumbleweed** and press **Enter** (or select **Next**).
3. **Disk & Partitioning**
   - Select your target disk from the top list.
   - Choose **Erase the whole disk** (automatic partitioning + optional swap size in GB) **or** **Manual**:
     - In **Manual** mode, select **Open partition editor (cfdisk) on the selected disk** to create/edit partitions:
       - Create an **EFI System** partition (at least `512M`, type `EFI System`) and a **Root** partition (at least `30G`, type `Linux filesystem`), then select **Write** -> type `yes` -> **Quit**.
     - Back in the installer, press **Enter** on each partition dropdown (`EFI`, `Root /`, and optional `/boot`, `swap`, `/home`) to assign your partitions.
   - Choose your root filesystem (`ext4`, `btrfs`, or `xfs`) and select **Next**.
4. **System Options**
   - Step through **Bootloader**, **Desktop environment / window manager**, **Graphics driver**, **Power management**, **Firewall**, **Audio**, and **Network manager**.
5. **Account & Localization**
   - Enter your **hostname**, **username** (lowercase), **user password**, and optional **root password** (leave empty to lock root and grant `sudo` to your user).
   - Type in the search boxes to filter and select your **Language/Locale**, **Keyboard Layout**, and **Time Zone**.
6. **Summary & Install**
   - Review all selections and verify which disk/partitions will be formatted.
   - Optionally select **Save profile** to export `~/diylinux-profile.json`.
   - Select **Install** and confirm to begin installation. Once complete, select **Reboot** and remove the installation media.

---

## Repository Structure

- `diylinux/` — Python package implementing the Textual TUI (`diylinux/tui/`), hardware & disk management (`hw.py`, `disk.py`), per-distro capability matrices (`diylinux/capabilities/*.toml`), and installation backends (`diylinux/backends/`).
- `live/` — Live ISO GRUB menu configuration (`live/grub/`) and `tty1` autostart script (`live/profile.d/diy-linux-autostart.sh`).
- `pyproject.toml` — Package metadata and entry points (`diylinux` and `diylinux-install`).
