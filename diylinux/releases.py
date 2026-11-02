"""Find the newest release of each base at run time, so an old ISO keeps installing current systems.

The TOML metadata carries the release that was current when the ISO was built; this module asks the
distribution's own servers for the newest one and, when that works, replaces release / release_label in
the loaded capability table. Arch and Tumbleweed are rolling and need nothing. Every lookup is best effort:
on any failure the built-in value stays and the caller gets an explanation string.
"""
from __future__ import annotations

import re
import threading
import urllib.request
from typing import Callable

from . import capabilities
from .run import DRY

TIMEOUT = 8
DEBIAN_RELEASE_URL = "https://deb.debian.org/debian/dists/stable/Release"
UBUNTU_META_URL = "https://changelogs.ubuntu.com/meta-release-lts"
FEDORA_RELEASES_URL = "https://dl.fedoraproject.org/pub/fedora/linux/releases/"

_lock = threading.Lock()
_done: dict[str, str] = {}        # base -> status message, once resolved (or failed)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "diylinux-installer"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


# ---- parsers (pure, unit-testable) ----
def parse_debian(release_file: str) -> tuple[str, str]:
    """Return (codename, label) from a dists/stable/Release file."""
    fields = dict(re.findall(r"^([A-Za-z-]+): (.*)$", release_file, re.M))
    codename = fields.get("Codename", "").strip()
    version = fields.get("Version", "").strip()
    if not re.fullmatch(r"[a-z]+", codename):
        raise ValueError("no Codename in Release file")
    return codename, f"{version} ({codename})" if version else codename


def parse_ubuntu(meta_release: str) -> tuple[str, str]:
    """Return (codename, label) of the newest *supported, released* LTS in meta-release-lts."""
    best: tuple[str, str] | None = None
    for block in meta_release.strip().split("\n\n"):
        fields = dict(re.findall(r"^([A-Za-z-]+): (.*)$", block, re.M))
        if fields.get("Supported", "0").strip() != "1":
            continue
        dist, version = fields.get("Dist", "").strip(), fields.get("Version", "").strip()
        if re.fullmatch(r"[a-z]+", dist) and version:
            best = (dist, version)          # blocks are oldest -> newest
    if not best:
        raise ValueError("no supported LTS found")
    return best[0], "latest"


def parse_fedora(listing_html: str) -> tuple[str, str]:
    """Return (version, label) for the highest numbered directory in the releases/ listing."""
    versions = {int(v) for v in re.findall(r'href="(\d+)/?"', listing_html)}
    if not versions:
        raise ValueError("no release directories found")
    v = str(max(versions))
    return v, "latest"


# ---- public API ----
def resolve(base: str, log: Callable[[str], None] | None = None) -> str:
    """Resolve one base (blocking, network). Returns a one-line status; updates capabilities.load(base)."""
    meta = capabilities.load(base)["meta"]
    name = meta["name"]
    if meta.get("rolling"):
        msg = f"{name} is rolling, always current"
    elif DRY:
        msg = f"{name}: dry run, keeping built-in release {meta.get('release_label', meta['release'])}"
    else:
        try:
            if base == "debian":
                rel, label = parse_debian(_fetch(DEBIAN_RELEASE_URL))
            elif base == "ubuntu":
                rel, label = parse_ubuntu(_fetch(UBUNTU_META_URL))
            elif base == "fedora":
                rel, label = parse_fedora(_fetch(FEDORA_RELEASES_URL))
            else:
                raise ValueError(f"no release lookup for {base}")
            old = meta.get("release_label", meta["release"])
            meta["release"], meta["release_label"] = rel, label
            msg = f"{name}: newest release is {label}" + ("" if label == old else f" (ISO was built for {old})")
        except Exception as e:  # noqa: BLE001
            msg = f"{name}: could not check for a newer release ({e.__class__.__name__}), using {meta.get('release_label', meta['release'])}"
    with _lock:
        _done[base] = msg
    if log:
        log(msg)
    return msg


def resolve_all(done: Callable[[dict[str, str]], None] | None = None) -> threading.Thread:
    """Resolve every base in a background thread; call done(messages) when finished."""
    def worker() -> None:
        for b in capabilities.BASES:
            resolve(b)
        if done:
            done(dict(_done))
    t = threading.Thread(target=worker, name="diylinux-releases", daemon=True)
    t.start()
    return t


def status(base: str) -> str | None:
    with _lock:
        return _done.get(base)
