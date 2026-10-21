"""Identify a Zendure device from its BLE advertisement.

The advertised local name (``Zen<x>_<n>``) is too short to identify a device,
so the serial number is read from manufacturer data instead: the 16-bit
company id (little endian) holds the first two serial characters and the
payload holds the remaining 13, followed by one trailing status byte.
"""

from collections.abc import Mapping
from typing import Final

from .const import SERIAL_NUMBER_LENGTH

# 2 company-id bytes + 13 serial bytes + 1 trailing byte.
_RAW_LENGTH: Final = SERIAL_NUMBER_LENGTH + 1


def parse_serial_number(manufacturer_data: Mapping[int, bytes]) -> str | None:
    """Return the serial number carried in ``manufacturer_data``, or ``None``.

    ``None`` means the advertisement is not a Zendure device in the expected
    format, so callers can ignore unrelated devices whose name merely starts
    with ``Zen``.
    """
    for company_id, payload in manufacturer_data.items():
        if not 0 <= company_id <= 0xFFFF:
            continue
        raw = company_id.to_bytes(2, "little") + bytes(payload)
        if len(raw) != _RAW_LENGTH:
            continue
        serial = raw[:SERIAL_NUMBER_LENGTH]
        if serial.isascii() and serial.isalnum() and serial.upper() == serial:
            return serial.decode("ascii")
    return None


__all__ = ["parse_serial_number"]
