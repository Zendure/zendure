"""BLE Wi-Fi provisioning for Zendure devices (local, no cloud token).

Kept apart from the HTTP client so that only callers that provision devices
need ``bleak``.
"""

from .advertisement import parse_serial_number
from .const import (
    COMMAND_CHAR_UUID,
    LOCAL_NAME_PREFIX,
    NOTIFY_CHAR_UUID,
    PROVISIONING_SERVICE_UUID,
)
from .provision import ProvisionResult, async_provision_wifi, build_provision_request

__all__ = [
    "COMMAND_CHAR_UUID",
    "LOCAL_NAME_PREFIX",
    "NOTIFY_CHAR_UUID",
    "PROVISIONING_SERVICE_UUID",
    "ProvisionResult",
    "async_provision_wifi",
    "build_provision_request",
    "parse_serial_number",
]
