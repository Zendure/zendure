"""GATT layout and limits of the Zendure BLE provisioning interface.

Verified on a SolarFlow device (advertised as ``ZenEB4_5``). The device needs no
pairing; writes require a response.
"""

from typing import Final

PROVISIONING_SERVICE_UUID: Final = "0000a002-0000-1000-8000-00805f9b34fb"
"""Vendor service that carries provisioning messages."""

COMMAND_CHAR_UUID: Final = "0000c304-0000-1000-8000-00805f9b34fb"
"""Write-with-response characteristic for requests."""

NOTIFY_CHAR_UUID: Final = "0000c305-0000-1000-8000-00805f9b34fb"
"""Read/notify characteristic the device pushes replies on."""

LOCAL_NAME_PREFIX: Final = "Zen"
"""Advertised local names start with this (``ZenEB4_5``); case-sensitive."""

MAX_PACKET_BYTES: Final = 500
"""Largest single write the device accepts (firmware limit)."""

SERIAL_NUMBER_LENGTH: Final = 15

DEFAULT_PROVISION_TIMEOUT: Final = 60.0
"""Seconds to wait for the join result, including the device's DHCP lease."""

HANDSHAKE_TIMEOUT: Final = 5.0
"""Seconds to wait for the device's ``BLESPP`` greeting after subscribing."""

WRITE_TIMEOUT: Final = 10.0
"""Seconds allowed for the request write itself to be acknowledged."""

__all__ = [
    "COMMAND_CHAR_UUID",
    "DEFAULT_PROVISION_TIMEOUT",
    "HANDSHAKE_TIMEOUT",
    "LOCAL_NAME_PREFIX",
    "MAX_PACKET_BYTES",
    "NOTIFY_CHAR_UUID",
    "PROVISIONING_SERVICE_UUID",
    "SERIAL_NUMBER_LENGTH",
    "WRITE_TIMEOUT",
]
