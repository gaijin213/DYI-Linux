# Start the installer on the first console only; other consoles stay plain shells.
if [ "$(tty)" = "/dev/tty1" ] && [ -z "$DIYLINUX_STARTED" ]; then
    export DIYLINUX_STARTED=1
    export TERM=linux
    FONT=""
    for arg in $(cat /proc/cmdline); do
        case "$arg" in diylinux.font=*) FONT="${arg#diylinux.font=}";; esac
    done
    if [ -z "$FONT" ]; then
        FBW=$(cut -d, -f1 /sys/class/graphics/fb0/virtual_size 2>/dev/null || echo 0)
        if [ "${FBW:-0}" -ge 2560 ]; then FONT=Uni2-Terminus32x16; else FONT=Uni2-Terminus24x12; fi
    fi
    [ "$FONT" != none ] && setfont "/usr/share/consolefonts/$FONT.psf.gz" 2>/dev/null
    command -v nm-online >/dev/null 2>&1 && nm-online -q --timeout=5 2>/dev/null || true
    PROFILE=""
    for arg in $(cat /proc/cmdline); do
        case "$arg" in diylinux.profile=*) PROFILE="${arg#diylinux.profile=}";; esac
    done
    if [ -z "$PROFILE" ]; then
        DEV=$(blkid -L DIYLINUX_AUTO 2>/dev/null || true)
        if [ -n "$DEV" ]; then
            mkdir -p /run/diylinux-auto && mount -o ro "$DEV" /run/diylinux-auto 2>/dev/null && \
              [ -f /run/diylinux-auto/diylinux-profile.json ] && PROFILE=/run/diylinux-auto/diylinux-profile.json
        fi
    fi
    TEE=/dev/null
    for d in /dev/ttyS0 /dev/ttyAMA0; do [ -c "$d" ] && TEE=$d; done
    if [ -n "$PROFILE" ]; then
        case "$PROFILE" in http*) curl -fsSL "$PROFILE" -o /tmp/diylinux-profile.json && PROFILE=/tmp/diylinux-profile.json;; esac
        echo "DIY Linux: unattended install from $PROFILE" | tee "$TEE"
        exec /usr/local/bin/diylinux-install "$PROFILE" 2>&1 | tee "$TEE"
    else
        exec /usr/local/bin/diylinux
    fi
fi
