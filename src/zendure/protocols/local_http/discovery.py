"""mDNS host-name helpers for zenSDK devices.

Devices advertise ``zendure-<productModel without spaces>-<sn>.local``. Browsing
(zeroconf) is the integration's job; this module only builds and parses names,
so a caller holding a name can derive the host and identity it expects.
"""

from typing import Final

_PREFIX: Final = "zendure-"
_SUFFIX: Final = ".local"


def build_mdns_hostname(product: str, serial_number: str) -> str:
    """``SolarFlow 5000 Max Pro`` + sn -> ``zendure-SolarFlow5000MaxPro-<sn>.local``."""
    model = "".join(product.split())
    return f"{_PREFIX}{model}-{serial_number}{_SUFFIX}"


def parse_mdns_hostname(hostname: str) -> tuple[str, str] | None:
    """Split an advertised host name into ``(product, serial_number)``.

    Accepts an optional trailing dot. Returns ``None`` when the name does not
    follow the zenSDK pattern.
    """
    name = hostname.rstrip(".")
    if not name.lower().startswith(_PREFIX) or not name.lower().endswith(_SUFFIX):
        return None
    core = name[len(_PREFIX) : -len(_SUFFIX)]
    product, sep, serial_number = core.rpartition("-")
    if not sep or not product or not serial_number:
        return None
    return product, serial_number


__all__ = ["build_mdns_hostname", "parse_mdns_hostname"]
