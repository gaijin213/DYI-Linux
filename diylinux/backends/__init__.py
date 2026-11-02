from .base import Backend
from .arch import ArchBackend
from .debian import DebianBackend, UbuntuBackend
from .fedora import FedoraBackend
from .opensuse import OpenSUSEBackend

BACKENDS = {
    "arch": ArchBackend,
    "debian": DebianBackend,
    "ubuntu": UbuntuBackend,
    "fedora": FedoraBackend,
    "opensuse": OpenSUSEBackend,
}


def get(profile, layout, arch: str) -> Backend:
    return BACKENDS[profile.base](profile, layout, arch)
